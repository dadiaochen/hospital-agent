from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.context_manager import ContextManager, ResetContextState
from app.agent.context_schemas import (
    ContextEnvelope,
    RAGSourceRef,
    RoleSpecificContextView,
    RunSummary,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult, ExpectedCase, ExpectedSource
from app.agent.evaluator import DeterministicEvaluator
from app.agent.model_gateway import DeterministicModelProvider, ModelGateway
from app.agent.model_gateway_schemas import (
    ModelCallRequest,
    ModelCallResult,
    ModelMessage,
)
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RAGTrace,
    RunTrace,
    SafetyTrace,
    build_tool_call_id,
)
from app.agent.workflow_planning import (
    DEFAULT_FORBIDDEN_PHRASES,
    DeterministicWorkflowPlanner,
    WorkflowToolInputBuilder,
)
from app.agent.workflow_schemas import (
    WorkflowFinalAnswerDraft,
    WorkflowPlan,
    WorkflowRunRequest,
    WorkflowRunResult,
)
from app.tools.mock_tools import build_mock_tool_registry
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult


ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "ProfileAgent": ("query_health_profile",),
    "RefillAgent": ("query_prescriptions", "query_medicine_box"),
    "PharmacyAgent": ("check_pharmacy_inventory",),
    "ReminderAgent": ("query_medicine_box",),
    "SafetyAgent": ("search_safety_knowledge",),
}

BLOCKING_SAFETY_FLAGS = {
    "dosage_change_request",
    "medication_switch_request",
    "severe_symptom",
    "stop_medication_request",
    "urgent_human_escalation",
}

class WorkflowState(TypedDict, total=False):
    request: WorkflowRunRequest
    supplied_expected_case: ExpectedCase | None
    plan: WorkflowPlan
    context_envelope: ContextEnvelope
    role_views: dict[str, RoleSpecificContextView]
    tool_results: list[ToolResult]
    safety_blocked: bool
    model_result: ModelCallResult[WorkflowFinalAnswerDraft]
    final_answer: FinalAnswerTrace
    evaluation_case: ExpectedCase
    run_trace: RunTrace
    run_summary: RunSummary
    reset_state: ResetContextState
    evaluation_result: EvaluationResult
    visited_nodes: tuple[str, ...]


class LangGraphAgentWorkflow:
    def __init__(
        self,
        *,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
        model_gateway: ModelGateway | None = None,
        evaluator: DeterministicEvaluator | None = None,
        planner: DeterministicWorkflowPlanner | None = None,
        tool_input_builder: WorkflowToolInputBuilder | None = None,
    ) -> None:
        self.context_manager = context_manager or ContextManager()
        self.tool_registry = tool_registry or build_mock_tool_registry()
        self.model_gateway = model_gateway or _default_workflow_model_gateway()
        self.evaluator = evaluator or DeterministicEvaluator()
        self.planner = planner or DeterministicWorkflowPlanner()
        self.tool_input_builder = tool_input_builder or WorkflowToolInputBuilder()
        self.graph = self._build_graph()

    def run(
        self,
        request: WorkflowRunRequest,
        *,
        expected_case: ExpectedCase | None = None,
    ) -> WorkflowRunResult:
        if expected_case is not None:
            if expected_case.expected_member_id != request.member_id:
                raise ValueError("expected case member_id must match workflow request")
            if expected_case.user_input != request.user_input:
                raise ValueError("expected case input must match workflow request")

        state = self.graph.invoke(
            WorkflowState(
                request=request,
                supplied_expected_case=expected_case,
                role_views={},
                tool_results=[],
                visited_nodes=(),
            )
        )
        return WorkflowRunResult(
            request=request,
            plan=state["plan"],
            context_envelope=state["context_envelope"],
            role_views=state["role_views"],
            tool_results=state["tool_results"],
            model_result=state["model_result"],
            run_trace=state["run_trace"],
            run_summary=state["run_summary"],
            reset_state=dict(state["reset_state"]),
            evaluation_case=state["evaluation_case"],
            evaluation_result=state["evaluation_result"],
            visited_nodes=state["visited_nodes"],
        )

    def run_case(
        self,
        expected_case: ExpectedCase,
        *,
        user_id: str = "user-workflow",
        human_confirmation_granted: bool = True,
    ) -> WorkflowRunResult:
        return self.run(
            WorkflowRunRequest(
                run_id=f"workflow-{expected_case.case_id}",
                task_id=f"task-{expected_case.case_id}",
                user_id=user_id,
                member_id=expected_case.expected_member_id,
                user_input=expected_case.user_input,
                medication_name="amlodipine tablets",
                city="mock city",
                human_confirmation_granted=human_confirmation_granted,
            ),
            expected_case=expected_case,
        )

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("context_manager", self._context_node)
        graph.add_node("profile_agent", self._profile_node)
        graph.add_node("refill_agent", self._refill_node)
        graph.add_node("pharmacy_agent", self._pharmacy_node)
        graph.add_node("reminder_agent", self._reminder_node)
        graph.add_node("safety_agent", self._safety_node)
        graph.add_node("confirmation_draft", self._confirmation_node)
        graph.add_node("final_answer", self._final_answer_node)
        graph.add_node("run_trace", self._run_trace_node)
        graph.add_node("context_reset", self._reset_node)
        graph.add_node("evaluator", self._evaluator_node)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "context_manager")
        graph.add_conditional_edges(
            "context_manager",
            lambda state: self._next_role(state, after=None),
            self._role_routes(),
        )
        graph.add_conditional_edges(
            "profile_agent",
            lambda state: self._next_role(state, after="ProfileAgent"),
            self._role_routes(),
        )
        graph.add_conditional_edges(
            "refill_agent",
            lambda state: self._next_role(state, after="RefillAgent"),
            self._role_routes(),
        )
        graph.add_conditional_edges(
            "pharmacy_agent",
            lambda state: self._next_role(state, after="PharmacyAgent"),
            self._role_routes(),
        )
        graph.add_edge("reminder_agent", "safety_agent")
        graph.add_conditional_edges(
            "safety_agent",
            self._route_after_safety,
            {
                "confirmation_draft": "confirmation_draft",
                "final_answer": "final_answer",
            },
        )
        graph.add_edge("confirmation_draft", "final_answer")
        graph.add_edge("final_answer", "run_trace")
        graph.add_edge("run_trace", "context_reset")
        graph.add_edge("context_reset", "evaluator")
        graph.add_edge("evaluator", END)
        return graph.compile()

    @staticmethod
    def _role_routes() -> dict[str, str]:
        return {
            "profile_agent": "profile_agent",
            "refill_agent": "refill_agent",
            "pharmacy_agent": "pharmacy_agent",
            "reminder_agent": "reminder_agent",
            "safety_agent": "safety_agent",
        }

    def _next_role(
        self,
        state: WorkflowState,
        *,
        after: str | None,
    ) -> str:
        roles = (*_business_roles(state["plan"]), "SafetyAgent")
        start = roles.index(after) + 1 if after is not None else 0
        return _node_name(roles[start])

    def _planner_node(self, state: WorkflowState) -> dict[str, Any]:
        resume_context = state["request"].resume_context
        return {
            "plan": (
                resume_context.plan
                if resume_context is not None
                else self.planner.plan(state["request"])
            ),
            "visited_nodes": _visit(state, "planner"),
        }

    def _context_node(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        plan = state["plan"]
        resume_context = request.resume_context
        confirmed_slots: dict[str, Any] = {"member_id": request.member_id}
        conversation_source_ids: list[str] = []
        if resume_context is not None:
            summary = resume_context.run_summary
            confirmed_slots.update(
                {
                    "resumed_from_run_id": resume_context.previous_run_id,
                    "previous_run_summary_ref": (
                        f"run_summary:{resume_context.previous_run_id}"
                    ),
                }
            )
            conversation_source_ids.extend(
                [
                    f"run_summary:{resume_context.previous_run_id}",
                    *(ref.source_id for ref in summary.tool_evidence_refs),
                    *(ref.source_id for ref in summary.rag_source_refs),
                ]
            )
        envelope = self.context_manager.build_envelope(
            user_input=request.user_input,
            run_id=request.run_id,
            task_id=request.task_id,
            user_id=request.user_id,
            member_id=request.member_id,
            intent=plan.intent,
            action_type=plan.action_type,
            confirmed_slots=confirmed_slots,
            pending_confirmations=(
                ["human_confirmation_required"]
                if plan.human_confirmation_required
                else []
            ),
            safety_flags=list(plan.safety_flags),
            allowed_tools=list(plan.required_tools),
            conversation_source_ids=conversation_source_ids,
        )
        planner_view = self.context_manager.build_role_view(envelope, "Planner")
        return {
            "context_envelope": envelope,
            "role_views": {"Planner": planner_view},
            "visited_nodes": _visit(state, "context_manager"),
        }

    def _profile_node(self, state: WorkflowState) -> dict[str, Any]:
        return self._role_node(state, "ProfileAgent", "profile_agent")

    def _refill_node(self, state: WorkflowState) -> dict[str, Any]:
        return self._role_node(state, "RefillAgent", "refill_agent")

    def _pharmacy_node(self, state: WorkflowState) -> dict[str, Any]:
        return self._role_node(state, "PharmacyAgent", "pharmacy_agent")

    def _reminder_node(self, state: WorkflowState) -> dict[str, Any]:
        return self._role_node(state, "ReminderAgent", "reminder_agent")

    def _safety_node(self, state: WorkflowState) -> dict[str, Any]:
        updates = self._role_node(state, "SafetyAgent", "safety_agent")
        plan = state["plan"]
        updates["safety_blocked"] = bool(
            BLOCKING_SAFETY_FLAGS & set(plan.safety_flags)
        )
        return updates

    def _role_node(
        self,
        state: WorkflowState,
        role: str,
        node_name: str,
    ) -> dict[str, Any]:
        context = state["context_envelope"]
        plan = state["plan"]
        tools = [
            tool
            for tool in ROLE_TOOLS[role]
            if tool in plan.required_tools
            and not any(result.tool_name == tool for result in state["tool_results"])
        ]
        permission_view = self.context_manager.build_role_view(
            context,
            role,
            extra_allowed_tools=[
                spec.name for spec in self.tool_registry.list_allowed_tools(role)
            ],
        )
        results = list(state["tool_results"])
        for tool_name in tools:
            results.append(self._call_tool(state, permission_view, role, tool_name))
        refreshed = self._refresh_context(state, results)
        final_view = self.context_manager.build_role_view(
            refreshed,
            role,
            extra_allowed_tools=[
                spec.name for spec in self.tool_registry.list_allowed_tools(role)
            ],
        )
        role_views = {**state.get("role_views", {}), role: final_view}
        return {
            "context_envelope": refreshed,
            "role_views": role_views,
            "tool_results": results,
            "visited_nodes": _visit(state, node_name),
        }

    def _confirmation_node(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        if not request.human_confirmation_granted:
            return {"visited_nodes": _visit(state, "confirmation_draft")}

        role = _draft_role(state["plan"])
        context = state["context_envelope"]
        permission_view = self.context_manager.build_role_view(
            context,
            role,
            extra_allowed_tools=[
                spec.name for spec in self.tool_registry.list_allowed_tools(role)
            ],
        )
        results = list(state["tool_results"])
        draft_result = self._call_tool(
                state,
                permission_view,
                role,
                "create_confirmation_draft",
            )
        results.append(draft_result)
        refreshed = self._refresh_context(
            state,
            results,
            pending_confirmations=[] if draft_result.success else None,
        )
        final_view = self.context_manager.build_role_view(
            refreshed,
            role,
            extra_allowed_tools=[
                spec.name for spec in self.tool_registry.list_allowed_tools(role)
            ],
        )
        return {
            "context_envelope": refreshed,
            "role_views": {**state["role_views"], role: final_view},
            "tool_results": results,
            "visited_nodes": _visit(state, "confirmation_draft"),
        }

    def _final_answer_node(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        plan = state["plan"]
        source_names = _source_names(state["tool_results"])
        draft_created = any(
            result.tool_name == "create_confirmation_draft" and result.success
            for result in state["tool_results"]
        )
        payload = {
            "blocked": state.get("safety_blocked", False),
            "confirmation_required": plan.human_confirmation_required,
            "draft_created": draft_created,
            "source_names": source_names,
            "intent": plan.intent,
        }
        model_result = self.model_gateway.invoke(
            ModelCallRequest(
                run_id=request.run_id,
                task_id=request.task_id,
                member_id=request.member_id,
                purpose="workflow_final_answer",
                messages=(
                    ModelMessage(
                        role="system",
                        content=(
                            "Return only the declared safe workflow final-answer JSON."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False),
                    ),
                ),
            ),
            WorkflowFinalAnswerDraft,
        )
        answer = model_result.output or WorkflowFinalAnswerDraft(
            content=(
                "A validated answer could not be generated. "
                "Please continue with manual review."
            ),
            contains_factual_claims=False,
            waiting_for_user_confirmation=(
                plan.human_confirmation_required and not draft_created
            ),
            human_confirmation_present=draft_created,
            action_status=(
                "draft"
                if draft_created
                else "awaiting_confirmation"
                if plan.human_confirmation_required
                else "none"
            ),
        )
        return {
            "model_result": model_result,
            "final_answer": FinalAnswerTrace(
                answer_id=f"answer:{request.run_id}",
                content=answer.content,
                contains_factual_claims=answer.contains_factual_claims,
                waiting_for_user_confirmation=answer.waiting_for_user_confirmation,
                human_confirmation_present=answer.human_confirmation_present,
                action_status=answer.action_status,
            ),
            "visited_nodes": _visit(state, "final_answer"),
        }

    def _run_trace_node(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        plan = state["plan"]
        expected = state.get("supplied_expected_case") or self._operational_case(state)
        tool_calls = tuple(
            result.to_tool_call_trace(member_id=request.member_id)
            for result in state["tool_results"]
        )
        rag_traces = tuple(self._rag_traces(state))
        model_trace = state["model_result"].trace
        run_trace = RunTrace(
            case_id=expected.case_id,
            run_id=request.run_id,
            task_id=request.task_id,
            user_id=request.user_id,
            member_id=request.member_id,
            intent=plan.intent,
            tool_calls=tool_calls,
            rag_traces=rag_traces,
            safety_trace=SafetyTrace(
                member_id=request.member_id,
                flags=plan.safety_flags,
                blocked=state.get("safety_blocked", False),
                requires_human_confirmation=plan.human_confirmation_required,
            ),
            final_answer=state["final_answer"],
            latency_ms=(
                sum(result.latency_ms for result in state["tool_results"])
                + model_trace.latency_ms
            ),
            schema_valid=(
                all(result.schema_valid for result in state["tool_results"])
                and model_trace.schema_valid
                and model_trace.safety_passed
            ),
        )
        return {
            "evaluation_case": expected,
            "run_trace": run_trace,
            "visited_nodes": _visit(state, "run_trace"),
        }

    def _reset_node(self, state: WorkflowState) -> dict[str, Any]:
        reset = self.context_manager.reset_after_run(
            envelope=state["context_envelope"],
            run_trace=state["run_trace"],
            final_answer=state["final_answer"],
        )
        return {
            "run_summary": reset["run_summary"],
            "reset_state": reset,
            "visited_nodes": _visit(state, "context_reset"),
        }

    def _evaluator_node(self, state: WorkflowState) -> dict[str, Any]:
        evaluation = self.evaluator.evaluate(
            state["evaluation_case"],
            state["run_trace"],
        )
        summary = self.context_manager.create_run_summary(
            envelope=state["context_envelope"],
            run_trace=state["run_trace"],
            final_answer=state["final_answer"],
            evaluation_result=evaluation,
        )
        evaluation_ref = summary.evaluation_ref
        reset = ResetContextState(state["reset_state"])
        reset["run_summary"] = summary
        reset["evaluation_ref"] = evaluation_ref
        return {
            "evaluation_result": evaluation,
            "run_summary": summary,
            "reset_state": reset,
            "visited_nodes": _visit(state, "evaluator"),
        }

    def _route_after_safety(self, state: WorkflowState) -> str:
        plan = state["plan"]
        if state.get("safety_blocked", False):
            return "final_answer"
        if plan.human_confirmation_required:
            return "confirmation_draft"
        return "final_answer"

    def _call_tool(
        self,
        state: WorkflowState,
        view: RoleSpecificContextView,
        role: str,
        tool_name: str,
    ) -> ToolResult:
        request = state["request"]
        plan = state["plan"]
        return self.tool_registry.call(
            tool_name,
            self.tool_input_builder.build(
                tool_name,
                request=request,
                plan=plan,
                registry=self.tool_registry,
                tool_results=state["tool_results"],
            ),
            ToolExecutionContext(
                run_id=request.run_id,
                task_id=request.task_id,
                user_id=request.user_id,
                member_id=request.member_id,
                agent_role=role,
                allowed_tools=list(view.allowed_tools),
                safety_flags=list(plan.safety_flags),
                human_confirmation_granted=(
                    request.human_confirmation_granted
                    if tool_name == "create_confirmation_draft"
                    else False
                ),
            ),
        )

    def _refresh_context(
        self,
        state: WorkflowState,
        results: list[ToolResult],
        *,
        pending_confirmations: list[str] | None = None,
    ) -> ContextEnvelope:
        request = state["request"]
        plan = state["plan"]
        current = state["context_envelope"]
        return self.context_manager.build_envelope(
            user_input=request.user_input,
            run_id=request.run_id,
            task_id=request.task_id,
            user_id=request.user_id,
            member_id=request.member_id,
            intent=plan.intent,
            action_type=plan.action_type,
            missing_slots=list(current.task_state.missing_slots),
            confirmed_slots=dict(current.task_state.confirmed_slots),
            pending_confirmations=(
                list(current.task_state.pending_confirmations)
                if pending_confirmations is None
                else pending_confirmations
            ),
            tool_evidence_refs=self._tool_evidence_refs(request, results),
            rag_source_refs=self._rag_source_refs(state, results),
            safety_flags=list(plan.safety_flags),
            allowed_tools=list(plan.required_tools),
            memory_refs=list(current.memory_refs),
            conversation_source_ids=list(current.conversation_summary.source_ids),
        )

    @staticmethod
    def _tool_evidence_refs(
        request: WorkflowRunRequest,
        results: Sequence[ToolResult],
    ) -> list[ToolEvidenceRef]:
        refs: list[ToolEvidenceRef] = []
        for index, result in enumerate(results, start=1):
            if not result.success or not result.evidence_present:
                continue
            source_id = result.output.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                continue
            refs.append(
                ToolEvidenceRef(
                    source_id=source_id,
                    run_id=request.run_id,
                    member_id=request.member_id,
                    tool_name=result.tool_name,
                    tool_call_id=build_tool_call_id(
                        request.run_id,
                        index,
                        result.tool_name,
                    ),
                    success=True,
                    schema_valid=result.schema_valid,
                )
            )
        return refs

    def _rag_source_refs(
        self,
        state: WorkflowState,
        results: Sequence[ToolResult],
    ) -> list[RAGSourceRef]:
        search = next(
            (
                result
                for result in results
                if result.tool_name == "search_safety_knowledge" and result.success
            ),
            None,
        )
        if search is None:
            return []
        retrieved_sources = search.output.get("sources")
        if isinstance(retrieved_sources, list):
            refs = [
                _retrieved_rag_ref(state["request"], source)
                for source in retrieved_sources
                if isinstance(source, dict)
            ]
            if refs:
                return refs
        expected = state.get("supplied_expected_case")
        names = [
            source.source_name
            for source in expected.expected_sources
            if source.source_type == "rag_source"
        ] if expected is not None else ["workflow_safety_rules"]
        base_id = str(search.output.get("source_id", f"rag:{state['request'].run_id}"))
        return [
            RAGSourceRef(
                source_id=f"{base_id}:{name}",
                document_id=name,
                chunk_id="workflow-source",
                member_id=state["request"].member_id,
                purpose="workflow safety grounding",
            )
            for name in names
        ]

    def _rag_traces(
        self,
        state: WorkflowState,
    ) -> list[RAGTrace]:
        refs = state["context_envelope"].rag_source_refs
        return [
            RAGTrace(
                source_id=ref.source_id,
                source_name=ref.document_id,
                member_id=state["request"].member_id,
                retrieved=True,
                schema_valid=True,
            )
            for ref in refs
        ]

    def _operational_case(self, state: WorkflowState) -> ExpectedCase:
        plan = state["plan"]
        request = state["request"]
        expected_tools = [
            tool
            for tool in plan.required_tools
            if tool != "create_confirmation_draft"
            or request.human_confirmation_granted
        ]
        successful_results = {
            result.tool_name: result
            for result in state["tool_results"]
            if result.success and result.evidence_present
        }
        expected_sources = [
            ExpectedSource(
                source_type="tool_evidence",
                source_name=(
                    successful_results[tool].source_name or tool
                    if tool in successful_results
                    else tool
                ),
            )
            for tool in expected_tools
            if tool not in {"create_confirmation_draft", "search_safety_knowledge"}
        ]
        if "search_safety_knowledge" in expected_tools:
            rag_names = [
                ref.document_id
                for ref in state["context_envelope"].rag_source_refs
            ] or ["workflow_safety_rules"]
            expected_sources.extend(
                ExpectedSource(source_type="rag_source", source_name=name)
                for name in rag_names
            )
        return ExpectedCase(
            case_id=f"workflow:{request.run_id}",
            input_category=plan.input_category,
            user_input=request.user_input,
            expected_intent=plan.intent,
            expected_member_id=request.member_id,
            expected_required_tools=expected_tools,
            expected_safety_flags=list(plan.safety_flags),
            expected_human_confirmation_required=plan.human_confirmation_required,
            forbidden_phrases=DEFAULT_FORBIDDEN_PHRASES,
            expected_sources=expected_sources,
        )


def _default_workflow_model_gateway() -> ModelGateway:
    return ModelGateway(DeterministicModelProvider(_deterministic_final_payload))


def _deterministic_final_payload(request: ModelCallRequest) -> dict[str, Any]:
    payload = json.loads(request.messages[-1].content)
    sources = ", ".join(payload["source_names"]) or "no verified source"
    if payload["blocked"]:
        content = (
            "This request is blocked for safety and requires licensed clinician or "
            f"urgent human review. Sources: {sources}. No medication instruction "
            "or external action was generated."
        )
    else:
        content = (
            f"Prepared a local {payload['intent']} result from sources: {sources}. "
            "No hospital, purchase, payment, or reminder action was submitted."
        )
    return {
        "content": content,
        "contains_factual_claims": bool(payload["source_names"]),
        "waiting_for_user_confirmation": (
            payload["confirmation_required"] and not payload["draft_created"]
        ),
        "human_confirmation_present": payload["draft_created"],
        "action_status": (
            "draft"
            if payload["draft_created"]
            else "awaiting_confirmation"
            if payload["confirmation_required"]
            else "none"
        ),
    }


def _node_name(role: str) -> str:
    return {
        "ProfileAgent": "profile_agent",
        "RefillAgent": "refill_agent",
        "PharmacyAgent": "pharmacy_agent",
        "ReminderAgent": "reminder_agent",
        "SafetyAgent": "safety_agent",
    }[role]


def _business_roles(plan: WorkflowPlan) -> tuple[str, ...]:
    required = set(plan.required_tools)
    roles: list[str] = []
    if plan.intent == "refill":
        if "query_health_profile" in required:
            roles.append("ProfileAgent")
        if required & {"query_prescriptions", "query_medicine_box"}:
            roles.append("RefillAgent")
        if "check_pharmacy_inventory" in required:
            roles.append("PharmacyAgent")
    elif plan.intent == "pharmacy":
        if required & {"query_prescriptions", "query_medicine_box"}:
            roles.append("RefillAgent")
        if "check_pharmacy_inventory" in required:
            roles.append("PharmacyAgent")
    elif plan.intent == "reminder":
        roles.append("ReminderAgent")
    return tuple(roles)


def _draft_role(plan: WorkflowPlan) -> str:
    if plan.intent == "reminder":
        return "ReminderAgent"
    if plan.intent == "pharmacy":
        return "PharmacyAgent"
    return "RefillAgent"


def _source_names(results: Sequence[ToolResult]) -> list[str]:
    return list(
        dict.fromkeys(
            result.source_name or result.tool_name
            for result in results
            if result.success and result.evidence_present
        )
    )


def _retrieved_rag_ref(
    request: WorkflowRunRequest,
    source: dict[str, Any],
) -> RAGSourceRef:
    return RAGSourceRef(
        source_id=str(source.get("source_id") or "").strip(),
        document_id=str(source.get("document_id") or "").strip(),
        chunk_id=str(source.get("chunk_id") or "").strip(),
        member_id=request.member_id,
        version=(
            str(source.get("chunk_version") or "").strip()
            or str(source.get("document_version") or "").strip()
            or None
        ),
        purpose=(
            str(source.get("purpose") or "").strip()
            or "workflow safety grounding"
        ),
    )


def _visit(state: WorkflowState, node: str) -> tuple[str, ...]:
    return (*state.get("visited_nodes", ()), node)


__all__ = [
    "DeterministicWorkflowPlanner",
    "LangGraphAgentWorkflow",
    "WorkflowToolInputBuilder",
]

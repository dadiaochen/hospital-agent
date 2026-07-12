from pathlib import Path
from typing import Any

from app.agent.context_manager import ContextManager
from app.agent.context_schemas import (
    ContextEnvelope,
    ContractModel,
    RAGSourceRef,
    RoleSpecificContextView,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult, ExpectedCase
from app.agent.evaluator import DeterministicEvaluator
from app.agent.harness_runner import AggregatedMetrics, HarnessRunner
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RAGTrace,
    RunTrace,
    SafetyTrace,
)
from app.tools.mock_tools import build_mock_tool_registry
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult


ROLE_ORDER = (
    "Planner",
    "ProfileAgent",
    "RefillAgent",
    "PharmacyAgent",
    "ReminderAgent",
    "SafetyAgent",
)


DEFAULT_TOOL_ROLES: dict[str, str] = {
    "query_health_profile": "ProfileAgent",
    "query_prescriptions": "RefillAgent",
    "query_medicine_box": "RefillAgent",
    "check_pharmacy_inventory": "PharmacyAgent",
    "search_safety_knowledge": "SafetyAgent",
    "create_confirmation_draft": "RefillAgent",
}


class HarnessRuntimeResult(ContractModel):
    case_id: str
    run_id: str
    context_envelope: ContextEnvelope
    role_views: dict[str, RoleSpecificContextView]
    tool_results: list[ToolResult]
    run_trace: RunTrace
    evaluation_result: EvaluationResult


class HarnessRuntimeBatchResult(ContractModel):
    runtime_results: list[HarnessRuntimeResult]
    evaluation_results: list[EvaluationResult]
    metrics: AggregatedMetrics


class AgentHarnessRuntime:
    """Minimal deterministic runtime for context -> tool -> trace -> eval replay.

    It does not call databases, HTTP APIs, model providers, or LangGraph. It only
    runs local mock tools through ToolRegistry.call and freezes their results.
    """

    def __init__(
        self,
        *,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
        evaluator: DeterministicEvaluator | None = None,
        skip_tools_by_case: dict[str, set[str]] | None = None,
        tool_role_overrides: dict[str, str] | None = None,
    ) -> None:
        self.context_manager = context_manager or ContextManager()
        self.tool_registry = tool_registry or build_mock_tool_registry()
        self.evaluator = evaluator or DeterministicEvaluator()
        self.skip_tools_by_case = skip_tools_by_case or {}
        self.tool_role_overrides = tool_role_overrides or {}
        self._loaded_case: ExpectedCase | None = None

    def load_case(self, expected_case: ExpectedCase) -> ExpectedCase:
        self._loaded_case = expected_case
        return expected_case

    def build_initial_context(self, expected_case: ExpectedCase) -> ContextEnvelope:
        return self.context_manager.build_envelope(
            user_input=expected_case.user_input,
            run_id=self._run_id(expected_case),
            task_id=self._task_id(expected_case),
            user_id="user-harness",
            member_id=expected_case.expected_member_id,
            intent=expected_case.expected_intent,
            action_type=self._action_type(expected_case),
            confirmed_slots={
                "case_id": expected_case.case_id,
                "input_category": expected_case.input_category,
                "member_id": expected_case.expected_member_id,
            },
            pending_confirmations=(
                ["human_confirmation_required"]
                if expected_case.expected_human_confirmation_required
                else []
            ),
            rag_source_refs=self._expected_rag_refs(expected_case),
            safety_flags=expected_case.expected_safety_flags,
            allowed_tools=expected_case.expected_required_tools,
        )

    def build_role_views(
        self,
        context_envelope: ContextEnvelope,
    ) -> dict[str, RoleSpecificContextView]:
        extra_tools_by_role = {
            role: [tool.name for tool in self.tool_registry.list_allowed_tools(role)]
            for role in ROLE_ORDER
        }
        return {
            role: self.context_manager.build_role_view(
                context_envelope,
                role,
                extra_allowed_tools=extra_tools_by_role[role],
            )
            for role in ROLE_ORDER
        }

    def execute_expected_tools_with_mock_registry(
        self,
        expected_case: ExpectedCase,
        context_envelope: ContextEnvelope,
        role_views: dict[str, RoleSpecificContextView] | None = None,
    ) -> list[ToolResult]:
        views = role_views or self.build_role_views(context_envelope)
        skipped = self.skip_tools_by_case.get(expected_case.case_id, set())
        results: list[ToolResult] = []
        for tool_name in expected_case.expected_required_tools:
            if tool_name in skipped:
                continue
            agent_role = self._agent_role_for_tool(expected_case, tool_name)
            results.append(
                self.tool_registry.call(
                    tool_name,
                    self._tool_input(expected_case, tool_name),
                    self._execution_context(
                        expected_case,
                        context_envelope,
                        views,
                        tool_name,
                        agent_role,
                    ),
                )
            )
        return results

    def build_run_trace(
        self,
        expected_case: ExpectedCase,
        context_envelope: ContextEnvelope,
        tool_results: list[ToolResult],
    ) -> RunTrace:
        tool_calls = tuple(
            result.to_tool_call_trace(member_id=context_envelope.member_id)
            for result in tool_results
        )
        rag_traces = tuple(self._rag_traces(expected_case, context_envelope, tool_results))
        return RunTrace(
            case_id=expected_case.case_id,
            run_id=context_envelope.run_id,
            task_id=context_envelope.task_id,
            user_id=context_envelope.user_id,
            member_id=context_envelope.member_id,
            intent=expected_case.expected_intent,
            tool_calls=tool_calls,
            rag_traces=rag_traces,
            safety_trace=SafetyTrace(
                member_id=context_envelope.member_id,
                flags=tuple(expected_case.expected_safety_flags),
                blocked=expected_case.input_category == "safety",
                requires_human_confirmation=(
                    expected_case.expected_human_confirmation_required
                ),
            ),
            final_answer=self._final_answer(expected_case, tool_results, rag_traces),
            latency_ms=self._latency_ms(expected_case, tool_results),
            schema_valid=all(result.schema_valid for result in tool_results),
        )

    def evaluate(
        self,
        expected_case: ExpectedCase,
        run_trace: RunTrace,
    ) -> EvaluationResult:
        return self.evaluator.evaluate(expected_case, run_trace)

    def run_case(self, expected_case: ExpectedCase) -> HarnessRuntimeResult:
        case = self.load_case(expected_case)
        initial_context = self.build_initial_context(case)
        role_views = self.build_role_views(initial_context)
        tool_results = self.execute_expected_tools_with_mock_registry(
            case,
            initial_context,
            role_views,
        )
        context_with_evidence = self._context_with_tool_refs(
            case,
            initial_context,
            tool_results,
        )
        run_trace = self.build_run_trace(case, context_with_evidence, tool_results)
        evaluation = self.evaluate(case, run_trace)
        return HarnessRuntimeResult(
            case_id=case.case_id,
            run_id=run_trace.run_id,
            context_envelope=context_with_evidence,
            role_views=role_views,
            tool_results=tool_results,
            run_trace=run_trace,
            evaluation_result=evaluation,
        )

    def run_all(self, expected_cases: list[ExpectedCase]) -> HarnessRuntimeBatchResult:
        runtime_results = [self.run_case(case) for case in expected_cases]
        evaluation_results = [result.evaluation_result for result in runtime_results]
        return HarnessRuntimeBatchResult(
            runtime_results=runtime_results,
            evaluation_results=evaluation_results,
            metrics=HarnessRunner.aggregate(evaluation_results),
        )

    @staticmethod
    def load_cases_from_path(cases_path: Path) -> list[ExpectedCase]:
        import json

        payload = json.loads(cases_path.read_text(encoding="utf-8"))
        return [ExpectedCase.model_validate(item) for item in payload]

    def _context_with_tool_refs(
        self,
        expected_case: ExpectedCase,
        context: ContextEnvelope,
        tool_results: list[ToolResult],
    ) -> ContextEnvelope:
        return self.context_manager.build_envelope(
            user_input=expected_case.user_input,
            run_id=context.run_id,
            task_id=context.task_id,
            user_id=context.user_id,
            member_id=context.member_id,
            intent=context.intent,
            action_type=context.action_type,
            missing_slots=list(context.task_state.missing_slots),
            confirmed_slots=dict(context.task_state.confirmed_slots),
            pending_confirmations=list(context.task_state.pending_confirmations),
            tool_evidence_refs=self._tool_evidence_refs(context, tool_results),
            rag_source_refs=self._expected_rag_refs(expected_case),
            safety_flags=list(context.safety_flags),
            allowed_tools=list(context.allowed_tools),
            memory_refs=list(context.memory_refs),
        )

    @staticmethod
    def _tool_evidence_refs(
        context: ContextEnvelope,
        tool_results: list[ToolResult],
    ) -> list[ToolEvidenceRef]:
        refs: list[ToolEvidenceRef] = []
        for index, result in enumerate(tool_results, start=1):
            if not result.evidence_present:
                continue
            source_id = result.output.get("source_id") or f"tool:{context.run_id}:{index}"
            refs.append(
                ToolEvidenceRef(
                    source_id=str(source_id),
                    run_id=context.run_id,
                    member_id=context.member_id,
                    tool_name=result.tool_name,
                    tool_call_id=f"{context.run_id}:{index}:{result.tool_name}",
                    success=result.success,
                    schema_valid=result.schema_valid,
                )
            )
        return refs

    def _execution_context(
        self,
        expected_case: ExpectedCase,
        context: ContextEnvelope,
        role_views: dict[str, RoleSpecificContextView],
        tool_name: str,
        agent_role: str,
    ) -> ToolExecutionContext:
        return ToolExecutionContext(
            run_id=context.run_id,
            task_id=context.task_id,
            member_id=context.member_id,
            agent_role=agent_role,
            allowed_tools=list(role_views[agent_role].allowed_tools),
            safety_flags=list(expected_case.expected_safety_flags),
            human_confirmation_granted=self._human_confirmation_for_tool(
                expected_case,
                tool_name,
            ),
        )

    def _agent_role_for_tool(self, expected_case: ExpectedCase, tool_name: str) -> str:
        if tool_name in self.tool_role_overrides:
            return self.tool_role_overrides[tool_name]
        if tool_name == "query_medicine_box" and expected_case.expected_intent == "reminder":
            return "ReminderAgent"
        if tool_name == "search_safety_knowledge":
            if expected_case.expected_intent == "reminder":
                return "ReminderAgent"
            if expected_case.expected_intent == "refill":
                return "RefillAgent"
            return "SafetyAgent"
        if tool_name == "create_confirmation_draft":
            if expected_case.expected_intent == "reminder":
                return "ReminderAgent"
            if expected_case.expected_intent == "pharmacy":
                return "PharmacyAgent"
            return "RefillAgent"
        return DEFAULT_TOOL_ROLES[tool_name]

    @staticmethod
    def _tool_input(expected_case: ExpectedCase, tool_name: str) -> dict[str, Any]:
        member_id = expected_case.expected_member_id
        if tool_name == "query_health_profile":
            return {"member_id": member_id}
        if tool_name == "query_prescriptions":
            return {"member_id": member_id, "medication_name": "amlodipine tablets"}
        if tool_name == "query_medicine_box":
            return {"member_id": member_id, "medication_name": "amlodipine tablets"}
        if tool_name == "check_pharmacy_inventory":
            return {
                "member_id": member_id,
                "medication_name": "amlodipine tablets",
                "city": "mock city",
            }
        if tool_name == "search_safety_knowledge":
            return {"query": expected_case.user_input, "member_id": member_id}
        if tool_name == "create_confirmation_draft":
            return {
                "member_id": member_id,
                "action_type": AgentHarnessRuntime._draft_action_type(expected_case),
                "summary": f"Mock confirmation draft for {expected_case.case_id}.",
            }
        raise ValueError(f"unknown expected mock tool: {tool_name}")

    @staticmethod
    def _draft_action_type(expected_case: ExpectedCase) -> str:
        if expected_case.expected_intent == "reminder":
            return "reminder_create"
        if expected_case.expected_intent == "pharmacy":
            return "pharmacy_option"
        return "refill_request"

    @staticmethod
    def _human_confirmation_for_tool(
        expected_case: ExpectedCase,
        tool_name: str,
    ) -> bool:
        if tool_name != "create_confirmation_draft":
            return False
        return expected_case.expected_human_confirmation_required

    @staticmethod
    def _expected_rag_refs(expected_case: ExpectedCase) -> list[RAGSourceRef]:
        refs: list[RAGSourceRef] = []
        for source in expected_case.expected_sources:
            if source.source_type != "rag_source":
                continue
            refs.append(
                RAGSourceRef(
                    source_id=f"rag:{expected_case.case_id}:{source.source_name}",
                    document_id=source.source_name,
                    chunk_id="mock-runtime-chunk",
                    member_id=expected_case.expected_member_id,
                    purpose="mock harness expected source",
                )
            )
        return refs

    @staticmethod
    def _rag_traces(
        expected_case: ExpectedCase,
        context: ContextEnvelope,
        tool_results: list[ToolResult],
    ) -> list[RAGTrace]:
        search_result = next(
            (
                result
                for result in tool_results
                if result.tool_name == "search_safety_knowledge"
                and result.success
                and result.schema_valid
            ),
            None,
        )
        traces: list[RAGTrace] = []
        for source in expected_case.expected_sources:
            if source.source_type != "rag_source":
                continue
            base_source_id = (
                str(search_result.output.get("source_id"))
                if search_result is not None
                else f"rag:{expected_case.case_id}:{source.source_name}"
            )
            traces.append(
                RAGTrace(
                    source_id=f"{base_source_id}:{source.source_name}",
                    source_name=source.source_name,
                    member_id=context.member_id,
                    retrieved=search_result is not None or source.required,
                    schema_valid=True,
                )
            )
        return traces

    @staticmethod
    def _final_answer(
        expected_case: ExpectedCase,
        tool_results: list[ToolResult],
        rag_traces: tuple[RAGTrace, ...],
    ) -> FinalAnswerTrace:
        tool_sources = [
            result.source_name or result.tool_name
            for result in tool_results
            if result.success and result.evidence_present
        ]
        rag_sources = [trace.source_name for trace in rag_traces if trace.retrieved]
        source_text = ", ".join([*tool_sources, *rag_sources]) or "no verified source"
        confirmation_text = (
            "waiting for user confirmation"
            if expected_case.expected_human_confirmation_required
            else "no final action requested"
        )
        content = (
            f"Mock final answer for {expected_case.case_id}. "
            f"Sources: {source_text}. "
            f"Confirmation: {confirmation_text}. "
            "Safety boundary: this runtime only prepares evidence and drafts; "
            "it does not execute medical, purchase, or reminder actions."
        )
        return FinalAnswerTrace(
            answer_id=f"answer-{expected_case.case_id}",
            content=content,
            contains_factual_claims=bool(tool_sources or rag_sources),
            waiting_for_user_confirmation=(
                expected_case.expected_human_confirmation_required
            ),
            action_status=(
                "awaiting_confirmation"
                if expected_case.expected_human_confirmation_required
                else "none"
            ),
        )

    @staticmethod
    def _latency_ms(
        expected_case: ExpectedCase,
        tool_results: list[ToolResult],
    ) -> int:
        return (
            100
            + len(tool_results) * 10
            + len(expected_case.expected_safety_flags) * 5
            + sum(result.latency_ms for result in tool_results)
        )

    @staticmethod
    def _run_id(expected_case: ExpectedCase) -> str:
        return f"runtime-{expected_case.case_id}"

    @staticmethod
    def _task_id(expected_case: ExpectedCase) -> str:
        return f"task-{expected_case.case_id}"

    @staticmethod
    def _action_type(expected_case: ExpectedCase) -> str:
        if expected_case.expected_intent == "safety_check":
            return "safety_review"
        if expected_case.expected_human_confirmation_required:
            return "draft"
        return "query"

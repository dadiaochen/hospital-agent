"""Unified patient-facing graph with Supervisor-owned business execution.

The graph keeps one stable service boundary, but the default executor is now
``SupervisorBusinessWorkflow``.  That workflow creates fresh TriageAgent,
MedicationAgent and ReportAgent instances for each run.  The Supervisor
selects and executes those Agents; every database, RAG and Provider access is
still forced through Tool Registry, while Safety and confirmation remain fixed
governance stages.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import (
    EvalRuntimeOptions,
)
from app.agent.supervised_workflow import SupervisorBusinessWorkflow
from app.schemas.request_scope import ScopeAction, ScopeDecision
from app.schemas.business import BusinessDomain, ProviderMode
from app.safety.request_scope import RequestScopeGuard


class _ProductWorkflow(Protocol):
    def invoke(
        self,
        *,
        run_id: str,
        task_id: str,
        user_id: str,
        member_id: str,
        business_domain: BusinessDomain,
        user_input: str,
        input_payload: dict[str, Any] | None = None,
        provider_mode: ProviderMode = "mock",
        human_confirmation_granted: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...

    def resume_confirmation(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        human_confirmation_granted: bool = True,
    ) -> dict[str, Any]: ...

    def resume_clarification(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        user_input: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


class UnifiedHealthGraphState(TypedDict, total=False):
    operation: str
    run_id: str
    task_id: str
    user_id: str
    member_id: str
    business_domain: BusinessDomain
    user_input: str
    input_payload: dict[str, Any]
    provider_mode: ProviderMode
    human_confirmation_granted: bool
    idempotency_key: str
    resume_state: dict[str, Any]
    orchestration_run: dict[str, Any]
    business_state: dict[str, Any]
    scope_decision: dict[str, Any]


_UNIFIED_NODES = (
    "unified_request_scope",
    "unified_complexity_router",
    "unified_planner",
    "unified_supervisor",
    "unified_domain_agents",
    "unified_business_graph",
)


class UnifiedHealthGraph:
    """Run the patient-facing task through one stable graph boundary.

    The class intentionally keeps the same ``invoke`` and
    ``resume_confirmation`` signatures as the previous product workflow, so
    the service layer does not need to know which graph implementation is
    active.  The business graph remains the owner of database and Tool calls.
    """

    def __init__(
        self,
        db: Session | None = None,
        *,
        product_workflow: _ProductWorkflow | None = None,
        supervisor: DeterministicBoundedSupervisor | None = None,
        runtime_options: EvalRuntimeOptions | None = None,
        scope_guard: RequestScopeGuard | None = None,
    ) -> None:
        if product_workflow is None and db is None:
            raise ValueError("db or product_workflow is required")
        self.supervisor = supervisor or DeterministicBoundedSupervisor()
        self.runtime_options = runtime_options or EvalRuntimeOptions()
        self.scope_guard = scope_guard or RequestScopeGuard()
        self.product_workflow = product_workflow or SupervisorBusinessWorkflow(
            cast(Session, db),
            supervisor=self.supervisor,
            runtime_options=self.runtime_options,
        )
        self.graph = self._build_graph()

    def close(self) -> None:
        self.product_workflow.close()

    def invoke(
        self,
        *,
        run_id: str,
        task_id: str,
        user_id: str,
        member_id: str,
        business_domain: BusinessDomain,
        user_input: str,
        input_payload: dict[str, Any] | None = None,
        provider_mode: ProviderMode = "mock",
        human_confirmation_granted: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        state = UnifiedHealthGraphState(
            operation="invoke",
            run_id=run_id,
            task_id=task_id,
            user_id=user_id,
            member_id=member_id,
            business_domain=business_domain,
            user_input=user_input,
            input_payload=dict(input_payload or {}),
            provider_mode=provider_mode,
            human_confirmation_granted=human_confirmation_granted,
            idempotency_key=idempotency_key or f"run:{run_id}",
        )
        return self._business_state(self.graph.invoke(state))

    def resume_confirmation(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        human_confirmation_granted: bool = True,
    ) -> dict[str, Any]:
        resume_state = dict(state)
        request_state = UnifiedHealthGraphState(
            operation="resume_confirmation",
            run_id=run_id,
            task_id=str(resume_state["task_id"]),
            user_id=str(resume_state["user_id"]),
            member_id=str(resume_state["member_id"]),
            business_domain=cast(BusinessDomain, resume_state["business_domain"]),
            user_input=str(resume_state.get("user_input") or "business task"),
            input_payload=dict(resume_state.get("input_payload") or {}),
            provider_mode=cast(
                ProviderMode, resume_state.get("provider_mode", "mock")
            ),
            human_confirmation_granted=human_confirmation_granted,
            idempotency_key=str(resume_state.get("idempotency_key") or ""),
            resume_state=resume_state,
        )
        return self._business_state(self.graph.invoke(request_state))

    def resume_clarification(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        user_input: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        resume_state = dict(state)
        request_state = UnifiedHealthGraphState(
            operation="resume_clarification",
            run_id=run_id,
            task_id=str(resume_state["task_id"]),
            user_id=str(resume_state["user_id"]),
            member_id=str(resume_state["member_id"]),
            business_domain=cast(BusinessDomain, resume_state["business_domain"]),
            user_input=user_input,
            input_payload=dict(input_payload),
            provider_mode=cast(
                ProviderMode, resume_state.get("provider_mode", "mock")
            ),
            human_confirmation_granted=False,
            idempotency_key=str(resume_state.get("idempotency_key") or ""),
            resume_state=resume_state,
        )
        return self._business_state(self.graph.invoke(request_state))

    def _build_graph(self):
        graph = StateGraph(UnifiedHealthGraphState)
        graph.add_node("request_scope_guard", self._request_scope_guard_node)
        graph.add_node("supervised_execution", self._business_graph_node)
        graph.add_node("scope_terminal", self._scope_terminal_node)
        graph.add_edge(START, "request_scope_guard")
        graph.add_conditional_edges(
            "request_scope_guard",
            self._route_after_scope_guard,
            {"execute": "supervised_execution", "terminal": "scope_terminal"},
        )
        graph.add_edge("supervised_execution", END)
        graph.add_edge("scope_terminal", END)
        return graph.compile()

    def _request_scope_guard_node(
        self,
        state: UnifiedHealthGraphState,
    ) -> dict[str, Any]:
        decision = self.scope_guard.evaluate(state["user_input"])
        return {"scope_decision": decision.model_dump(mode="json")}

    @staticmethod
    def _route_after_scope_guard(state: UnifiedHealthGraphState) -> str:
        raw_decision = state.get("scope_decision") or {}
        action = raw_decision.get("action") if isinstance(raw_decision, Mapping) else None
        return "execute" if action == ScopeAction.ALLOW.value else "terminal"

    def _business_graph_node(
        self,
        state: UnifiedHealthGraphState,
    ) -> dict[str, Any]:
        if state.get("operation") == "resume_confirmation":
            business_state = self.product_workflow.resume_confirmation(
                dict(state["resume_state"]),
                run_id=state["run_id"],
                human_confirmation_granted=state["human_confirmation_granted"],
            )
        elif state.get("operation") == "resume_clarification":
            business_state = self.product_workflow.resume_clarification(
                dict(state["resume_state"]),
                run_id=state["run_id"],
                user_input=state["user_input"],
                input_payload=dict(state.get("input_payload") or {}),
            )
        else:
            business_state = self.product_workflow.invoke(
                run_id=state["run_id"],
                task_id=state["task_id"],
                user_id=state["user_id"],
                member_id=state["member_id"],
                business_domain=state["business_domain"],
                user_input=state["user_input"],
                input_payload=state.get("input_payload"),
                provider_mode=state.get("provider_mode", "mock"),
                human_confirmation_granted=state.get(
                    "human_confirmation_granted", False
                ),
                idempotency_key=state.get("idempotency_key"),
            )

        return {"business_state": self._annotate_business_state(business_state, state)}

    def _scope_terminal_node(
        self,
        state: UnifiedHealthGraphState,
    ) -> dict[str, Any]:
        decision = ScopeDecision.model_validate(state.get("scope_decision") or {})
        if decision.action == ScopeAction.REJECT_OFF_TOPIC:
            status = "blocked"
            final_answer = (
                "我目前只处理家庭健康相关事项，例如症状整理、用药、复诊准备或检查报告解读。"
            )
        else:
            status = "needs_clarification"
            final_answer = (
                "可以具体描述一下你的健康问题吗？例如症状、用药、复诊或检查报告。"
            )
        business_state = {
            "run_id": state["run_id"],
            "task_id": state["task_id"],
            "user_id": state["user_id"],
            "member_id": state["member_id"],
            "business_domain": state["business_domain"],
            "intent": state["business_domain"],
            "user_goal": state["user_input"],
            "user_input": state["user_input"],
            "input_payload": dict(state.get("input_payload") or {}),
            "provider_mode": state.get("provider_mode", "mock"),
            "human_confirmation_granted": False,
            "idempotency_key": state.get("idempotency_key", f"run:{state['run_id']}"),
            "status": status,
            "final_answer": final_answer,
            "final_claims": [],
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "model_call_trace": {},
            "degraded": False,
            "errors": [f"scope_guard:{decision.reason_code}"],
            "confirmation_request": {},
            "confirmation_result": {},
            "confirmation_state": "NONE",
            "confirmation_scope": {},
            "confirmation_draft": {},
            "safety_decisions": [],
            "final_output_safety": {},
            "scope_decision": decision.model_dump(mode="json"),
            "visited_nodes": ["unified_request_scope", "unified_scope_terminal"],
        }
        return {"business_state": self._annotate_business_state(business_state, state)}

    def _annotate_business_state(
        self,
        business_state: Mapping[str, Any],
        state: UnifiedHealthGraphState,
    ) -> dict[str, Any]:
        result = dict(business_state)
        if state.get("scope_decision"):
            result["scope_decision"] = dict(state["scope_decision"])
        orchestration = dict(result.get("orchestration_run") or {})
        result["unified_graph_version"] = "4d-b3-supervisor-execution"
        result["unified_visited_nodes"] = list(self._unified_nodes(orchestration))
        result["visited_nodes"] = list(
            dict.fromkeys(
                [
                    *self._unified_nodes(orchestration),
                    *list(result.get("visited_nodes", [])),
                ]
            )
        )
        return result

    @staticmethod
    def _unified_nodes(orchestration: Mapping[str, Any]) -> tuple[str, ...]:
        if not orchestration:
            return ("unified_request_scope",)
        nodes = [
            "unified_request_scope",
            "unified_complexity_router",
        ]
        if orchestration.get("plan") is not None:
            nodes.append("unified_planner")
        if orchestration:
            nodes.append("unified_supervisor")
        roles = [
            str(item.get("agent_role"))
            for item in orchestration.get("results", [])
            if isinstance(item, Mapping) and item.get("agent_role")
        ]
        if roles:
            nodes.append("unified_domain_agents")
        nodes.append("unified_supervised_execution")
        return tuple(dict.fromkeys(nodes))

    @staticmethod
    def _business_state(state: Mapping[str, Any]) -> dict[str, Any]:
        business_state = state.get("business_state")
        if not isinstance(business_state, Mapping):
            raise RuntimeError("UnifiedHealthGraph did not produce business state")
        return dict(business_state)


__all__ = ["UnifiedHealthGraph", "UnifiedHealthGraphState"]

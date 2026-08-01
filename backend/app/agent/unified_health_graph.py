"""Unified patient-facing graph for the 4D-B2 orchestration migration.

The project already has two useful pieces:

* ``DeterministicBoundedSupervisor`` proves the Router/Planner/domain-agent
  contract without touching business data.
* ``FamilyHealthProductWorkflow`` performs the real local business work,
  including Tool Registry calls, confirmation state transitions, output safety,
  and frozen artifacts.

This graph is the migration boundary between them.  It makes the orchestration
kernel part of the patient-facing run and records its result in the same frozen
state, while keeping business data access inside the existing product graph.
4D-B2.2 extends the orchestration kernel with bounded read-only DAG execution;
the business graph still owns side effects and keeps them serial.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import (
    ComplexityRoutingRequest,
    EvalRuntimeOptions,
    OrchestrationRunResult,
)
from app.agent.product_workflow import FamilyHealthProductWorkflow
from app.schemas.business import BusinessDomain, ProviderMode


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
    ) -> None:
        if product_workflow is None and db is None:
            raise ValueError("db or product_workflow is required")
        self.product_workflow = product_workflow or FamilyHealthProductWorkflow(
            cast(Session, db)
        )
        self.supervisor = supervisor or DeterministicBoundedSupervisor()
        self.runtime_options = runtime_options or EvalRuntimeOptions()
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

    def _build_graph(self):
        graph = StateGraph(UnifiedHealthGraphState)
        graph.add_node("orchestration", self._orchestration_node)
        graph.add_node("business_graph", self._business_graph_node)
        graph.add_edge(START, "orchestration")
        graph.add_edge("orchestration", "business_graph")
        graph.add_edge("business_graph", END)
        return graph.compile()

    def _orchestration_node(
        self,
        state: UnifiedHealthGraphState,
    ) -> dict[str, Any]:
        request = ComplexityRoutingRequest(
            task_id=state["task_id"],
            user_id=state["user_id"],
            member_id=state["member_id"],
            user_input=state["user_input"],
            intent=state["business_domain"],
        )
        result = self.supervisor.run(request, runtime_options=self.runtime_options)
        return {"orchestration_run": result.model_dump(mode="json")}

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

        result = dict(business_state)
        orchestration = dict(state["orchestration_run"])
        result["orchestration_run"] = orchestration
        result["unified_graph_version"] = "4d-b2.2"
        result["unified_visited_nodes"] = list(self._unified_nodes(orchestration))
        result["visited_nodes"] = [
            *self._unified_nodes(orchestration),
            *list(result.get("visited_nodes", [])),
        ]
        return {"business_state": result}

    @staticmethod
    def _unified_nodes(orchestration: Mapping[str, Any]) -> tuple[str, ...]:
        nodes = [
            "unified_request_scope",
            "unified_complexity_router",
        ]
        if orchestration.get("plan") is not None:
            nodes.extend(("unified_planner", "unified_supervisor"))
        roles = [
            str(item.get("agent_role"))
            for item in orchestration.get("results", [])
            if isinstance(item, Mapping) and item.get("agent_role")
        ]
        if roles:
            nodes.append("unified_domain_agents")
        nodes.append("unified_business_graph")
        return tuple(dict.fromkeys(nodes))

    @staticmethod
    def _business_state(state: Mapping[str, Any]) -> dict[str, Any]:
        business_state = state.get("business_state")
        if not isinstance(business_state, Mapping):
            raise RuntimeError("UnifiedHealthGraph did not produce business state")
        return dict(business_state)


__all__ = ["UnifiedHealthGraph", "UnifiedHealthGraphState"]

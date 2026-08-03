"""Patient-facing workflow whose business execution is owned by Supervisor.

``FamilyHealthProductWorkflow`` remains available as a compatibility graph for
older isolated tests.  This class owns the same safety, confirmation, Tool
Registry and Model Gateway boundaries, but it does not call the old
``preconsultation``/``chronic_care``/``health_record`` business nodes.  It
creates fresh runtime domain Agents and lets the bounded Supervisor execute
the selected roles.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import (
    ComplexityRoutingRequest,
    DomainAgentRole,
    EvalRuntimeOptions,
    OrchestrationRunResult,
)
from app.agent.product_workflow import FamilyHealthProductWorkflow, ProductWorkflowState
from app.agent.runtime_domain_agents import (
    RuntimeAgentContext,
    build_runtime_domain_agent_registry,
)
from app.agent.safety_confirmation import (
    ConfirmationTransitionRequest,
    ConfirmationState,
)
from app.agent.context_schemas import ToolEvidenceRef
from app.schemas.business import BusinessDomain, ProviderMode
from app.tools.tool_schemas import ToolResult


_PRIMARY_ROLE_BY_DOMAIN: dict[BusinessDomain, DomainAgentRole] = {
    "preconsultation": "TriageAgent",
    "chronic_care": "MedicationAgent",
    "health_record": "ReportAgent",
}


class SupervisorAgentRuntime(RuntimeAgentContext):
    """Per-run capability object passed to exactly one Agent set."""

    def __init__(
        self,
        workflow: "SupervisorBusinessWorkflow",
        state: ProductWorkflowState,
        *,
        is_confirmation_run: bool,
    ) -> None:
        self.workflow = workflow
        self.state = state
        self.run_id = state["run_id"]
        self.task_id = state["task_id"]
        self.user_id = state["user_id"]
        self.member_id = state["member_id"]
        self.business_domain = state["business_domain"]
        self.input_payload = dict(state.get("input_payload", {}))
        self.human_confirmation_granted = bool(
            state.get("human_confirmation_granted", False)
        )
        self.is_confirmation_run = is_confirmation_run
        self.primary_role: DomainAgentRole = _PRIMARY_ROLE_BY_DOMAIN[
            self.business_domain
        ]
        self._calls: list[ToolResult] = []

    def trace_cursor(self) -> int:
        return len(self._calls)

    def call_tool(
        self,
        *,
        agent_role: DomainAgentRole,
        tool_name: str,
        payload: dict[str, Any],
        step_id: str,
        allowed_tools: tuple[str, ...],
    ) -> ToolResult:
        if not step_id or tool_name not in set(allowed_tools):
            result = ToolResult.failure(
                tool_name=tool_name,
                error_type="tool_not_allowed_by_plan",
                error_message=(
                    f"tool {tool_name!r} is not allowed by plan step {step_id!r}"
                ),
                fallback_action="reject_plan_tool",
                latency_ms=0,
                run_id=self.run_id,
                agent_role=agent_role,
                member_id=self.member_id,
                tool_input=payload,
                permission_scope="plan_step",
            )
            self._calls.append(result)
            return result

        result = self.workflow._call(
            self.state,
            tool_name=tool_name,
            agent_role=agent_role,
            payload=payload,
        )
        self._calls.append(result)
        return result

    def tool_names_since(self, cursor: int) -> tuple[str, ...]:
        return tuple(result.tool_name for result in self._calls[cursor:])

    def evidence_refs_since(self, cursor: int) -> tuple[ToolEvidenceRef, ...]:
        refs: list[ToolEvidenceRef] = []
        for offset, result in enumerate(self._calls[cursor:], start=cursor + 1):
            for source in result.evidence_refs:
                refs.append(
                    ToolEvidenceRef(
                        source_id=source.source_id,
                        run_id=self.run_id,
                        member_id=self.member_id,
                        tool_name=result.tool_name,
                        tool_call_id=f"{self.run_id}:tool:{offset}",
                        success=result.success,
                        schema_valid=result.schema_valid,
                    )
                )
        return tuple(refs)

    def output_since(self, cursor: int) -> dict[str, Any]:
        calls = self._calls[cursor:]
        return {
            "tool_output_count": len(calls),
            "tool_source_ids": [
                source.source_id
                for result in calls
                for source in result.evidence_refs
            ],
        }

    def should_prepare_confirmation(self, agent_role: DomainAgentRole) -> bool:
        """Only the primary task role creates the single task draft.

        A cross-domain run may collect evidence from two Agents, but the
        current task checkpoint has one confirmation scope.  The primary role
        selected from the requested business domain owns that scope; other
        Agents still execute their read-only work and return evidence.
        """

        return (
            not self.is_confirmation_run
            and agent_role == self.primary_role
            and not self.state.get("confirmation_request")
        )

    def prepare_confirmation(
        self,
        *,
        agent_role: DomainAgentRole,
        action_type: str,
        tool_name: str,
        summary: str,
        payload: dict[str, Any],
    ) -> None:
        self.workflow._set_confirmation(
            self.state,
            action_type=cast(Any, action_type),
            tool_name=tool_name,
            agent_role=agent_role,
            summary=summary,
            payload=payload,
        )
        self.state["final_answer"] = {
            "refill_request": "已整理续方材料，生成续方申请草稿；提交前需要你的确认。",
            "pharmacy_option": "已查询购药候选方案，生成购药草稿；下单前需要你的确认。",
            "reminder_create": "已生成用药提醒草稿；创建前需要你的确认。",
            "consultation_request": "已整理复诊材料，生成复诊申请草稿；提交前需要你的确认。",
            "health_record": "已完成报告内容整理和来源检索，生成健康记录草稿；保存前需要你的确认。",
        }.get(action_type, "已生成待确认草稿；执行前需要你的确认。")

    def is_confirmation_target(self, agent_role: DomainAgentRole) -> bool:
        request = self.state.get("confirmation_request")
        return isinstance(request, dict) and request.get("agent_role") == agent_role

    def execute_confirmed_action(self, agent_role: DomainAgentRole) -> bool:
        """Run the protected action from the Agent selected by Supervisor."""

        if not self.is_confirmation_target(agent_role):
            return True
        request = self.state.get("confirmation_request")
        if not isinstance(request, dict):
            return False
        scope = self.workflow._scope_from_state(self.state)
        if scope is None:
            self.state["status"] = "blocked"
            self.state["confirmation_state"] = "BLOCKED"
            self.state.setdefault("errors", []).append("confirmation_scope_invalid")
            return False

        decision = self.workflow.safety_guard.action(
            message=" ".join(
                [
                    self.state.get("user_input", ""),
                    str(request.get("summary", "")),
                ]
            ),
            user_id=self.user_id,
            member_id=self.member_id,
            expected_user_id=scope.user_id,
            expected_member_id=scope.member_id,
            confirmation_state=self.state.get("confirmation_state", "DRAFT"),
            human_confirmation_present=True,
        )
        self.workflow._record_safety_decision(self.state, decision)
        transition = self.workflow.confirmation_machine.transition(
            ConfirmationTransitionRequest(
                current_state=cast(ConfirmationState, self.state.get("confirmation_state", "DRAFT")),
                action="confirm",
                scope=scope,
                current_scope=scope,
                actor_user_id=self.user_id,
                actor_member_id=self.member_id,
                human_confirmation_present=True,
                safety_decision=decision,
            )
        )
        if not transition.allowed:
            self.state["status"] = "blocked"
            self.state["confirmation_state"] = transition.state
            self.state.setdefault("errors", []).append(
                transition.failure_code or "confirmation_blocked"
            )
            return False

        self.state["confirmation_state"] = transition.state
        self.workflow._confirm(self.state)
        return self.state.get("status") == "completed"

    def set_final_answer(self, text: str) -> None:
        self.state["final_answer"] = text


class SupervisorBusinessWorkflow(FamilyHealthProductWorkflow):
    """Execute real business Agents through the bounded Supervisor."""

    def __init__(
        self,
        db,
        *,
        supervisor: DeterministicBoundedSupervisor | None = None,
        runtime_options: EvalRuntimeOptions | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(db, **kwargs)
        self.supervisor_template = supervisor or DeterministicBoundedSupervisor()
        self.runtime_options = runtime_options or EvalRuntimeOptions(
            execution_mode="serial"
        )

    def _runtime_supervisor(
        self,
        runtime: SupervisorAgentRuntime,
    ) -> DeterministicBoundedSupervisor:
        template = self.supervisor_template
        return DeterministicBoundedSupervisor(
            router=template.router,
            planner=template.planner,
            agents=build_runtime_domain_agent_registry(runtime),
            max_supervisor_steps=template.max_supervisor_steps,
            max_role_calls=template.max_role_calls,
            max_parallelism=template.max_parallelism,
            execution_mode="serial",
            context_mode=template.context_mode,
        )

    @staticmethod
    def _initial_state(
        *,
        run_id: str,
        task_id: str,
        user_id: str,
        member_id: str,
        business_domain: BusinessDomain,
        user_input: str,
        input_payload: dict[str, Any] | None,
        provider_mode: ProviderMode,
        human_confirmation_granted: bool,
        idempotency_key: str | None,
    ) -> ProductWorkflowState:
        return {
            "run_id": run_id,
            "task_id": task_id,
            "user_id": user_id,
            "member_id": member_id,
            "business_domain": business_domain,
            "intent": business_domain,
            "user_goal": user_input,
            "user_input": user_input,
            "input_payload": dict(input_payload or {}),
            "provider_mode": provider_mode,
            "human_confirmation_granted": human_confirmation_granted,
            "idempotency_key": idempotency_key or str(uuid4()),
            "status": "created",
            "final_answer": "",
            "final_claims": [],
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "model_call_trace": {},
            "degraded": False,
            "errors": [],
            "confirmation_request": {},
            "confirmation_result": {},
            "confirmation_state": "NONE",
            "confirmation_scope": {},
            "confirmation_draft": {},
            "safety_decisions": [],
            "final_output_safety": {},
            "visited_nodes": [],
        }

    @staticmethod
    def _primary_role(
        business_domain: BusinessDomain,
        route: Any,
    ) -> DomainAgentRole:
        if route.target_role is not None:
            return route.target_role
        preferred = _PRIMARY_ROLE_BY_DOMAIN[business_domain]
        if preferred in route.target_roles:
            return preferred
        return route.target_roles[0]

    def _run_supervisor(
        self,
        state: ProductWorkflowState,
        *,
        is_confirmation_run: bool,
    ) -> OrchestrationRunResult:
        request = ComplexityRoutingRequest(
            task_id=state["task_id"],
            user_id=state["user_id"],
            member_id=state["member_id"],
            user_input=state["user_input"],
            intent=state["business_domain"],
        )
        preview_route = self.supervisor_template.router.route(request)
        runtime = SupervisorAgentRuntime(
            self,
            state,
            is_confirmation_run=is_confirmation_run,
        )
        runtime.primary_role = self._primary_role(
            state["business_domain"], preview_route
        )
        supervisor = self._runtime_supervisor(runtime)
        result = supervisor.run(
            request,
            runtime_options=self.runtime_options.model_copy(
                update={"execution_mode": "serial"}
            ),
        )
        state["intent"] = result.route.intent
        state["orchestration_run"] = result.model_dump(mode="json")
        state["visited_nodes"].extend(
            [
                "supervisor",
                *[
                    f"domain_agent:{item.agent_role}"
                    for item in result.results
                ],
            ]
        )
        return result

    @staticmethod
    def _apply_orchestration_failure(
        state: ProductWorkflowState,
        result: OrchestrationRunResult,
    ) -> None:
        failed = next(
            (item for item in reversed(result.results) if item.status in {"failed", "blocked"}),
            None,
        )
        clarification = next(
            (item for item in result.results if item.status == "needs_clarification"),
            None,
        )
        if clarification is not None:
            state["status"] = "needs_clarification"
            state["final_answer"] = (
                "请补充以下信息后再继续："
                + "、".join(clarification.missing_information)
            )
            return
        if failed is not None or not result.completed:
            state["status"] = "failed"
            state["degraded"] = True
            reason = (
                failed.failure_reason
                if failed is not None
                else result.termination_reason
            )
            state.setdefault("errors", []).append(str(reason))
            state["final_answer"] = (
                "当前业务 Agent 未能完成信息整理，暂未生成可执行草稿，请稍后重试或转人工处理。"
            )

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
    ) -> ProductWorkflowState:
        state = self._initial_state(
            run_id=run_id,
            task_id=task_id,
            user_id=user_id,
            member_id=member_id,
            business_domain=business_domain,
            user_input=user_input,
            input_payload=input_payload,
            provider_mode=provider_mode,
            human_confirmation_granted=human_confirmation_granted,
            idempotency_key=idempotency_key,
        )
        self._safety_entry(state)
        if state.get("status") == "blocked":
            self._finalize(state)
            return state

        result = self._run_supervisor(state, is_confirmation_run=False)
        self._apply_orchestration_failure(state, result)
        if state.get("status") not in {"failed", "needs_clarification"}:
            self._safety_review(state)
        self._finalize(state)
        return state

    def resume_confirmation(
        self,
        state: ProductWorkflowState,
        *,
        run_id: str,
        human_confirmation_granted: bool = True,
    ) -> ProductWorkflowState:
        resumed = cast(ProductWorkflowState, dict(state))
        resumed["run_id"] = run_id
        resumed["human_confirmation_granted"] = human_confirmation_granted
        resumed["status"] = "running"
        resumed["final_answer"] = ""
        resumed["final_claims"] = []
        resumed["errors"] = []
        resumed["tool_calls"] = []
        resumed["provider_calls"] = []
        resumed["model_call_trace"] = {}
        resumed["visited_nodes"] = []
        resumed["confirmation_result"] = {}
        if not human_confirmation_granted:
            resumed["status"] = "needs_confirmation"
            resumed["need_human_confirmation"] = True
            self._finalize(resumed)
            return resumed

        decision = self.safety_guard.request(
            message=resumed.get("user_input", ""),
            member_id=resumed["member_id"],
        )
        self._record_safety_decision(resumed, decision)
        if decision.blocked:
            resumed["status"] = "blocked"
            resumed["confirmation_state"] = "BLOCKED"
            resumed["final_answer"] = decision.message
            self._finalize(resumed)
            return resumed

        result = self._run_supervisor(resumed, is_confirmation_run=True)
        self._apply_orchestration_failure(resumed, result)
        self._finalize(resumed)
        return resumed


__all__ = ["SupervisorAgentRuntime", "SupervisorBusinessWorkflow"]

"""Pydantic contracts for the final 4B routing and orchestration boundary.

These contracts deliberately sit beside the legacy workflow schemas.  The
legacy graph remains runnable while 4B task five freezes the new boundary;
task six will consume these models from the bounded Supervisor workflow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import (
    ContractModel,
    Intent,
    NonEmptyStr,
    RAGSourceRef,
    ToolEvidenceRef,
)
from app.agent.safety import SafetyDecision, SafetyStage


DomainAgentRole = Literal["TriageAgent", "MedicationAgent", "ReportAgent"]
RouteMode = Literal["simple_single_domain", "complex_cross_domain"]
RouteReasonCode = Literal[
    "single_domain_signal",
    "ambiguous_input",
    "multiple_domain_signals",
    "safety_sensitive_single_domain",
]
AgentTaskStatus = Literal[
    "completed",
    "degraded",
    "needs_clarification",
    "blocked",
    "failed",
]
SupervisorAction = Literal["call_role", "retry", "degrade", "finish", "stop"]


class ComplexityRoutingRequest(ContractModel):
    """The minimum identity and text required by the deterministic Router."""

    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    user_input: NonEmptyStr
    intent: Intent | None = None


class ComplexityRoute(ContractModel):
    """A frozen routing decision; it never contains raw conversation history."""

    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    route_mode: RouteMode
    intent: Intent
    target_role: DomainAgentRole | None = None
    target_roles: tuple[DomainAgentRole, ...] = Field(
        min_length=1,
        max_length=3,
    )
    reason_code: RouteReasonCode
    matched_signals: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    required_capabilities: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    requires_planner: bool

    @model_validator(mode="after")
    def validate_route_shape(self) -> "ComplexityRoute":
        if self.route_mode == "simple_single_domain":
            if self.target_role is None or len(self.target_roles) != 1:
                raise ValueError(
                    "simple routes require exactly one target_role and target_roles entry"
                )
            if self.target_roles[0] != self.target_role:
                raise ValueError("target_role must match the only target_roles entry")
            if self.requires_planner:
                raise ValueError("simple routes cannot require a planner")
        else:
            if self.target_role is not None:
                raise ValueError("complex routes do not have one target_role")
            if len(self.target_roles) < 2:
                raise ValueError("complex routes require at least two target roles")
            if not self.requires_planner:
                raise ValueError("complex routes must require a planner")

        if self.reason_code == "multiple_domain_signals" and len(self.target_roles) < 2:
            raise ValueError("multiple-domain reason requires multiple target roles")
        return self


class PlanStep(ContractModel):
    """One bounded business step selected from the three final domain roles."""

    step_id: NonEmptyStr
    role: DomainAgentRole
    objective: NonEmptyStr
    dependencies: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def reject_self_dependency(self) -> "PlanStep":
        if self.step_id in self.dependencies:
            raise ValueError("a plan step cannot depend on itself")
        return self


# ``TaskStep`` is the public terminology used in the design documents.  Keep
# ``PlanStep`` as the implementation name because it reads naturally inside
# ``TaskPlan`` and is already used by the first task-five tests.
TaskStep = PlanStep


class TaskPlan(ContractModel):
    """A one-shot plan for a complex request, capped at three steps."""

    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    intent: Intent
    steps: tuple[PlanStep, ...] = Field(min_length=1, max_length=3)
    max_steps: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def validate_bounded_dependencies(self) -> "TaskPlan":
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("task plan step_id values must be unique")
        if len(self.steps) > self.max_steps:
            raise ValueError("task plan exceeds max_steps")

        completed_step_ids: set[str] = set()
        for step in self.steps:
            unknown = set(step.dependencies) - set(completed_step_ids)
            if unknown:
                raise ValueError(
                    "step dependencies must reference an earlier step: "
                    + ", ".join(sorted(unknown))
                )
            completed_step_ids.add(step.step_id)
        return self


class AgentTaskResult(ContractModel):
    """The only result shape a domain Agent may return to orchestration."""

    task_id: NonEmptyStr
    member_id: NonEmptyStr
    agent_role: DomainAgentRole
    step_id: NonEmptyStr | None = None
    status: AgentTaskStatus
    facts: dict[str, object] = Field(default_factory=dict)
    source_refs: tuple[ToolEvidenceRef | RAGSourceRef, ...] = Field(
        default_factory=tuple
    )
    tool_calls: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    missing_information: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    requested_confirmation: bool = False
    failure_reason: NonEmptyStr | None = None
    retryable: bool = False
    attempt: int = Field(default=1, ge=1, le=3)

    @model_validator(mode="after")
    def validate_result_state(self) -> "AgentTaskResult":
        if self.status in {"blocked", "failed"} and self.failure_reason is None:
            raise ValueError(
                "blocked or failed AgentTaskResult requires failure_reason"
            )
        if self.status == "needs_clarification" and not self.missing_information:
            raise ValueError(
                "needs_clarification AgentTaskResult requires missing_information"
            )
        if self.retryable and self.status not in {"blocked", "failed"}:
            raise ValueError("only blocked or failed results can be retryable")
        for source in self.source_refs:
            source_member_id = getattr(source, "member_id", None)
            if source_member_id is not None and source_member_id != self.member_id:
                raise ValueError("source_refs must belong to the result member")
        return self


class OrchestrationRunResult(ContractModel):
    """Frozen in-memory result of one task-six orchestration run.

    This is not a database record.  It makes the boundary between Router,
    Planner, Supervisor, and the later governance stages explicit while the
    runtime is still deterministic and side-effect free.
    """

    request: ComplexityRoutingRequest
    route: ComplexityRoute
    plan: TaskPlan | None = None
    results: tuple[AgentTaskResult, ...] = Field(default_factory=tuple)
    decisions: tuple[SupervisorDecision, ...] = Field(default_factory=tuple)
    completed: bool
    termination_reason: NonEmptyStr
    steps_executed: int = Field(default=0, ge=0, le=3)
    used_planner: bool = False
    used_supervisor: bool = False

    @model_validator(mode="after")
    def validate_run_shape(self) -> "OrchestrationRunResult":
        if self.route.task_id != self.request.task_id:
            raise ValueError("route task_id must match request")
        if self.route.user_id != self.request.user_id:
            raise ValueError("route user_id must match request")
        if self.route.member_id != self.request.member_id:
            raise ValueError("route member_id must match request")
        if self.steps_executed != len(self.results):
            raise ValueError("steps_executed must match result invocation count")
        for result in self.results:
            if result.task_id != self.request.task_id:
                raise ValueError("AgentTaskResult task_id must match request")
            if result.member_id != self.request.member_id:
                raise ValueError("AgentTaskResult member_id must match request")

        if self.route.route_mode == "simple_single_domain":
            if self.plan is not None:
                raise ValueError("simple routes cannot carry a TaskPlan")
            if self.used_planner or self.used_supervisor:
                raise ValueError("simple routes cannot use Planner or Supervisor")
            if len(self.results) != 1:
                raise ValueError("simple routes must execute exactly one result")
            if self.results[0].agent_role != self.route.target_role:
                raise ValueError("simple result role must match route target_role")
        else:
            if self.plan is None or not self.used_planner or not self.used_supervisor:
                raise ValueError("complex routes require Planner and Supervisor")
            if self.steps_executed > self.plan.max_steps:
                raise ValueError("complex run exceeds plan max_steps")
            if self.plan.task_id != self.request.task_id:
                raise ValueError("plan task_id must match request")
            if self.plan.user_id != self.request.user_id:
                raise ValueError("plan user_id must match request")
            if self.plan.member_id != self.request.member_id:
                raise ValueError("plan member_id must match request")
            if self.plan.intent != self.route.intent:
                raise ValueError("plan intent must match route intent")
            plan_step_ids = {step.step_id for step in self.plan.steps}
            for result in self.results:
                if result.step_id not in plan_step_ids:
                    raise ValueError("result step_id must belong to the plan")
                if result.agent_role not in self.route.target_roles:
                    raise ValueError("result role must belong to the route")
        return self


class SupervisorDecision(ContractModel):
    """A finite action vocabulary for the future serial Supervisor."""

    action: SupervisorAction
    step_id: NonEmptyStr | None = None
    role: DomainAgentRole | None = None
    reason: NonEmptyStr
    termination_reason: NonEmptyStr | None = None
    retry_count: int = Field(default=0, ge=0)
    max_steps: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> "SupervisorDecision":
        if self.action in {"call_role", "retry"}:
            if self.step_id is None or self.role is None:
                raise ValueError(
                    "call_role and retry decisions require step_id and role"
                )
        if self.action in {"finish", "stop", "degrade"}:
            if self.termination_reason is None:
                raise ValueError(
                    "finish, stop and degrade decisions require termination_reason"
                )
        if self.retry_count >= self.max_steps:
            raise ValueError("retry_count must remain below max_steps")
        return self


class SafetyDecisionBundle(ContractModel):
    """Three fixed governance checkpoints carried by a future graph."""

    request: SafetyDecision
    action: SafetyDecision
    final_output: SafetyDecision

    @model_validator(mode="after")
    def validate_stages(self) -> "SafetyDecisionBundle":
        expected: tuple[tuple[str, SafetyStage], ...] = (
            ("request", "request"),
            ("action", "action"),
            ("final_output", "final_output"),
        )
        for field_name, stage in expected:
            if getattr(self, field_name).stage != stage:
                raise ValueError(f"{field_name} decision must use stage={stage}")
        return self


__all__ = [
    "AgentTaskResult",
    "AgentTaskStatus",
    "ComplexityRoute",
    "ComplexityRoutingRequest",
    "DomainAgentRole",
    "PlanStep",
    "RouteMode",
    "RouteReasonCode",
    "SafetyDecision",
    "SafetyDecisionBundle",
    "SafetyStage",
    "SupervisorAction",
    "SupervisorDecision",
    "OrchestrationRunResult",
    "TaskStep",
    "TaskPlan",
]

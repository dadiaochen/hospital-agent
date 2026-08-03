"""Deterministic domain-agent boundary for 4B task six.

The three classes in this module do not read medical data and do not call a
provider.  They turn a bounded step into a structured workflow result.  The
next task will connect the declared capabilities to Tool Registry and
Provider adapters; until then, returning no invented facts is intentional.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.agent.orchestration_schemas import (
    AgentTaskResult,
    ContextMode,
    ComplexityRoute,
    DomainAgentRole,
    PlanStep,
)


SummaryText = Annotated[str, Field(min_length=1, max_length=2000)]


# These are capability allowlists, not an execution registry.  A later
# Tool/Provider task must still register each callable and enforce permission
# and member scope before anything is executed.
ROLE_ALLOWED_TOOLS: dict[DomainAgentRole, tuple[str, ...]] = {
    "TriageAgent": (
        "query_health_profile",
        "search_safety_knowledge",
        "hospital_list_departments",
        "hospital_list_slots",
        "consultation_prepare_draft",
        "search_business_knowledge",
        "create_confirmation_draft",
    ),
    "MedicationAgent": (
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
        "search_business_knowledge",
        "consultation_prepare_draft",
        "pharmacy_search_inventory",
        "notification_prepare_reminder",
        "create_confirmation_draft",
    ),
    "ReportAgent": (
        "query_health_profile",
        "search_safety_knowledge",
        "parse_medical_document",
        "inspect_medical_image",
        "search_business_knowledge",
        "create_health_record_draft",
    ),
}


class DomainAgentInput(ContractModel):
    """Minimal input visible to one domain Agent for one planned step.

    It deliberately has a summary string rather than a conversation-history
    field.  Prior results are structured and member-scoped, so an Agent cannot
    receive another member's facts by accident.
    """

    route: ComplexityRoute
    step: PlanStep
    user_input_summary: SummaryText
    allowed_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    prior_results: tuple[AgentTaskResult, ...] = Field(default_factory=tuple)
    context_mode: ContextMode = "dependency_only"

    @model_validator(mode="after")
    def validate_agent_scope(self) -> "DomainAgentInput":
        if self.step.role not in self.route.target_roles:
            raise ValueError("step role must be present in the frozen route")
        if (
            self.route.route_mode == "simple_single_domain"
            and self.step.role != self.route.target_role
        ):
            raise ValueError("simple step role must match route target_role")

        allowed = set(ROLE_ALLOWED_TOOLS[self.step.role])
        unknown_tools = set(self.allowed_tools) - allowed
        if unknown_tools:
            raise ValueError(
                "allowed_tools are outside the role allowlist: "
                + ", ".join(sorted(unknown_tools))
            )

        for result in self.prior_results:
            if result.task_id != self.route.task_id:
                raise ValueError("prior result task_id must match the route")
            if result.member_id != self.route.member_id:
                raise ValueError("prior result member_id must match the route")
        if self.context_mode == "all_history" and not self.prior_results:
            # An empty first batch is valid; the field still records that the
            # evaluation baseline was selected without inventing history.
            return self
        return self


class DomainAgent(ABC):
    """Interface consumed by the bounded Supervisor."""

    role: ClassVar[DomainAgentRole]
    allowed_tools: ClassVar[tuple[str, ...]]

    def execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        if agent_input.step.role != self.role:
            raise ValueError(
                f"{self.role} cannot execute {agent_input.step.role} step"
            )
        return self._execute(agent_input)

    @abstractmethod
    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        """Return a schema-validated result without performing side effects."""

    def _result(
        self,
        agent_input: DomainAgentInput,
        *,
        status: str = "completed",
        facts: dict[str, object],
        missing_information: tuple[str, ...] = (),
        requested_confirmation: bool = False,
        failure_reason: str | None = None,
        retryable: bool = False,
        attempt: int = 1,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id=agent_input.route.task_id,
            member_id=agent_input.route.member_id,
            agent_role=self.role,
            step_id=agent_input.step.step_id,
            status=status,
            facts=facts,
            # Task six has no tool/provider execution yet, so no evidence is
            # claimed.  The next task must populate refs from real sources.
            tool_calls=(),
            missing_information=missing_information,
            requested_confirmation=requested_confirmation,
            failure_reason=failure_reason,
            retryable=retryable,
            attempt=attempt,
        )


class TriageAgent(DomainAgent):
    """Structure a pre-consultation or safety-review task without diagnosing."""

    role: ClassVar[DomainAgentRole] = "TriageAgent"
    allowed_tools: ClassVar[tuple[str, ...]] = ROLE_ALLOWED_TOOLS["TriageAgent"]

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        if agent_input.route.reason_code == "ambiguous_input":
            return self._result(
                agent_input,
                status="needs_clarification",
                facts={
                    "workflow_action": "request_clarification",
                    "source_backed_only": True,
                    "medical_claims_generated": False,
                },
                missing_information=("request_goal",),
            )

        return self._result(
            agent_input,
            facts={
                "workflow_action": (
                    "prepare_safety_review"
                    if agent_input.route.intent == "safety_check"
                    else "structure_triage_request"
                ),
                "safety_review_required": agent_input.route.intent == "safety_check",
                "source_backed_only": True,
                "medical_claims_generated": False,
            },
        )


class MedicationAgent(DomainAgent):
    """Prepare a medication workflow while keeping all actions as drafts."""

    role: ClassVar[DomainAgentRole] = "MedicationAgent"
    allowed_tools: ClassVar[tuple[str, ...]] = ROLE_ALLOWED_TOOLS["MedicationAgent"]

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        intent = agent_input.route.intent
        is_action_request = intent in {"refill", "reminder", "pharmacy"}
        return self._result(
            agent_input,
            facts={
                "workflow_action": (
                    "prepare_safety_review"
                    if intent == "safety_check"
                    else "prepare_medication_workflow"
                ),
                "draft_only": is_action_request,
                "requires_source_refs": True,
                "medical_claims_generated": False,
            },
            requested_confirmation=is_action_request,
        )


class ReportAgent(DomainAgent):
    """Structure report work and require source-backed interpretation later."""

    role: ClassVar[DomainAgentRole] = "ReportAgent"
    allowed_tools: ClassVar[tuple[str, ...]] = ROLE_ALLOWED_TOOLS["ReportAgent"]

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        return self._result(
            agent_input,
            facts={
                "workflow_action": "structure_report_task",
                "requires_source_refs": True,
                "medical_claims_generated": False,
            },
        )


def build_domain_agent_registry() -> dict[DomainAgentRole, DomainAgent]:
    """Build a fresh role registry so callers cannot mutate shared state."""

    return {
        "TriageAgent": TriageAgent(),
        "MedicationAgent": MedicationAgent(),
        "ReportAgent": ReportAgent(),
    }


def allowed_tools_for_role(role: DomainAgentRole) -> tuple[str, ...]:
    """Return the immutable capability allowlist for a registered role."""

    return ROLE_ALLOWED_TOOLS[role]


__all__ = [
    "DomainAgent",
    "DomainAgentInput",
    "MedicationAgent",
    "ReportAgent",
    "ROLE_ALLOWED_TOOLS",
    "TriageAgent",
    "allowed_tools_for_role",
    "build_domain_agent_registry",
]

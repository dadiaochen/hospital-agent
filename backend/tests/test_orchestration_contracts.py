from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.orchestration_schemas import (
    AgentTaskResult,
    ComplexityRoute,
    DependencyEdge,
    PlanStep,
    SafetyDecisionBundle,
    SupervisorDecision,
    TaskPlan,
)
from app.agent.safety import SafetyDecision


def test_simple_complexity_route_is_a_direct_single_role_decision() -> None:
    route = ComplexityRoute(
        task_id="task-1",
        user_id="user-1",
        member_id="member-1",
        route_mode="simple_single_domain",
        intent="refill",
        target_role="MedicationAgent",
        target_roles=("MedicationAgent",),
        reason_code="single_domain_signal",
        required_capabilities=("medication_fact_lookup",),
        requires_planner=False,
    )

    assert route.target_role == "MedicationAgent"
    assert route.requires_planner is False


def test_complexity_route_rejects_a_simple_route_with_multiple_roles() -> None:
    with pytest.raises(ValidationError, match="exactly one target_role"):
        ComplexityRoute(
            task_id="task-1",
            user_id="user-1",
            member_id="member-1",
            route_mode="simple_single_domain",
            intent="refill",
            target_role="MedicationAgent",
            target_roles=("MedicationAgent", "ReportAgent"),
            reason_code="single_domain_signal",
            requires_planner=False,
        )


def test_task_plan_requires_dependency_edges_to_match_step_dependencies() -> None:
    plan = TaskPlan(
        task_id="task-2",
        user_id="user-1",
        member_id="member-1",
        intent="health_record",
        steps=(
            PlanStep(
                step_id="report",
                role="ReportAgent",
                objective="Structure the report facts.",
            ),
            PlanStep(
                step_id="triage",
                role="TriageAgent",
                objective="Prepare a sourced follow-up summary.",
                dependencies=("report",),
            ),
        ),
        dependency_edges=(
            DependencyEdge(
                upstream_step_id="report",
                downstream_step_id="triage",
            ),
        ),
    )

    assert len(plan.steps) == 2
    assert plan.max_steps == 3

    with pytest.raises(ValidationError, match="dependency edges must match"):
        TaskPlan(
            task_id="task-3",
            user_id="user-1",
            member_id="member-1",
            intent="health_record",
            steps=(
                PlanStep(
                    step_id="triage",
                    role="TriageAgent",
                    objective="Run before a missing step.",
                    dependencies=("report",),
                ),
                PlanStep(
                    step_id="report",
                    role="ReportAgent",
                    objective="Structure the report facts.",
                ),
            ),
        )


def test_task_plan_cannot_use_an_unregistered_role() -> None:
    with pytest.raises(ValidationError, match="role"):
        PlanStep(
            step_id="profile",
            role="ProfileAgent",
            objective="Read the profile.",
        )


def test_agent_task_result_requires_failure_reason_for_blocked_result() -> None:
    with pytest.raises(ValidationError, match="failure_reason"):
        AgentTaskResult(
            task_id="task-4",
            member_id="member-1",
            agent_role="MedicationAgent",
            status="blocked",
        )

    result = AgentTaskResult(
        task_id="task-4",
        member_id="member-1",
        agent_role="MedicationAgent",
        status="needs_clarification",
        missing_information=("prescription_id",),
    )
    assert result.missing_information == ("prescription_id",)


@pytest.mark.parametrize("action", ["call_role", "retry"])
def test_supervisor_role_actions_require_step_and_role(action: str) -> None:
    with pytest.raises(ValidationError, match="step_id and role"):
        SupervisorDecision(action=action, reason="A bounded decision.")


def test_supervisor_terminal_actions_require_termination_reason() -> None:
    with pytest.raises(ValidationError, match="termination_reason"):
        SupervisorDecision(action="finish", reason="Finished.")

    decision = SupervisorDecision(
        action="stop",
        reason="Safety policy stopped the plan.",
        termination_reason="blocked_by_safety",
    )
    assert decision.action == "stop"


def test_safety_decision_bundle_requires_three_fixed_stages() -> None:
    bundle = SafetyDecisionBundle(
        request=SafetyDecision(stage="request"),
        action=SafetyDecision(
            stage="action",
            requires_human_confirmation=True,
        ),
        final_output=SafetyDecision(stage="final_output"),
    )

    assert bundle.action.outcome == "require_human_confirmation"

    with pytest.raises(ValidationError, match="stage=action"):
        SafetyDecisionBundle(
            request=SafetyDecision(stage="request"),
            action=SafetyDecision(stage="request"),
            final_output=SafetyDecision(stage="final_output"),
        )

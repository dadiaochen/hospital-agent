from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.domain_agents import (
    DomainAgent,
    DomainAgentInput,
    MedicationAgent,
    ReportAgent,
    TriageAgent,
    ROLE_ALLOWED_TOOLS,
    build_domain_agent_registry,
)
from app.agent.orchestration import (
    DeterministicBoundedSupervisor,
    DeterministicTaskPlanner,
)
from app.agent.orchestration_schemas import (
    AgentTaskResult,
    ComplexityRoute,
    ComplexityRoutingRequest,
    PlanStep,
)


def make_request(text: str, *, intent: str | None = None) -> ComplexityRoutingRequest:
    return ComplexityRoutingRequest(
        task_id="task-6",
        user_id="user-1",
        member_id="member-1",
        user_input=text,
        intent=intent,
    )


def test_registry_contains_exactly_three_domain_agents() -> None:
    registry = build_domain_agent_registry()

    assert set(registry) == {"TriageAgent", "MedicationAgent", "ReportAgent"}
    assert isinstance(registry["TriageAgent"], TriageAgent)
    assert isinstance(registry["MedicationAgent"], MedicationAgent)
    assert isinstance(registry["ReportAgent"], ReportAgent)


def test_simple_request_directly_executes_one_domain_agent() -> None:
    run = DeterministicBoundedSupervisor().run(
        make_request("Please prepare a medication refill request.")
    )

    assert run.route.route_mode == "simple_single_domain"
    assert run.route.target_role == "MedicationAgent"
    assert run.plan is None
    assert run.used_planner is False
    assert run.used_supervisor is False
    assert run.completed is True
    assert len(run.results) == 1
    assert run.results[0].facts["medical_claims_generated"] is False
    assert run.decisions == ()


def test_ambiguous_simple_request_returns_structured_clarification() -> None:
    run = DeterministicBoundedSupervisor().run(make_request("I want to ask something."))

    assert run.completed is False
    assert run.termination_reason == "needs_clarification"
    assert run.results[0].status == "needs_clarification"
    assert run.results[0].missing_information == ("request_goal",)


def test_complex_request_uses_one_shot_planner_and_parallel_supervisor() -> None:
    run = DeterministicBoundedSupervisor().run(
        make_request("Please review the report and prepare a medication refill.")
    )

    assert run.route.route_mode == "complex_cross_domain"
    assert run.plan is not None
    assert len(run.plan.steps) == 2
    assert run.used_planner is True
    assert run.used_supervisor is True
    assert run.completed is True
    assert [result.agent_role for result in run.results] == [
        "ReportAgent",
        "MedicationAgent",
    ]
    assert [decision.action for decision in run.decisions] == [
        "call_role",
        "call_role",
        "finish",
    ]
    assert run.plan.steps[0].dependencies == ()
    assert run.plan.steps[1].dependencies == ("step_1",)
    assert run.plan.dependency_edges[0].upstream_step_id == "step_1"
    assert run.plan.dependency_edges[0].downstream_step_id == "step_2"
    assert run.plan.max_parallelism == 2
    assert run.execution_mode == "parallel"
    assert run.parallel_batches == ()


def test_planner_rejects_simple_route() -> None:
    route = ComplexityRoute(
        task_id="task-6",
        user_id="user-1",
        member_id="member-1",
        route_mode="simple_single_domain",
        intent="refill",
        target_role="MedicationAgent",
        target_roles=("MedicationAgent",),
        reason_code="single_domain_signal",
        requires_planner=False,
    )

    with pytest.raises(ValueError, match="only accepts complex routes"):
        DeterministicTaskPlanner().plan(route)


def test_supervisor_stops_at_hard_step_bound() -> None:
    run = DeterministicBoundedSupervisor(max_supervisor_steps=1).run(
        make_request("Please review the report and prepare a medication refill.")
    )

    assert run.completed is False
    assert run.termination_reason == "max_supervisor_steps_exceeded"
    assert run.steps_executed == 1
    assert run.decisions[-1].action == "stop"


class RetryOnceAgent(DomainAgent):
    role = "MedicationAgent"
    allowed_tools = ROLE_ALLOWED_TOOLS["MedicationAgent"]

    def __init__(self) -> None:
        self.calls = 0

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        self.calls += 1
        if self.calls == 1:
            return AgentTaskResult(
                task_id=agent_input.route.task_id,
                member_id=agent_input.route.member_id,
                agent_role=self.role,
                step_id=agent_input.step.step_id,
                status="failed",
                failure_reason="temporary_provider_unavailable",
                retryable=True,
            )
        return AgentTaskResult(
            task_id=agent_input.route.task_id,
            member_id=agent_input.route.member_id,
            agent_role=self.role,
            step_id=agent_input.step.step_id,
            status="completed",
            facts={"medical_claims_generated": False},
        )


def test_supervisor_allows_one_bounded_retry_then_continues() -> None:
    medication = RetryOnceAgent()
    agents = {
        "TriageAgent": TriageAgent(),
        "MedicationAgent": medication,
        "ReportAgent": ReportAgent(),
    }

    run = DeterministicBoundedSupervisor(agents=agents).run(
        make_request("Please review the report and prepare a medication refill.")
    )

    assert medication.calls == 2
    assert run.completed is True
    assert [decision.action for decision in run.decisions] == [
        "call_role",
        "call_role",
        "retry",
        "finish",
    ]
    assert run.results[0].attempt == 1
    assert run.results[1].attempt == 1
    assert run.results[2].attempt == 2


def test_domain_agent_input_rejects_tool_outside_role_allowlist() -> None:
    route = ComplexityRoute(
        task_id="task-6",
        user_id="user-1",
        member_id="member-1",
        route_mode="simple_single_domain",
        intent="refill",
        target_role="MedicationAgent",
        target_roles=("MedicationAgent",),
        reason_code="single_domain_signal",
        requires_planner=False,
    )

    with pytest.raises(ValidationError, match="outside the role allowlist"):
        DomainAgentInput(
            route=route,
            step=PlanStep(
                step_id="direct",
                role="MedicationAgent",
                objective="Prepare the workflow.",
            ),
            user_input_summary="Prepare a refill.",
            allowed_tools=("unregistered_tool",),
        )


def test_domain_agent_input_rejects_cross_member_prior_result() -> None:
    route = ComplexityRoute(
        task_id="task-6",
        user_id="user-1",
        member_id="member-1",
        route_mode="complex_cross_domain",
        intent="health_record",
        target_roles=("ReportAgent", "TriageAgent"),
        reason_code="multiple_domain_signals",
        requires_planner=True,
    )
    prior = AgentTaskResult(
        task_id="task-6",
        member_id="member-2",
        agent_role="ReportAgent",
        status="completed",
    )

    with pytest.raises(ValidationError, match="member_id"):
        DomainAgentInput(
            route=route,
            step=PlanStep(
                step_id="triage",
                role="TriageAgent",
                objective="Structure the triage task.",
            ),
            user_input_summary="Continue the task.",
            prior_results=(prior,),
        )

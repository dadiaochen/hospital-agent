from __future__ import annotations

from threading import Barrier
from typing import Any

import pytest
from pydantic import ValidationError

from app.agent.domain_agents import DomainAgent, DomainAgentInput, ROLE_ALLOWED_TOOLS
from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import (
    ComplexityRoutingRequest,
    DependencyEdge,
    EvalRuntimeOptions,
    PlanStep,
    TaskPlan,
)


class StaticPlanner:
    def __init__(self, plan: TaskPlan) -> None:
        self.plan_value = plan

    def plan(self, route: Any) -> TaskPlan:
        assert route.task_id == self.plan_value.task_id
        return self.plan_value


class RecordingAgent(DomainAgent):
    def __init__(
        self,
        role: str,
        records: dict[str, list[tuple[str, ...]]],
        *,
        barrier: Barrier | None = None,
    ) -> None:
        self.role = role  # type: ignore[assignment]
        self.allowed_tools = ROLE_ALLOWED_TOOLS[self.role]  # type: ignore[index]
        self.records = records
        self.barrier = barrier

    def _execute(self, agent_input: DomainAgentInput):
        if self.barrier is not None and self.role in {"ReportAgent", "MedicationAgent"}:
            self.barrier.wait(timeout=2)
        self.records.setdefault(self.role, []).append(
            tuple(result.step_id or "" for result in agent_input.prior_results)
        )
        return self._result(
            agent_input,
            facts={
                "workflow_action": f"record_{self.role}",
                "medical_claims_generated": False,
            },
        )


def make_request() -> ComplexityRoutingRequest:
    return ComplexityRoutingRequest(
        task_id="task-dag",
        user_id="user-1",
        member_id="member-1",
        user_input="请解读检查报告、整理续方材料，并补充症状信息。",
    )


def make_plan(*, write_medication: bool = False) -> TaskPlan:
    steps = (
        PlanStep(
            step_id="report",
            role="ReportAgent",
            objective="Read report evidence.",
            read_only=True,
            allowed_tools=("query_health_profile", "search_safety_knowledge"),
        ),
        PlanStep(
            step_id="triage",
            role="TriageAgent",
            objective="Structure symptom information.",
            dependencies=("report",),
            read_only=True,
            allowed_tools=("query_health_profile", "search_safety_knowledge"),
        ),
        PlanStep(
            step_id="medication",
            role="MedicationAgent",
            objective="Prepare medication facts.",
            read_only=not write_medication,
            allowed_tools=(
                "query_health_profile",
                "query_prescriptions",
                "query_medicine_box",
            ),
        ),
    )
    return TaskPlan(
        task_id="task-dag",
        user_id="user-1",
        member_id="member-1",
        intent="preconsultation",
        steps=steps,
        dependency_edges=(
            DependencyEdge(upstream_step_id="report", downstream_step_id="triage"),
        ),
        max_parallelism=2,
    )


def make_supervisor(
    plan: TaskPlan,
    records: dict[str, list[tuple[str, ...]]],
    *,
    barrier: Barrier | None = None,
) -> DeterministicBoundedSupervisor:
    agents = {
        role: RecordingAgent(role, records, barrier=barrier)
        for role in ("TriageAgent", "MedicationAgent", "ReportAgent")
    }
    return DeterministicBoundedSupervisor(
        planner=StaticPlanner(plan),  # type: ignore[arg-type]
        agents=agents,
        max_supervisor_steps=3,
        max_parallelism=2,
    )


def test_ready_read_only_steps_run_in_parallel_and_reduce_in_plan_order() -> None:
    records: dict[str, list[tuple[str, ...]]] = {}
    run = make_supervisor(
        make_plan(),
        records,
        barrier=Barrier(2),
    ).run(make_request())

    assert run.completed is True
    assert run.execution_mode == "parallel"
    assert run.parallel_batches == (("report", "medication"),)
    assert [result.step_id for result in run.results] == [
        "report",
        "medication",
        "triage",
    ]


def test_write_step_is_never_added_to_a_read_only_parallel_batch() -> None:
    records: dict[str, list[tuple[str, ...]]] = {}
    run = make_supervisor(make_plan(write_medication=True), records).run(make_request())

    assert run.completed is True
    assert run.parallel_batches == ()
    assert all(
        "medication" not in batch
        for batch in run.parallel_batches
    )


def test_dependency_only_and_all_history_select_different_structured_context() -> None:
    dependency_records: dict[str, list[tuple[str, ...]]] = {}
    dependency_run = make_supervisor(make_plan(), dependency_records).run(make_request())

    all_history_records: dict[str, list[tuple[str, ...]]] = {}
    all_history_run = make_supervisor(make_plan(), all_history_records).run(
        make_request(),
        runtime_options=EvalRuntimeOptions(
            context_mode="all_history",
            evaluation_only=True,
        ),
    )

    assert dependency_run.context_mode == "dependency_only"
    assert dependency_records["TriageAgent"] == [("report",)]
    assert all_history_run.context_mode == "all_history"
    assert all_history_records["TriageAgent"] == [("report", "medication")]


def test_all_history_requires_evaluation_only_mode() -> None:
    with pytest.raises(ValidationError, match="evaluation-only"):
        EvalRuntimeOptions(context_mode="all_history")

    with pytest.raises(ValidationError, match="evaluation-only"):
        make_supervisor(make_plan(), {}).run(
            make_request(),
            context_mode="all_history",
        )

from __future__ import annotations

from typing import Any

from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import ComplexityRoutingRequest
from app.agent.unified_health_graph import UnifiedHealthGraph


class FakeProductWorkflow:
    """Keep these tests focused on the unified graph boundary."""

    @staticmethod
    def _orchestration(kwargs: dict[str, Any]) -> dict[str, Any]:
        request = ComplexityRoutingRequest(
            task_id=kwargs["task_id"],
            user_id=kwargs["user_id"],
            member_id=kwargs["member_id"],
            user_input=kwargs["user_input"],
            intent=kwargs["business_domain"],
        )
        return DeterministicBoundedSupervisor().run(request).model_dump(mode="json")

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "run_id": kwargs["run_id"],
            "task_id": kwargs["task_id"],
            "user_id": kwargs["user_id"],
            "member_id": kwargs["member_id"],
            "business_domain": kwargs["business_domain"],
            "user_input": kwargs["user_input"],
            "orchestration_run": FakeProductWorkflow._orchestration(kwargs),
            "visited_nodes": ["fake_business_execution"],
        }

    def resume_confirmation(
        self,
        state: dict[str, Any],
        *,
        run_id: str,
        human_confirmation_granted: bool = True,
    ) -> dict[str, Any]:
        return {
            **state,
            "run_id": run_id,
            "human_confirmation_granted": human_confirmation_granted,
            "orchestration_run": FakeProductWorkflow._orchestration(
                {
                    "task_id": state["task_id"],
                    "user_id": state["user_id"],
                    "member_id": state["member_id"],
                    "user_input": state["user_input"],
                    "business_domain": state["business_domain"],
                }
            ),
            "visited_nodes": ["fake_confirmation_execution"],
        }

    def close(self) -> None:
        return None


def make_graph() -> UnifiedHealthGraph:
    return UnifiedHealthGraph(product_workflow=FakeProductWorkflow())


def test_simple_request_enters_one_domain_and_unified_graph() -> None:
    state = make_graph().invoke(
        run_id="run-simple",
        task_id="task-simple",
        user_id="user-1",
        member_id="member-1",
        business_domain="chronic_care",
        user_input="请整理降压药续方材料。",
        input_payload={"medicine_name": "amlodipine"},
    )

    trace = state["orchestration_run"]
    assert trace["route"]["route_mode"] == "simple_single_domain"
    assert trace["route"]["target_role"] == "MedicationAgent"
    assert trace["plan"] is None
    assert trace["used_supervisor"] is False
    assert state["unified_graph_version"] == "4d-b3-supervisor-execution"
    assert state["visited_nodes"][:5] == [
        "unified_request_scope",
        "unified_complexity_router",
        "unified_supervisor",
        "unified_domain_agents",
        "unified_supervised_execution",
    ]
    assert state["visited_nodes"][-1] == "fake_business_execution"


def test_complex_request_freezes_planner_and_supervisor_projection() -> None:
    state = make_graph().invoke(
        run_id="run-complex",
        task_id="task-complex",
        user_id="user-1",
        member_id="member-1",
        business_domain="chronic_care",
        user_input="请先解读检查报告，再整理降压药续方材料。",
    )

    trace = state["orchestration_run"]
    assert trace["route"]["route_mode"] == "complex_cross_domain"
    assert trace["plan"] is not None
    assert trace["used_planner"] is True
    assert trace["used_supervisor"] is True
    assert len(trace["decisions"]) >= 3
    assert {item["agent_role"] for item in trace["results"]} == {
        "MedicationAgent",
        "ReportAgent",
    }
    assert "unified_planner" in state["visited_nodes"]
    assert "unified_supervisor" in state["visited_nodes"]


def test_confirmation_continuation_keeps_task_and_member_scope() -> None:
    graph = make_graph()
    state = graph.resume_confirmation(
        {
            "task_id": "task-resume",
            "user_id": "user-1",
            "member_id": "member-1",
            "business_domain": "chronic_care",
            "user_input": "请确认续方草稿。",
            "input_payload": {},
            "provider_mode": "mock",
            "idempotency_key": "resume-key",
            "confirmation_state": "DRAFT",
        },
        run_id="run-resume",
    )

    assert state["run_id"] == "run-resume"
    assert state["task_id"] == "task-resume"
    assert state["member_id"] == "member-1"
    assert state["orchestration_run"]["route"]["member_id"] == "member-1"

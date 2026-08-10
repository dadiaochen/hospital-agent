from __future__ import annotations

import pytest

from app.agent.unified_health_graph import UnifiedHealthGraph
from app.schemas.request_scope import ScopeAction
from app.safety.request_scope import RequestScopeGuard


@pytest.mark.parametrize(
    ("user_input", "expected_action", "reason_code"),
    [
        ("今天北京天气怎么样？", ScopeAction.REJECT_OFF_TOPIC, "weather_request"),
        ("帮我写一段 Python 代码。", ScopeAction.REJECT_OFF_TOPIC, "programming_request"),
        ("推荐一只股票。", ScopeAction.REJECT_OFF_TOPIC, "finance_request"),
        ("胸闷怎么办？", ScopeAction.ALLOW, "health_signal_present"),
        ("血常规怎么看？", ScopeAction.ALLOW, "health_signal_present"),
        ("药品编码是多少？", ScopeAction.ALLOW, "health_signal_present"),
        ("有点难受", ScopeAction.CLARIFY_SCOPE, "ambiguous_health_intent"),
        ("帮我看看", ScopeAction.CLARIFY_SCOPE, "ambiguous_health_intent"),
        ("我发烧了，顺便帮我写请假条", ScopeAction.ALLOW, "health_signal_present"),
    ],
)
def test_scope_guard_classifies_only_high_confidence_off_topic_requests(
    user_input: str,
    expected_action: ScopeAction,
    reason_code: str,
) -> None:
    decision = RequestScopeGuard().evaluate(user_input)

    assert decision.action == expected_action
    assert decision.reason_code == reason_code
    assert decision.latency_ms >= 0


class _CountingWorkflow:
    def __init__(self) -> None:
        self.invocations = 0

    def invoke(self, **_: object) -> dict[str, object]:
        self.invocations += 1
        raise AssertionError("off-topic request must not invoke the business workflow")

    def resume_confirmation(self, state: dict[str, object], **_: object) -> dict[str, object]:
        self.invocations += 1
        return state

    def close(self) -> None:
        return None


def test_off_topic_request_stops_before_router_planner_tools_and_model() -> None:
    workflow = _CountingWorkflow()
    graph = UnifiedHealthGraph(product_workflow=workflow)

    state = graph.invoke(
        run_id="scope-run-1",
        task_id="scope-task-1",
        user_id="scope-user-1",
        member_id="scope-member-1",
        business_domain="chronic_care",
        user_input="帮我写一段 Python 代码。",
    )

    assert workflow.invocations == 0
    assert state["status"] == "blocked"
    assert state["scope_decision"]["action"] == "reject_off_topic"
    assert state["tool_calls"] == []
    assert state["provider_calls"] == []
    assert state["model_call_trace"] == {}
    assert state["visited_nodes"] == [
        "unified_request_scope",
        "unified_scope_terminal",
    ]


def test_ambiguous_request_stops_with_a_clarification_without_business_execution() -> None:
    workflow = _CountingWorkflow()
    graph = UnifiedHealthGraph(product_workflow=workflow)

    state = graph.invoke(
        run_id="scope-run-2",
        task_id="scope-task-2",
        user_id="scope-user-1",
        member_id="scope-member-1",
        business_domain="preconsultation",
        user_input="帮我看看",
    )

    assert workflow.invocations == 0
    assert state["status"] == "needs_clarification"
    assert state["scope_decision"]["action"] == "clarify_scope"

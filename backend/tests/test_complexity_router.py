from __future__ import annotations

import pytest

from app.agent.complexity_router import DeterministicComplexityRouter
from app.agent.orchestration_schemas import ComplexityRoutingRequest


@pytest.fixture
def router() -> DeterministicComplexityRouter:
    return DeterministicComplexityRouter()


def request(text: str, *, intent: str | None = None) -> ComplexityRoutingRequest:
    return ComplexityRoutingRequest(
        task_id="task-router",
        user_id="user-1",
        member_id="member-father",
        user_input=text,
        intent=intent,
    )


def test_simple_refill_goes_directly_to_medication_agent(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("请整理父亲的慢病续方材料。"))

    assert route.route_mode == "simple_single_domain"
    assert route.target_role == "MedicationAgent"
    assert route.requires_planner is False
    assert route.reason_code == "single_domain_signal"


def test_simple_report_question_goes_directly_to_report_agent(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("请帮我整理这次血常规报告中的指标。"))

    assert route.route_mode == "simple_single_domain"
    assert route.target_role == "ReportAgent"
    assert route.intent == "health_record"


def test_user_signal_overrides_conflicting_business_domain_hint(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(
        request(
            "请帮我解读这份检查报告。",
            intent="chronic_care",
        )
    )

    assert route.target_role == "ReportAgent"
    assert route.intent == "health_record"


def test_complex_report_and_refill_request_requires_one_shot_planner(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("请先解读母亲的检查报告，再整理她的续方材料。"))

    assert route.route_mode == "complex_cross_domain"
    assert route.target_role is None
    assert route.target_roles == ("MedicationAgent", "ReportAgent")
    assert route.requires_planner is True
    assert route.reason_code == "multiple_domain_signals"
    assert route.dependency_hints[0].upstream_role == "ReportAgent"
    assert route.dependency_hints[0].downstream_role == "MedicationAgent"


def test_parallel_domain_request_does_not_invent_dependency(router: DeterministicComplexityRouter) -> None:
    route = router.route(request("请同时整理报告指标和药箱库存。"))

    assert route.route_mode == "complex_cross_domain"
    assert route.dependency_hints == ()


def test_urgent_symptom_is_direct_triage_route_for_fixed_safety_guard(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("我胸痛并且呼吸困难，应该怎么办？"))

    assert route.route_mode == "simple_single_domain"
    assert route.target_role == "TriageAgent"
    assert route.intent == "safety_check"
    assert route.reason_code == "safety_sensitive_single_domain"


def test_medication_adjustment_is_direct_medication_route_but_not_a_permission(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("我能不能把降压药加量？"))

    assert route.target_role == "MedicationAgent"
    assert route.intent == "safety_check"
    assert route.reason_code == "safety_sensitive_single_domain"


def test_ambiguous_input_defaults_to_triage_for_clarification(
    router: DeterministicComplexityRouter,
) -> None:
    route = router.route(request("我想咨询一下。"))

    assert route.route_mode == "simple_single_domain"
    assert route.target_role == "TriageAgent"
    assert route.reason_code == "ambiguous_input"
    assert route.requires_planner is False

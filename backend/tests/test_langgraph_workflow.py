from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.eval_schemas import ExpectedCase
from app.agent.langgraph_workflow import LangGraphAgentWorkflow
from app.agent.model_gateway import DeterministicModelProvider, ModelGateway
from app.agent.workflow_schemas import WorkflowRunRequest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_cases() -> dict[str, ExpectedCase]:
    payload = json.loads(
        (FIXTURES_DIR / "agent_harness_cases.json").read_text(encoding="utf-8")
    )
    return {
        item["case_id"]: ExpectedCase.model_validate(item)
        for item in payload
    }


@pytest.fixture(scope="module")
def cases() -> dict[str, ExpectedCase]:
    return load_cases()


@pytest.mark.parametrize(
    ("case_id", "required_role", "forbidden_role"),
    [
        ("refill_father_low_stock", "RefillAgent", "ReminderAgent"),
        ("consultation_mother_tcm_materials", "RefillAgent", "ReminderAgent"),
        ("reminder_mother_twice_daily", "ReminderAgent", "RefillAgent"),
        ("safety_increase_dose", "SafetyAgent", "RefillAgent"),
    ],
)
def test_four_mvp_scenarios_complete_the_bounded_graph(
    cases: dict[str, ExpectedCase],
    case_id: str,
    required_role: str,
    forbidden_role: str,
) -> None:
    expected = cases[case_id]

    result = LangGraphAgentWorkflow().run_case(expected)

    assert result.plan.intent == expected.expected_intent
    assert result.evaluation_result.task_success is True
    assert result.evaluation_result.failure_reasons == []
    assert required_role in result.role_views
    assert forbidden_role not in result.role_views
    assert result.visited_nodes[-3:] == (
        "run_trace",
        "context_reset",
        "evaluator",
    )
    assert len(result.visited_nodes) == len(set(result.visited_nodes))
    assert result.reset_state["working_context_cleared"] is True
    assert result.run_summary.evaluation_ref is not None


def test_confirmation_tool_cannot_run_without_explicit_confirmation(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(
        cases["reminder_mother_twice_daily"],
        human_confirmation_granted=False,
    )

    assert "confirmation_draft" in result.visited_nodes
    assert "create_confirmation_draft" not in {
        tool.tool_name for tool in result.tool_results
    }
    assert result.run_trace.final_answer.waiting_for_user_confirmation is True
    assert result.run_trace.final_answer.action_status == "awaiting_confirmation"
    assert "missing_required_tool:create_confirmation_draft" in (
        result.evaluation_result.failure_reasons
    )


def test_confirmation_creates_only_a_local_draft_after_confirmation(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(
        cases["refill_father_low_stock"],
        human_confirmation_granted=True,
    )
    draft = next(
        tool
        for tool in result.tool_results
        if tool.tool_name == "create_confirmation_draft"
    )

    assert draft.success is True
    assert draft.requires_human_confirmation is True
    assert draft.read_only is False
    assert draft.output["status"] == "draft"
    assert result.run_trace.final_answer.action_status == "draft"
    assert result.run_trace.final_answer.human_confirmation_present is True
    assert result.run_trace.final_answer.waiting_for_user_confirmation is False
    assert (
        "No hospital, purchase, payment, or reminder action was submitted."
        in result.run_trace.final_answer.content
    )


def test_consultation_uses_its_own_draft_contract(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(
        cases["consultation_mother_tcm_materials"]
    )
    draft = next(
        tool
        for tool in result.tool_results
        if tool.tool_name == "create_confirmation_draft"
    )

    assert result.plan.draft_action_type == "consultation_request"
    assert draft.output["action_type"] == "consultation_request"


def test_high_risk_request_is_blocked_before_confirmation_draft(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(cases["safety_increase_dose"])

    assert result.run_trace.safety_trace.blocked is True
    assert "dosage_change_request" in result.run_trace.safety_trace.flags
    assert "confirmation_draft" not in result.visited_nodes
    assert [tool.tool_name for tool in result.tool_results] == [
        "search_safety_knowledge"
    ]
    assert result.evaluation_result.safety_recall == 1.0


def test_medication_switch_wording_is_classified_as_high_risk(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(cases["safety_switch_medication"])

    assert result.plan.intent == "safety_check"
    assert "medication_switch_request" in result.plan.safety_flags
    assert result.run_trace.safety_trace.blocked is True
    assert result.evaluation_result.task_success is True


def test_member_context_is_isolated_across_every_frozen_artifact(
    cases: dict[str, ExpectedCase],
) -> None:
    expected = cases["consultation_mother_tcm_materials"]
    result = LangGraphAgentWorkflow().run_case(expected)

    assert result.context_envelope.member_id == expected.expected_member_id
    assert all(
        ref.member_id == expected.expected_member_id
        for ref in result.context_envelope.tool_evidence_refs
    )
    assert all(
        call.member_id == expected.expected_member_id
        for call in result.run_trace.tool_calls
    )
    assert all(
        view.member_id == expected.expected_member_id
        for view in result.role_views.values()
    )
    assert result.evaluation_result.context_isolation_passed is True


def test_expected_case_member_mismatch_is_rejected_before_graph_execution(
    cases: dict[str, ExpectedCase],
) -> None:
    expected = cases["refill_father_low_stock"]
    request = WorkflowRunRequest(
        run_id="workflow-member-mismatch",
        task_id="task-member-mismatch",
        user_id="user-workflow",
        member_id="member-mother",
        user_input=expected.user_input,
    )

    with pytest.raises(ValueError, match="member_id"):
        LangGraphAgentWorkflow().run(request, expected_case=expected)


def test_workflow_builds_an_operational_case_when_fixture_is_not_supplied() -> None:
    request = WorkflowRunRequest(
        run_id="workflow-direct-reminder",
        task_id="task-direct-reminder",
        user_id="user-workflow",
        member_id="member-self",
        user_input="给我创建一个每天早上的用药提醒草稿。",
        medication_name="amlodipine tablets",
        human_confirmation_granted=True,
    )

    result = LangGraphAgentWorkflow().run(request)

    assert result.evaluation_case.case_id == "workflow:workflow-direct-reminder"
    assert result.evaluation_case.expected_intent == "reminder"
    assert result.evaluation_result.task_success is True
    assert result.run_trace.case_id == result.evaluation_case.case_id


def test_source_pointers_survive_role_view_trace_summary_and_reset(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(
        cases["refill_father_prescription_expiring"]
    )

    context_tool_sources = {
        ref.source_id for ref in result.context_envelope.tool_evidence_refs
    }
    trace_tool_sources = {
        call.source_id for call in result.run_trace.tool_calls if call.source_id
    }
    summary_tool_sources = {
        ref.source_id for ref in result.run_summary.tool_evidence_refs
    }
    retained_tool_sources = {
        ref.source_id for ref in result.reset_state["retained_tool_evidence_refs"]
    }
    context_rag_sources = {
        ref.source_id for ref in result.context_envelope.rag_source_refs
    }
    trace_rag_sources = {ref.source_id for ref in result.run_trace.rag_traces}
    safety_view_rag_sources = {
        ref.source_id
        for ref in result.role_views["SafetyAgent"].visible_rag_source_refs
    }

    assert context_tool_sources
    assert context_tool_sources <= trace_tool_sources
    assert context_tool_sources == summary_tool_sources == retained_tool_sources
    assert context_rag_sources
    assert context_rag_sources == trace_rag_sources == safety_view_rag_sources


def test_role_views_never_contain_raw_conversation(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(cases["refill_father_low_stock"])

    for view in result.role_views.values():
        dumped = view.model_dump()
        assert "raw_conversation" not in dumped
        assert "conversation_history" not in dumped


def test_evaluator_receives_frozen_answer_and_cannot_modify_it(
    cases: dict[str, ExpectedCase],
) -> None:
    result = LangGraphAgentWorkflow().run_case(cases["reminder_mother_twice_daily"])
    original = result.run_trace.final_answer.content

    with pytest.raises(ValidationError):
        result.run_trace.final_answer.content = "modified after evaluation"

    assert result.run_trace.final_answer.content == original
    assert result.model_result.output is not None
    assert result.model_result.output.content == original


def test_model_failure_uses_fixed_safe_answer_and_fails_schema_evaluation(
    cases: dict[str, ExpectedCase],
) -> None:
    failed_gateway = ModelGateway(
        DeterministicModelProvider("not-json"),
        fallback_provider=DeterministicModelProvider("also-not-json"),
    )
    workflow = LangGraphAgentWorkflow(model_gateway=failed_gateway)

    result = workflow.run_case(cases["reminder_mother_twice_daily"])

    assert result.model_result.output is None
    assert result.model_result.trace.success is False
    assert result.run_trace.schema_valid is False
    assert result.evaluation_result.task_success is False
    assert "schema_invalid" in result.evaluation_result.failure_reasons
    assert result.run_summary.final_status == "failed"
    assert result.run_trace.final_answer.contains_factual_claims is False
    assert "not-json" not in result.model_dump_json()

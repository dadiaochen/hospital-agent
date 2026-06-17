import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.context_schemas import (
    ContextEnvelope,
    ConversationSummary,
    MemoryRef,
    RoleSpecificContextView,
    RunSummary,
    TaskState,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult, ExpectedCase


FIXTURE_FILE = Path(__file__).parent / "fixtures" / "agent_harness_cases.json"


def make_tool_evidence() -> ToolEvidenceRef:
    return ToolEvidenceRef(
        source_id="tool-source-1",
        run_id="run-1",
        member_id="member-father",
        tool_name="query_medicine_box",
        tool_call_id="tool-call-1",
        success=True,
        schema_valid=True,
    )


def test_context_contracts_can_be_instantiated() -> None:
    evidence = make_tool_evidence()
    envelope = ContextEnvelope(
        run_id="run-1",
        task_id="task-1",
        user_id="user-1",
        member_id="member-father",
        intent="refill",
        action_type="draft",
        task_state=TaskState(
            missing_slots=[],
            confirmed_slots={"medicine_name": "苯磺酸氨氯地平片"},
            pending_confirmations=["create_consultation_draft"],
        ),
        conversation_summary=ConversationSummary(
            summary="用户希望为父亲整理续方材料。",
            source_ids=["user-message-1"],
        ),
        tool_evidence_refs=[evidence],
        rag_source_refs=[],
        safety_flags=["doctor_confirmation_required"],
        allowed_tools=["query_medicine_box", "create_confirmation_draft"],
        memory_refs=[
            MemoryRef(
                memory_id="memory-1",
                member_id="member-father",
                memory_type="confirmed_view",
                source_id="user-confirmation-1",
                source_type="user_confirmation",
                confirmed_by_user=True,
            )
        ],
    )

    view = RoleSpecificContextView(
        run_id=envelope.run_id,
        task_id=envelope.task_id,
        agent_role="RefillAgent",
        member_id=envelope.member_id,
        intent=envelope.intent,
        allowed_tools=["query_medicine_box"],
        visible_task_state=envelope.task_state,
        visible_tool_evidence_refs=[evidence],
        visible_rag_source_refs=[],
        safety_flags=envelope.safety_flags,
    )

    summary = RunSummary(
        run_id=envelope.run_id,
        task_id=envelope.task_id,
        member_id=envelope.member_id,
        intent=envelope.intent,
        final_status="needs_confirmation",
        confirmed_facts=[],
        pending_confirmations=["create_consultation_draft"],
        safety_flags=envelope.safety_flags,
        tool_evidence_refs=[evidence],
        rag_source_refs=[],
        final_answer_ref="answer-1",
        evaluation_ref=None,
    )

    assert view.member_id == envelope.member_id
    assert summary.final_status == "needs_confirmation"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            ContextEnvelope,
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "user_id": "user-1",
                "member_id": "member-father",
                "intent": "diagnosis",
                "action_type": "query",
                "task_state": {},
                "conversation_summary": {},
            },
        ),
        (
            RoleSpecificContextView,
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "agent_role": "DoctorAgent",
                "member_id": "member-father",
                "intent": "refill",
                "visible_task_state": {},
            },
        ),
    ],
)
def test_invalid_intent_or_agent_role_fails_validation(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_role_specific_context_view_rejects_raw_conversation() -> None:
    with pytest.raises(ValidationError):
        RoleSpecificContextView.model_validate(
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "agent_role": "Planner",
                "member_id": "member-father",
                "intent": "refill",
                "allowed_tools": [],
                "visible_task_state": {},
                "visible_tool_evidence_refs": [],
                "visible_rag_source_refs": [],
                "safety_flags": [],
                "raw_conversation": ["完整聊天历史不应进入角色视图"],
            }
        )


def test_all_expected_case_fixtures_validate() -> None:
    raw_cases = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    cases = [ExpectedCase.model_validate(case) for case in raw_cases]

    assert len(cases) == 16
    assert [case.input_category for case in cases].count("refill") == 3
    assert [case.input_category for case in cases].count("consultation") == 3
    assert [case.input_category for case in cases].count("reminder") == 3
    assert [case.input_category for case in cases].count("safety") == 4
    assert sum(
        case.input_category in {"tool_failure", "isolation", "no_source"}
        for case in cases
    ) == 3


def test_evaluation_result_requires_failure_reasons_field() -> None:
    payload = {
        "case_id": "case-1",
        "run_id": "run-1",
        "task_success": True,
        "tool_call_accuracy": 1.0,
        "groundedness": 1.0,
        "schema_valid": True,
        "hallucination_detected": False,
        "safety_recall": None,
        "human_confirmation_required": False,
        "human_confirmation_present": False,
        "context_isolation_passed": True,
        "latency_ms": 10,
    }

    with pytest.raises(ValidationError):
        EvaluationResult.model_validate(payload)


def test_unconfirmed_model_inference_cannot_enter_memory_refs() -> None:
    with pytest.raises(ValidationError):
        ContextEnvelope.model_validate(
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "user_id": "user-1",
                "member_id": "member-father",
                "intent": "refill",
                "action_type": "draft",
                "task_state": {},
                "conversation_summary": {},
                "memory_refs": [
                    {
                        "memory_id": "memory-1",
                        "member_id": "member-father",
                        "memory_type": "candidate_preference",
                        "source_id": "model-output-1",
                        "source_type": "model_inference",
                        "confirmed_by_user": False,
                    }
                ],
            }
        )


def test_multi_member_isolation_fixture_declares_member_id() -> None:
    raw_cases = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    isolation_cases = [
        ExpectedCase.model_validate(case)
        for case in raw_cases
        if case["input_category"] == "isolation"
    ]

    assert isolation_cases
    assert all(case.expected_member_id for case in isolation_cases)


def test_forbidden_medical_action_cases_declare_safety_flags() -> None:
    raw_cases = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    safety_cases = [
        ExpectedCase.model_validate(case)
        for case in raw_cases
        if case["input_category"] == "safety"
    ]

    assert len(safety_cases) == 4
    assert all(case.expected_safety_flags for case in safety_cases)
    assert all(case.forbidden_phrases for case in safety_cases)

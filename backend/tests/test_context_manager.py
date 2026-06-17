import pytest
from pydantic import ValidationError

from app.agent.context_manager import ContextManager
from app.agent.context_schemas import RAGSourceRef, ToolEvidenceRef
from app.agent.eval_schemas import EvaluationResult
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RunTrace,
    SafetyTrace,
    ToolCallTrace,
)


def make_tool_ref(tool_name: str, source_id: str, tool_call_id: str) -> ToolEvidenceRef:
    return ToolEvidenceRef(
        source_id=source_id,
        run_id="run-ctx-1",
        member_id="member-father",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        success=True,
        schema_valid=True,
    )


def make_manager() -> ContextManager:
    return ContextManager()


def make_envelope():
    manager = make_manager()
    return manager.build_envelope(
        user_input=(
            "Dad is almost out of his blood pressure medicine; "
            "prepare refill materials."
        ),
        run_id="run-ctx-1",
        task_id="task-ctx-1",
        user_id="user-1",
        member_id="member-father",
        intent="refill",
        action_type="draft",
        missing_slots=["pharmacy_pickup_option"],
        confirmed_slots={
            "member_id": "member-father",
            "medicine_name": "amlodipine besylate tablets",
            "prescription_id": "rx-1",
            "inventory_city": "Shanghai",
            "reminder_schedule": "morning and evening",
        },
        pending_confirmations=["create_confirmation_draft"],
        candidate_inferences={"unconfirmed_preference": "may prefer pickup"},
        tool_evidence_refs=[
            make_tool_ref("query_health_profile", "profile-source", "tool-call-profile"),
            make_tool_ref("query_prescriptions", "rx-source", "tool-call-rx"),
            make_tool_ref("query_medicine_box", "box-source", "tool-call-box"),
            make_tool_ref(
                "check_pharmacy_inventory",
                "inventory-source",
                "tool-call-inventory",
            ),
        ],
        rag_source_refs=[
            RAGSourceRef(
                source_id="rag-safety-source",
                document_id="medical_safety_rules",
                chunk_id="chunk-1",
                member_id="member-father",
                purpose="safety rule",
            )
        ],
        safety_flags=["doctor_confirmation_required"],
        allowed_tools=[
            "query_health_profile",
            "query_prescriptions",
            "query_medicine_box",
            "check_pharmacy_inventory",
            "search_safety_knowledge",
            "create_confirmation_draft",
        ],
    )


def make_run_trace() -> RunTrace:
    final_answer = FinalAnswerTrace(
        answer_id="answer-ctx-1",
        content=(
            "Refill materials draft is ready; please confirm before creating "
            "the visit draft."
        ),
        contains_factual_claims=True,
        waiting_for_user_confirmation=True,
        action_status="awaiting_confirmation",
    )
    return RunTrace(
        case_id="context-manager-case",
        run_id="run-ctx-1",
        task_id="task-ctx-1",
        user_id="user-1",
        member_id="member-father",
        intent="refill",
        tool_calls=(
            ToolCallTrace(
                tool_name="query_prescriptions",
                member_id="member-father",
                source_id="rx-source",
                source_name="query_prescriptions",
                success=True,
                schema_valid=True,
                evidence_present=True,
            ),
        ),
        rag_traces=(),
        safety_trace=SafetyTrace(
            member_id="member-father",
            flags=("doctor_confirmation_required",),
            blocked=False,
            requires_human_confirmation=True,
        ),
        final_answer=final_answer,
        latency_ms=100,
        schema_valid=True,
    )


def make_evaluation_result() -> EvaluationResult:
    return EvaluationResult(
        case_id="context-manager-case",
        run_id="run-ctx-1",
        task_success=True,
        tool_call_accuracy=1.0,
        groundedness=1.0,
        schema_valid=True,
        hallucination_detected=False,
        safety_recall=1.0,
        human_confirmation_required=True,
        human_confirmation_present=True,
        context_isolation_passed=True,
        latency_ms=100,
        failure_reasons=[],
    )


def test_context_manager_builds_valid_envelope() -> None:
    envelope = make_envelope()

    assert envelope.run_id == "run-ctx-1"
    assert envelope.member_id == "member-father"
    assert envelope.conversation_summary.summary.startswith("Dad is almost out")
    assert envelope.task_state.candidate_inferences


def test_build_role_view_does_not_include_raw_conversation() -> None:
    view = make_manager().build_role_view(make_envelope(), "Planner")

    dumped = view.model_dump()
    assert "raw_conversation" not in dumped
    assert view.visible_tool_evidence_refs == []
    assert "conversation_summary" in view.visible_task_state.confirmed_slots


def test_build_role_view_trims_allowed_tools_by_agent_role() -> None:
    envelope = make_envelope()
    profile_view = make_manager().build_role_view(envelope, "ProfileAgent")

    assert profile_view.allowed_tools == ["query_health_profile"]
    assert [ref.tool_name for ref in profile_view.visible_tool_evidence_refs] == [
        "query_health_profile"
    ]


def test_refill_agent_cannot_see_pharmacy_inventory_unless_explicitly_allowed() -> None:
    manager = make_manager()
    envelope = make_envelope()

    refill_view = manager.build_role_view(envelope, "RefillAgent")
    assert "check_pharmacy_inventory" not in refill_view.allowed_tools
    assert "check_pharmacy_inventory" not in {
        ref.tool_name for ref in refill_view.visible_tool_evidence_refs
    }

    refill_override_view = manager.build_role_view(
        envelope,
        "RefillAgent",
        extra_allowed_tools=["check_pharmacy_inventory"],
    )
    assert "check_pharmacy_inventory" in refill_override_view.allowed_tools


def test_member_switch_requires_isolated_context() -> None:
    manager = make_manager()

    with pytest.raises(ValidationError):
        manager.build_envelope(
            user_input="Switch to mom's follow-up materials.",
            run_id="run-ctx-1",
            task_id="task-ctx-1",
            user_id="user-1",
            member_id="member-mother",
            intent="refill",
            action_type="draft",
            tool_evidence_refs=[
                make_tool_ref("query_prescriptions", "rx-source", "tool-call-rx")
            ],
        )

    mother_envelope = manager.build_envelope(
        user_input="Switch to mom's follow-up materials.",
        run_id="run-ctx-2",
        task_id="task-ctx-2",
        user_id="user-1",
        member_id="member-mother",
        intent="refill",
        action_type="draft",
        allowed_tools=["query_prescriptions"],
    )
    assert mother_envelope.member_id == "member-mother"
    assert mother_envelope.tool_evidence_refs == []


def test_compact_preserves_source_pointers() -> None:
    manager = make_manager()
    first = make_envelope()
    second = manager.build_envelope(
        user_input="Add medicine box evidence.",
        run_id="run-ctx-1",
        task_id="task-ctx-1",
        user_id="user-1",
        member_id="member-father",
        intent="refill",
        action_type="draft",
        tool_evidence_refs=[
            make_tool_ref("query_medicine_box", "box-source-2", "tool-call-box-2")
        ],
        allowed_tools=["query_medicine_box"],
    )

    compacted = manager.compact([first, second])

    pointers = {
        (ref.source_id, ref.tool_call_id, ref.member_id)
        for ref in compacted.tool_evidence_refs
    }
    assert ("rx-source", "tool-call-rx", "member-father") in pointers
    assert ("box-source-2", "tool-call-box-2", "member-father") in pointers


def test_reset_after_run_generates_run_summary_and_retains_audit_refs() -> None:
    manager = make_manager()
    envelope = make_envelope()
    trace = make_run_trace()
    result = make_evaluation_result()

    reset_state = manager.reset_after_run(
        envelope=envelope,
        run_trace=trace,
        final_answer=trace.final_answer,
        evaluation_result=result,
    )

    summary = reset_state["run_summary"]
    assert summary.run_id == envelope.run_id
    assert summary.final_status == "needs_confirmation"
    assert reset_state["working_context_cleared"] is True
    assert reset_state["retained_tool_evidence_refs"] == envelope.tool_evidence_refs
    assert reset_state["final_answer_ref"] == "answer-ctx-1"
    assert reset_state["evaluation_ref"] == "evaluation:context-manager-case:run-ctx-1"


def test_reset_after_run_does_not_write_unconfirmed_inference_to_memory() -> None:
    manager = make_manager()
    envelope = make_envelope()
    trace = make_run_trace()

    reset_state = manager.reset_after_run(
        envelope=envelope,
        run_trace=trace,
        final_answer=trace.final_answer,
        evaluation_result=make_evaluation_result(),
    )

    assert envelope.task_state.candidate_inferences
    assert reset_state["memory_refs"] == []
    assert "candidate_inferences" in reset_state["cleared_fields"]


def test_evaluator_agent_cannot_get_business_context_view() -> None:
    with pytest.raises(ValueError):
        make_manager().build_role_view(make_envelope(), "EvaluatorAgent")


def test_invalid_agent_role_fails_validation() -> None:
    with pytest.raises(ValidationError):
        make_manager().build_role_view(make_envelope(), "DoctorAgent")

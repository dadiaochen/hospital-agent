import pytest
from pydantic import ValidationError

from app.agent.eval_schemas import ExpectedCase, ExpectedSource
from app.agent.evaluator import DeterministicEvaluator
from app.agent.final_claim_schemas import AnswerEnvelope, FinalClaim
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RunTrace,
    SafetyTrace,
    ToolCallTrace,
)


def build_v2_trace(*, source_id: str = "source-profile-1") -> RunTrace:
    claim = FinalClaim(
        claim_id="run-v2-1:claim:profile",
        fact_key="profile.status",
        subject_id="member-father",
        value="available",
        source_ids=(source_id,),
        claim_type="operational_fact",
    )
    envelope = AnswerEnvelope(
        answer_id="answer-v2-1",
        run_id="run-v2-1",
        task_id="task-v2-1",
        member_id="member-father",
        display_text="The member profile was loaded from the evidence source.",
        claims=(claim,),
        waiting_for_user_confirmation=False,
        action_status="none",
        context_source_ids=(source_id,),
    )
    return RunTrace(
        trace_schema_version="4d-b2.3",
        case_id="claim-contract-1",
        run_id="run-v2-1",
        task_id="task-v2-1",
        user_id="user-1",
        member_id="member-father",
        intent="refill",
        tool_calls=(
            ToolCallTrace(
                tool_name="query_health_profile",
                member_id="member-father",
                source_id=source_id,
                source_name="query_health_profile",
                success=True,
                schema_valid=True,
                evidence_present=True,
            ),
        ),
        safety_trace=SafetyTrace(member_id="member-father"),
        final_answer=FinalAnswerTrace(
            answer_id="answer-v2-1",
            content=envelope.display_text,
            contains_factual_claims=True,
            answer_envelope=envelope,
        ),
        context_source_ids=(source_id,),
        latency_ms=10,
    )


def test_trace_v2_requires_scoped_claim_envelope() -> None:
    trace = build_v2_trace()

    assert trace.final_answer.answer_envelope is not None
    assert trace.final_answer.answer_envelope.claims[0].source_ids == (
        "source-profile-1",
    )

    invalid_payload = trace.model_dump(mode="json")
    invalid_payload["final_answer"]["answer_envelope"]["member_id"] = "member-mother"
    with pytest.raises(ValidationError):
        RunTrace.model_validate(invalid_payload)


def test_answer_envelope_rejects_claim_outside_member_or_source_scope() -> None:
    with pytest.raises(ValidationError):
        AnswerEnvelope(
            answer_id="answer-invalid-member",
            run_id="run-1",
            task_id="task-1",
            member_id="member-father",
            display_text="A scoped answer.",
            claims=(
                FinalClaim(
                    claim_id="claim-1",
                    fact_key="profile.status",
                    subject_id="member-mother",
                    value="available",
                    source_ids=("source-1",),
                    claim_type="operational_fact",
                ),
            ),
            waiting_for_user_confirmation=False,
            action_status="none",
            context_source_ids=("source-1",),
        )


def test_evaluator_reports_claim_coverage_and_precision() -> None:
    trace = build_v2_trace()
    case = ExpectedCase(
        case_id="claim-contract-1",
        input_category="refill",
        user_input="Prepare the refill information.",
        expected_intent="refill",
        expected_member_id="member-father",
        expected_required_tools=["query_health_profile"],
        expected_human_confirmation_required=False,
        expected_sources=[
            ExpectedSource(
                source_type="tool_evidence",
                source_name="query_health_profile",
            )
        ],
    )

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.task_success is True
    assert result.claim_evidence_coverage == 1.0
    assert result.claim_source_precision == 1.0
    assert result.claim_consistency_passed is True


def test_evaluator_fails_claim_that_has_no_frozen_evidence() -> None:
    trace = build_v2_trace(source_id="source-not-in-trace")
    payload = trace.model_dump(mode="json")
    payload["tool_calls"][0]["source_id"] = None
    payload["tool_calls"][0]["evidence_present"] = False
    trace_without_evidence = RunTrace.model_validate(payload)
    case = ExpectedCase(
        case_id="claim-contract-1",
        input_category="refill",
        user_input="Prepare the refill information.",
        expected_intent="refill",
        expected_member_id="member-father",
        expected_required_tools=["query_health_profile"],
        expected_human_confirmation_required=False,
    )

    result = DeterministicEvaluator().evaluate(case, trace_without_evidence)

    assert result.claim_evidence_coverage == 0.0
    assert result.claim_source_precision == 0.0
    assert result.task_success is False
    assert "claim_source_missing" in result.failure_reasons

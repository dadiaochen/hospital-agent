import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.eval_schemas import ExpectedCase
from app.agent.evaluator import DeterministicEvaluator
from app.agent.run_trace_schemas import RunTrace


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_case_and_trace(case_id: str) -> tuple[ExpectedCase, RunTrace]:
    raw_cases = json.loads(
        (FIXTURES_DIR / "agent_harness_cases.json").read_text(encoding="utf-8")
    )
    raw_traces = json.loads(
        (FIXTURES_DIR / "mock_run_traces.json").read_text(encoding="utf-8")
    )
    case = ExpectedCase.model_validate(
        next(item for item in raw_cases if item["case_id"] == case_id)
    )
    trace = RunTrace.model_validate(
        next(item for item in raw_traces if item["case_id"] == case_id)
    )
    return case, trace


def test_normal_case_returns_success() -> None:
    case, trace = load_case_and_trace("refill_father_low_stock")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.task_success is True
    assert result.tool_call_accuracy == 1.0
    assert result.groundedness == 1.0
    assert result.failure_reasons == []


def test_missing_required_tool_reduces_accuracy_and_records_failure() -> None:
    case, trace = load_case_and_trace("refill_father_prescription_expiring")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.task_success is False
    assert result.tool_call_accuracy == 0.8
    assert "missing_required_tool:search_safety_knowledge" in result.failure_reasons


def test_forbidden_phrase_marks_hallucination_and_failure() -> None:
    case, trace = load_case_and_trace("safety_switch_medication")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.hallucination_detected is True
    assert result.task_success is False
    assert "forbidden_phrase:建议换成" in result.failure_reasons


def test_high_risk_case_without_safety_flag_fails_recall() -> None:
    case, trace = load_case_and_trace("safety_increase_dose")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.safety_recall == 0.0
    assert result.task_success is False
    assert "missing_safety_flag:dosage_change_request" in result.failure_reasons


def test_member_mismatch_fails_context_isolation() -> None:
    case, trace = load_case_and_trace("isolation_father_not_mother_context")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.context_isolation_passed is False
    assert "member_id_mismatch" in result.failure_reasons
    assert "cross_member_context" in result.failure_reasons


def test_factual_answer_without_sources_fails_groundedness() -> None:
    case, trace = load_case_and_trace("no_source_inventory_claim")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.groundedness == 0.0
    assert result.hallucination_detected is True
    assert "ungrounded_factual_answer" in result.failure_reasons


def test_missing_required_confirmation_is_reported() -> None:
    case, trace = load_case_and_trace("consultation_mother_missing_tongue_report")

    result = DeterministicEvaluator().evaluate(case, trace)

    assert result.human_confirmation_required is True
    assert result.human_confirmation_present is False
    assert "human_confirmation_missing" in result.failure_reasons


def test_evaluator_does_not_modify_frozen_final_answer() -> None:
    case, trace = load_case_and_trace("refill_father_low_stock")
    original = trace.final_answer.model_dump()

    DeterministicEvaluator().evaluate(case, trace)

    assert trace.final_answer.model_dump() == original
    with pytest.raises(ValidationError):
        trace.final_answer.content = "attempted mutation"

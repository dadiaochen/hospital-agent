from app.safety.final_answer_quality_gate import FinalAnswerQualityGate


def test_quality_gate_requests_at_most_one_model_only_repair() -> None:
    gate = FinalAnswerQualityGate()
    first = gate.review(
        content="草稿已准备", waiting_for_confirmation=True,
        contains_factual_claims=False, claim_count=0, source_count=0,
    )
    second = gate.review(
        content="草稿已准备", waiting_for_confirmation=True,
        contains_factual_claims=False, claim_count=0, source_count=0,
        regeneration_attempts=1,
    )
    assert first.requires_regeneration is True
    assert first.regeneration_attempts == 0
    assert second.requires_regeneration is False
    assert second.hard_failed is False


def test_quality_gate_fails_closed_when_factual_answer_lacks_evidence() -> None:
    result = FinalAnswerQualityGate().review(
        content="已整理结果", waiting_for_confirmation=False,
        contains_factual_claims=True, claim_count=0, source_count=0,
    )
    assert result.passed is False
    assert result.hard_failed is True
    assert result.requires_regeneration is False

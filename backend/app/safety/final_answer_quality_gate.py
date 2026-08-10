"""Deterministic final-answer quality gate with one bounded repair allowance."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinalAnswerQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    hard_failed: bool = False
    requires_regeneration: bool = False
    regeneration_attempts: int = Field(default=0, ge=0, le=1)
    issues: tuple[str, ...] = Field(default_factory=tuple)


class FinalAnswerQualityGate:
    """Checks display readiness after safety and before freezing an answer.

    The gate is deliberately deterministic.  It neither calls tools nor
    introduces medical reasoning; callers may attempt one model-only repair.
    """

    def review(
        self,
        *,
        content: str,
        waiting_for_confirmation: bool,
        contains_factual_claims: bool,
        claim_count: int,
        source_count: int,
        regeneration_attempts: int = 0,
        safety_blocked: bool = False,
    ) -> FinalAnswerQualityResult:
        if safety_blocked:
            return FinalAnswerQualityResult(
                passed=False, hard_failed=True, regeneration_attempts=regeneration_attempts,
                issues=("safety_fail_closed",),
            )
        issues: list[str] = []
        if not content.strip():
            issues.append("empty_content")
        if contains_factual_claims and (not source_count or not claim_count):
            issues.append("unsupported_factual_claim")
        if waiting_for_confirmation and not any(token in content for token in ("确认", "confirm")):
            issues.append("confirmation_instruction_missing")
        if not issues:
            return FinalAnswerQualityResult(passed=True, regeneration_attempts=regeneration_attempts)
        # Source/claim absence cannot be repaired by text-only regeneration.
        hard = "unsupported_factual_claim" in issues
        return FinalAnswerQualityResult(
            passed=False, hard_failed=hard,
            requires_regeneration=not hard and regeneration_attempts == 0,
            regeneration_attempts=regeneration_attempts,
            issues=tuple(issues),
        )


__all__ = ["FinalAnswerQualityGate", "FinalAnswerQualityResult"]

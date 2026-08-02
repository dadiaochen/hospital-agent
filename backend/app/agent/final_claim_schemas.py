"""Structured final-answer contracts for 4D-B2.3.

The final answer is still readable text, but every factual statement that is
meant to be evaluated must also have a structured Claim.  The Claim points to
source IDs; it does not copy an entire database row or a provider response.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, NonEmptyStr


ClaimType = Literal[
    "operational_fact",
    "knowledge_fact",
    "safety_notice",
    "uncertainty_notice",
]
ClaimActionStatus = Literal["none", "draft", "awaiting_confirmation", "executed"]


class FinalClaim(ContractModel):
    """One atomic, source-backed statement in a frozen final answer."""

    claim_id: NonEmptyStr
    fact_key: NonEmptyStr
    subject_id: NonEmptyStr
    value: Any
    source_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    claim_type: ClaimType

    @model_validator(mode="after")
    def validate_value(self) -> "FinalClaim":
        if self.value is None:
            raise ValueError("FinalClaim value cannot be null")
        return self


class AnswerEnvelope(ContractModel):
    """The user-facing text and the Claims produced in the same step."""

    schema_version: Literal["4d-b2.3"] = "4d-b2.3"
    answer_id: NonEmptyStr
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    display_text: NonEmptyStr
    claims: tuple[FinalClaim, ...] = Field(default_factory=tuple)
    waiting_for_user_confirmation: bool
    human_confirmation_present: bool = False
    action_status: ClaimActionStatus
    context_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    dependency_result_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_claim_scope(self) -> "AnswerEnvelope":
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("AnswerEnvelope claim_id values must be unique")
        context_sources = set(self.context_source_ids)
        for claim in self.claims:
            if claim.subject_id != self.member_id:
                raise ValueError("FinalClaim subject_id must match envelope member_id")
            if not set(claim.source_ids).issubset(context_sources):
                raise ValueError(
                    "FinalClaim source_ids must be present in context_source_ids"
                )
        if self.waiting_for_user_confirmation and self.action_status != "awaiting_confirmation":
            raise ValueError(
                "waiting answers must use awaiting_confirmation action_status"
            )
        return self


def build_workflow_claims(
    *,
    run_id: str,
    member_id: str,
    status: str,
    confirmation_state: str,
    source_ids: Iterable[str],
) -> tuple[FinalClaim, ...]:
    """Create conservative operational Claims from structured workflow state.

    This helper never reads or summarizes the natural-language answer. It
    records only facts already represented by the workflow state and binds
    them to the evidence pointers collected during the run.
    """

    unique_source_ids = tuple(dict.fromkeys(source_id for source_id in source_ids if source_id))
    if not unique_source_ids:
        return ()
    return (
        FinalClaim(
            claim_id=f"{run_id}:claim:workflow-status",
            fact_key="workflow.status",
            subject_id=member_id,
            value=status,
            source_ids=unique_source_ids,
            claim_type="operational_fact",
        ),
        FinalClaim(
            claim_id=f"{run_id}:claim:confirmation-state",
            fact_key="workflow.confirmation_state",
            subject_id=member_id,
            value=confirmation_state,
            source_ids=unique_source_ids,
            claim_type="operational_fact",
        ),
    )


__all__ = [
    "AnswerEnvelope",
    "ClaimActionStatus",
    "ClaimType",
    "FinalClaim",
    "build_workflow_claims",
]

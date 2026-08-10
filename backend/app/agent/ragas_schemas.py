"""Stable, dependency-free contracts for offline RAGAS evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.agent.context_schemas import ContractModel, NonEmptyStr


RagasEvaluationStatus = Literal["scored", "skipped", "failed"]


class RagasGenerationEvalInput(ContractModel):
    user_input: NonEmptyStr
    response: NonEmptyStr
    retrieved_contexts: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    reference: NonEmptyStr


class RagasGenerationEvalResult(ContractModel):
    faithfulness: float | None = Field(default=None, ge=0, le=1)
    response_relevancy: float | None = Field(default=None, ge=0, le=1)
    context_recall: float | None = Field(default=None, ge=0, le=1)
    evaluator_model: NonEmptyStr
    ragas_version: NonEmptyStr
    status: RagasEvaluationStatus
    latency_ms: int = Field(default=0, ge=0)
    error: str | None = None


__all__ = [
    "RagasEvaluationStatus",
    "RagasGenerationEvalInput",
    "RagasGenerationEvalResult",
]

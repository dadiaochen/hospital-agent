from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]
RetrievalMode = Literal["keyword", "vector", "hybrid"]
EffectiveRetrievalMode = Literal["keyword", "vector", "hybrid"]
MatchMode = Literal["keyword", "vector"]


class RetrievalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RetrievalRequest(RetrievalContract):
    query: NonEmptyStr
    purpose: NonEmptyStr
    mode: RetrievalMode = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)


class VectorMatch(RetrievalContract):
    document_id: NonEmptyStr
    chunk_id: NonEmptyStr
    score: float = Field(ge=0.0, le=1.0)


class RetrievedChunk(RetrievalContract):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    chunk_id: NonEmptyStr
    document_version: NonEmptyStr
    chunk_version: NonEmptyStr
    title: NonEmptyStr
    category: NonEmptyStr
    source: NonEmptyStr
    safety_level: NonEmptyStr
    chunk_index: int = Field(ge=0)
    content: NonEmptyStr
    keywords: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0)
    purpose: NonEmptyStr
    matched_by: tuple[MatchMode, ...] = Field(min_length=1)


class RetrievalResult(RetrievalContract):
    query: NonEmptyStr
    purpose: NonEmptyStr
    requested_mode: RetrievalMode
    effective_mode: EffectiveRetrievalMode
    fallback_used: bool = False
    fallback_reason: NonEmptyStr | None = None
    evidence_present: bool
    sources: list[RetrievedChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_and_fallback(self) -> "RetrievalResult":
        if self.evidence_present != bool(self.sources):
            raise ValueError("evidence_present must match whether sources are present")
        if self.fallback_used and self.fallback_reason is None:
            raise ValueError("fallback_reason is required when fallback_used is true")
        if not self.fallback_used and self.fallback_reason is not None:
            raise ValueError("fallback_reason requires fallback_used to be true")
        return self


__all__ = [
    "EffectiveRetrievalMode",
    "MatchMode",
    "RetrievedChunk",
    "RetrievalMode",
    "RetrievalRequest",
    "RetrievalResult",
    "VectorMatch",
]

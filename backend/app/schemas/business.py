from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

BusinessDomain = Literal[
    "preconsultation",
    "chronic_care",
    "health_record",
]
ProviderMode = Literal["mock", "sandbox", "real"]
SourceType = Literal[
    "doctor_confirmation",
    "medical_document",
    "structured_database",
    "user_statement",
    "knowledge_base",
    "agent_inference",
]


class BusinessContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceRef(BusinessContractModel):
    """Traceable source reference shared by RAG, tools, and evaluation."""

    source_id: NonEmptyStr
    source_type: SourceType
    document_id: NonEmptyStr | None = None
    document_version: NonEmptyStr | None = None
    chunk_id: NonEmptyStr | None = None
    retrieval_mode: NonEmptyStr | None = None
    provider: NonEmptyStr | None = None
    member_id: NonEmptyStr | None = None
    verified: bool = False
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_provenance(self) -> "SourceRef":
        if self.source_type == "agent_inference" and self.verified:
            raise ValueError("agent inference cannot be marked as a verified fact")

        if self.source_type in {"medical_document", "knowledge_base"}:
            required = {
                "document_id": self.document_id,
                "document_version": self.document_version,
                "retrieval_mode": self.retrieval_mode,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(
                    "document-backed sources require " + ", ".join(missing)
                )

        return self


class BusinessRequestContext(BusinessContractModel):
    """Shared request identity for the three product business lines."""

    business_domain: BusinessDomain
    provider_mode: ProviderMode = "mock"
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    source_refs: list[SourceRef] = Field(default_factory=list)

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.business import BusinessDomain, ProviderMode, SourceRef


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation: str = Field(min_length=1)
    business_domain: BusinessDomain
    provider_mode: ProviderMode = "mock"
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_name: str = Field(min_length=1)
    provider_mode: ProviderMode
    operation: str = Field(min_length=1)
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    retryable: bool = False
    degraded: bool = False
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_degraded_response(self) -> "ProviderResponse":
        if self.degraded and not self.fallback_reason:
            raise ValueError(
                "degraded provider responses require fallback_reason"
            )
        if self.fallback_reason and not self.degraded:
            raise ValueError(
                "fallback_reason requires degraded provider response"
            )
        return self

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.reliability import ErrorCategory, RETRYABLE_ERROR_CATEGORIES
from app.schemas.business import BusinessDomain, ProviderMode, SourceRef


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation: str = Field(min_length=1)
    business_domain: BusinessDomain
    provider_mode: ProviderMode = "mock"
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProviderRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=5)
    backoff_ms: int = Field(default=0, ge=0, le=5000)


class ProviderAttemptTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    attempt_no: int = Field(ge=1)
    success: bool
    latency_ms: int = Field(ge=0)
    error_type: str | None = None
    error_category: ErrorCategory | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_status(self) -> "ProviderAttemptTrace":
        if self.success and any(
            (self.error_type is not None, self.error_category is not None, self.retryable)
        ):
            raise ValueError("successful provider attempts cannot carry errors")
        if not self.success and (
            self.error_type is None or self.error_category is None
        ):
            raise ValueError("failed provider attempts require normalized errors")
        return self


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_name: str = Field(min_length=1)
    provider_mode: ProviderMode
    operation: str = Field(min_length=1)
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    error_type: str | None = None
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    retryable: bool = False
    degraded: bool = False
    fallback_reason: str | None = None
    latency_ms: int = Field(default=0, ge=0)
    attempts: list[ProviderAttemptTrace] = Field(default_factory=list)

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
        if self.success:
            if any(
                (
                    self.error_type is not None,
                    self.error_category is not None,
                    self.error_message is not None,
                    self.retryable,
                    self.degraded,
                )
            ):
                raise ValueError("successful provider responses cannot carry errors")
        elif self.error_type is None or self.error_category is None:
            raise ValueError("failed provider responses require normalized errors")
        if not self.success and (self.data or self.source_refs):
            raise ValueError(
                "failed provider responses cannot carry data or source evidence"
            )
        if self.retryable and self.error_category not in RETRYABLE_ERROR_CATEGORIES:
            raise ValueError("only recoverable provider errors may be retryable")
        return self


ProviderStatus = Literal["success", "degraded"]


__all__ = [
    "ProviderAttemptTrace",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderRetryPolicy",
    "ProviderStatus",
]

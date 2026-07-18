from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]
ModelMessageRole = Literal["system", "user", "assistant"]


class ModelGatewayContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
        protected_namespaces=(),
    )


class ModelMessage(ModelGatewayContract):
    role: ModelMessageRole
    content: NonEmptyStr


class ModelCallRequest(ModelGatewayContract):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    purpose: NonEmptyStr
    messages: tuple[ModelMessage, ...] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=512, ge=1, le=4096)


class ProviderRawResponse(ModelGatewayContract):
    provider_name: NonEmptyStr
    model_name: NonEmptyStr
    content: NonEmptyStr
    provider_request_id: NonEmptyStr | None = None


class ModelProviderAttemptTrace(ModelGatewayContract):
    provider_name: NonEmptyStr
    model_name: NonEmptyStr
    success: bool
    schema_valid: bool
    safety_passed: bool
    safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    latency_ms: int = Field(ge=0)
    error_type: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_attempt_status(self) -> "ModelProviderAttemptTrace":
        if self.success:
            if not self.schema_valid or not self.safety_passed:
                raise ValueError("successful attempts require valid schema and safety")
            if self.error_type is not None:
                raise ValueError("successful attempts cannot contain error_type")
        elif self.error_type is None:
            raise ValueError("failed attempts require error_type")
        return self


class ModelCallTrace(ModelGatewayContract):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    purpose: NonEmptyStr
    requested_provider: NonEmptyStr
    effective_provider: NonEmptyStr | None = None
    success: bool
    schema_valid: bool
    safety_passed: bool
    fallback_used: bool = False
    fallback_reason: NonEmptyStr | None = None
    latency_ms: int = Field(ge=0)
    attempts: tuple[ModelProviderAttemptTrace, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_call_status(self) -> "ModelCallTrace":
        if self.fallback_used != (self.fallback_reason is not None):
            raise ValueError("fallback_used and fallback_reason must be set together")
        if self.success:
            if self.effective_provider is None:
                raise ValueError("successful calls require effective_provider")
            if not self.schema_valid or not self.safety_passed:
                raise ValueError("successful calls require valid schema and safety")
        elif self.effective_provider is not None:
            raise ValueError("failed calls cannot have effective_provider")
        return self


OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelCallResult(ModelGatewayContract, Generic[OutputT]):
    output: OutputT | None = None
    trace: ModelCallTrace

    @model_validator(mode="after")
    def validate_output_status(self) -> "ModelCallResult[OutputT]":
        if self.trace.success != (self.output is not None):
            raise ValueError("output must be present exactly when the call succeeds")
        return self


__all__ = [
    "ModelCallRequest",
    "ModelCallResult",
    "ModelCallTrace",
    "ModelGatewayContract",
    "ModelMessage",
    "ModelMessageRole",
    "ModelProviderAttemptTrace",
    "ProviderRawResponse",
]

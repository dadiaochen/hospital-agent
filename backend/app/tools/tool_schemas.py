from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.context_schemas import ContractModel, ExecutionAgentRole, NonEmptyStr
from app.agent.run_trace_schemas import ToolCallTrace


ToolPermissionScope = Literal[
    "profile:read",
    "prescription:read",
    "medicine_box:read",
    "pharmacy:read",
    "safety:read",
    "draft:create",
]


class RetryPolicy(ContractModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_ms: int = Field(default=0, ge=0)


class ToolSpec(ContractModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: NonEmptyStr
    description: NonEmptyStr
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: ToolPermissionScope
    allowed_agent_roles: list[ExecutionAgentRole] = Field(min_length=1)
    timeout_ms: int = Field(default=1000, ge=1)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False

    @field_validator("input_schema", "output_schema")
    @classmethod
    def require_pydantic_schema(cls, value: type[BaseModel]) -> type[BaseModel]:
        if not isinstance(value, type) or not issubclass(value, BaseModel):
            raise ValueError("tool schemas must be Pydantic BaseModel subclasses")
        return value


class ToolExecutionContext(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    agent_role: ExecutionAgentRole
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    human_confirmation_granted: bool = False


class ToolResult(ContractModel):
    tool_name: NonEmptyStr
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error_type: NonEmptyStr | None = None
    error_message: str | None = None
    fallback_action: NonEmptyStr | None = None
    latency_ms: int = Field(ge=0)
    schema_valid: bool
    requires_human_confirmation: bool
    evidence_present: bool
    source_name: NonEmptyStr | None = None

    @classmethod
    def failure(
        cls,
        *,
        tool_name: str,
        error_type: str,
        error_message: str,
        fallback_action: str,
        latency_ms: int,
        schema_valid: bool = True,
        requires_human_confirmation: bool = False,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            success=False,
            output={},
            error_type=error_type,
            error_message=error_message,
            fallback_action=fallback_action,
            latency_ms=latency_ms,
            schema_valid=schema_valid,
            requires_human_confirmation=requires_human_confirmation,
            evidence_present=False,
            source_name=None,
        )

    def to_tool_call_trace(self, *, member_id: str) -> ToolCallTrace:
        source_id = self.output.get("source_id")
        return ToolCallTrace(
            tool_name=self.tool_name,
            member_id=member_id,
            source_id=source_id if isinstance(source_id, str) and source_id else None,
            source_name=self.source_name,
            success=self.success,
            schema_valid=self.schema_valid,
            evidence_present=self.evidence_present,
        )

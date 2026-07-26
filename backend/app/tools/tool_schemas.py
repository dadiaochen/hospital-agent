from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.business import ProviderMode, SourceRef


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
AgentRole = Literal[
    "Planner",
    "ProfileAgent",
    "RefillAgent",
    "PharmacyAgent",
    "ReminderAgent",
    "SafetyAgent",
]


class ToolContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ToolPermissionScope = NonEmptyStr


class RetryPolicy(ToolContractModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_ms: int = Field(default=0, ge=0)


class ToolSpec(ToolContractModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: NonEmptyStr
    tool_version: NonEmptyStr = "v1"
    description: NonEmptyStr
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: ToolPermissionScope
    allowed_agent_roles: list[AgentRole] = Field(min_length=1)
    timeout_ms: int = Field(default=1000, ge=1)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False
    read_only: bool = True

    @field_validator("input_schema", "output_schema")
    @classmethod
    def require_pydantic_schema(cls, value: type[BaseModel]) -> type[BaseModel]:
        if not isinstance(value, type) or not issubclass(value, BaseModel):
            raise ValueError("tool schemas must be Pydantic BaseModel subclasses")
        return value


class ToolExecutionContext(ToolContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr | None = None
    member_id: NonEmptyStr
    agent_role: AgentRole
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    human_confirmation_granted: bool = False
    provider_mode: ProviderMode = "mock"


class ToolResult(ToolContractModel):
    tool_name: NonEmptyStr
    tool_version: NonEmptyStr = "v1"
    provider_mode: ProviderMode = "mock"
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    run_id: NonEmptyStr | None = None
    agent_role: AgentRole | None = None
    member_id: NonEmptyStr | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    error_type: NonEmptyStr | None = None
    error_message: str | None = None
    fallback_action: NonEmptyStr | None = None
    latency_ms: int = Field(ge=0)
    schema_valid: bool
    requires_human_confirmation: bool
    evidence_present: bool
    evidence_refs: list[SourceRef] = Field(default_factory=list)
    retryable: bool = False
    source_name: NonEmptyStr | None = None
    permission_scope: NonEmptyStr | None = None
    read_only: bool = True

    @property
    def tool_output(self) -> dict[str, Any] | None:
        """Compatibility view for database-backed tool consumers."""
        return self.output if self.success else None

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
        run_id: str | None = None,
        agent_role: AgentRole | None = None,
        member_id: str | None = None,
        tool_input: dict[str, Any] | None = None,
        permission_scope: str | None = None,
        read_only: bool = True,
        tool_version: str = "v1",
        provider_mode: ProviderMode = "mock",
        retryable: bool = False,
        evidence_refs: list[SourceRef] | None = None,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            tool_version=tool_version,
            provider_mode=provider_mode,
            success=False,
            output={},
            error_type=error_type,
            error_message=error_message,
            fallback_action=fallback_action,
            latency_ms=latency_ms,
            schema_valid=schema_valid,
            requires_human_confirmation=requires_human_confirmation,
            evidence_present=False,
            evidence_refs=evidence_refs or [],
            retryable=retryable,
            source_name=None,
            run_id=run_id,
            agent_role=agent_role,
            member_id=member_id,
            tool_input=tool_input or {},
            permission_scope=permission_scope,
            read_only=read_only,
        )

    def to_tool_call_trace(self, member_id: str | None = None):
        from app.agent.run_trace_schemas import ToolCallTrace

        trace_member_id = member_id or self.member_id
        if trace_member_id is None:
            raise ValueError("member_id is required to build ToolCallTrace")
        source_id = self.output.get("source_id")
        return ToolCallTrace(
            tool_name=self.tool_name,
            member_id=trace_member_id,
            source_id=source_id if isinstance(source_id, str) and source_id else None,
            source_name=self.source_name,
            success=self.success,
            schema_valid=self.schema_valid,
            evidence_present=self.evidence_present,
        )

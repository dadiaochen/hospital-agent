from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class RetryPolicy(ToolContractModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_seconds: float = Field(default=0.0, ge=0.0)


class ToolSpec(ToolContractModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: str = Field(min_length=1)
    allowed_agent_roles: tuple[AgentRole, ...] = Field(default_factory=tuple)
    timeout: float = Field(default=10.0, gt=0.0)
    timeout_ms: int = Field(default=10_000, gt=0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False
    read_only: bool = True


class ToolExecutionContext(ToolContractModel):
    run_id: str = Field(min_length=1)
    agent_role: AgentRole
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)


class ToolResult(ToolContractModel):
    tool_name: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_role: AgentRole
    member_id: str = Field(min_length=1)
    tool_input: dict[str, Any]
    tool_output: dict[str, Any] | None = None
    latency_ms: int = Field(ge=0)
    success: bool
    error_message: str | None = None
    error_type: str | None = None
    fallback_action: str | None = None
    schema_valid: bool
    evidence_present: bool = False
    source_id: str | None = None
    source_name: str | None = None
    permission_scope: str
    requires_human_confirmation: bool = False
    read_only: bool = True

    def to_tool_call_trace(self, member_id: str | None = None):
        from app.agent.run_trace_schemas import ToolCallTrace

        return ToolCallTrace(
            tool_name=self.tool_name,
            member_id=member_id or self.member_id,
            source_id=self.source_id,
            source_name=self.source_name or self.tool_name,
            success=self.success,
            schema_valid=self.schema_valid,
            evidence_present=self.evidence_present,
        )

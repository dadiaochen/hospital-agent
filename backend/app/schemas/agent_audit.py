from datetime import datetime
from typing import Any

from app.schemas.common import ApiSchema


class AgentRunListQuery(ApiSchema):
    member_id: str | None = None


class AgentRunResponse(ApiSchema):
    id: str
    user_id: str
    member_id: str | None
    user_goal: str
    intent: str | None
    status: str
    final_answer: str | None
    need_human_confirmation: bool
    safety_result: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    step_count: int
    task_success: bool | None
    groundedness_score: float | None
    hallucination_flag: bool
    human_confirmation_rate: float | None


class AgentRunListResponse(ApiSchema):
    items: list[AgentRunResponse]


class AgentToolCallResponse(ApiSchema):
    id: str
    run_id: str
    agent_role: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any] | None
    latency_ms: int | None
    success: bool
    error_message: str | None
    error_type: str | None
    fallback_action: str | None
    schema_valid: bool


class AgentToolCallListResponse(ApiSchema):
    items: list[AgentToolCallResponse]

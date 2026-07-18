from typing import Literal

from pydantic import Field, field_validator

from app.agent.context_schemas import RAGSourceRef, RunSummary, ToolEvidenceRef
from app.agent.eval_schemas import EvaluationResult
from app.agent.model_gateway_schemas import ModelCallTrace
from app.agent.run_trace_schemas import RunTrace, SafetyTrace
from app.schemas.agent_audit import AgentRunResponse
from app.schemas.common import ApiSchema


class AgentRunCreateRequest(ApiSchema):
    member_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=120)
    user_input: str = Field(min_length=1, max_length=4000)
    medication_name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    human_confirmation_granted: Literal[False] = False

    @field_validator(
        "member_id",
        "idempotency_key",
        "user_input",
        "medication_name",
        "city",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AgentRunContinueRequest(ApiSchema):
    idempotency_key: str = Field(min_length=1, max_length=120)
    confirmation_message: str = Field(min_length=1, max_length=1000)
    human_confirmation_granted: Literal[True]

    @field_validator("idempotency_key", "confirmation_message")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AgentRunArtifactsResponse(ApiSchema):
    run_id: str
    task_id: str
    status: str
    run_trace: RunTrace
    model_call_trace: ModelCallTrace
    run_summary: RunSummary
    tool_evidence_refs: tuple[ToolEvidenceRef, ...]
    rag_source_refs: tuple[RAGSourceRef, ...]
    safety_trace: SafetyTrace
    evaluation_result: EvaluationResult
    resumed_from_run_id: str | None
    restored_source_ids: tuple[str, ...]
    external_action_status: Literal["not_submitted"]


class AgentRunExecutionResponse(ApiSchema):
    run: AgentRunResponse
    artifacts: AgentRunArtifactsResponse
    idempotent_replay: bool


__all__ = [
    "AgentRunArtifactsResponse",
    "AgentRunContinueRequest",
    "AgentRunCreateRequest",
    "AgentRunExecutionResponse",
]

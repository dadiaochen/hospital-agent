from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.agent.context_schemas import RunSummary
from app.agent.eval_schemas import EvaluationResult
from app.agent.run_trace_schemas import RunTrace
from app.schemas.business import BusinessDomain, ProviderMode, SourceRef
from app.schemas.common import ApiSchema


class BusinessTaskCreateRequest(ApiSchema):
    business_domain: BusinessDomain
    member_id: str = Field(min_length=1)
    user_input: str = Field(min_length=1)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=120)
    provider_mode: ProviderMode = "mock"
    human_confirmation_granted: Literal[False] = False


class BusinessTaskConfirmRequest(ApiSchema):
    human_confirmation_granted: Literal[True] = True
    idempotency_key: str = Field(min_length=1, max_length=120)


class BusinessTaskSummaryResponse(ApiSchema):
    id: str
    user_id: str
    member_id: str
    business_domain: str
    intent: str
    status: str
    user_input: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    need_human_confirmation: bool
    confirmed_at: datetime | None = None
    current_run_id: str | None = None
    degraded: bool
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class BusinessTaskExecutionResponse(ApiSchema):
    task: BusinessTaskSummaryResponse
    run_id: str | None = None
    final_answer: str
    status: str
    need_human_confirmation: bool
    confirmation_request: dict[str, Any]
    confirmation_result: dict[str, Any]
    safety_flags: list[str]
    source_refs: list[SourceRef]
    tool_calls: list[dict[str, Any]]
    provider_calls: list[dict[str, Any]]
    degraded: bool
    run_trace: RunTrace | None = None
    run_summary: RunSummary | None = None
    evaluation_result: EvaluationResult | None = None
    idempotent_replay: bool = False


class BusinessTaskListResponse(ApiSchema):
    items: list[BusinessTaskSummaryResponse]
    total: int


class SourceReferenceResponse(ApiSchema):
    id: str
    user_id: str
    task_id: str
    run_id: str | None = None
    source_id: str
    source_type: str
    document_id: str | None = None
    document_version: str | None = None
    chunk_id: str | None = None
    retrieval_mode: str | None = None
    provider: str | None = None
    member_id: str | None = None
    verified: bool
    source_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

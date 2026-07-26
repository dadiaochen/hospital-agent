from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HealthRecordEvent
from app.providers.mock import build_mock_provider_registry
from app.providers.registry import ProviderRegistry
from app.providers.schemas import ProviderRequest
from app.rag.retrieval_schemas import RetrievalRequest
from app.rag.retriever import Retriever, create_knowledge_retriever
from app.schemas.business import BusinessDomain, SourceRef
from app.tools.tool_registry import ToolExecutionError, ToolRegistry
from app.tools.tool_schemas import (
    AgentRole,
    RetryPolicy,
    ToolContractModel,
    ToolExecutionContext,
    ToolSpec,
)


class ProviderToolInput(ToolContractModel):
    operation: str = Field(min_length=1)
    business_domain: BusinessDomain
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProviderToolOutput(ToolContractModel):
    source_name: str = Field(min_length=1)
    evidence_present: bool
    provider_name: str = Field(min_length=1)
    provider_mode: Literal["mock", "sandbox", "real"]
    operation: str = Field(min_length=1)
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    retryable: bool = False
    degraded: bool = False
    fallback_reason: str | None = None
    provider_call: dict[str, Any]


class KnowledgeSearchInput(ToolContractModel):
    query: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    limit: int = Field(default=8, ge=1, le=50)


class KnowledgeSearchOutput(ToolContractModel):
    source_name: str = "knowledge_base"
    evidence_present: bool
    requested_mode: Literal["keyword", "vector", "hybrid"]
    effective_mode: Literal["keyword", "vector", "hybrid"]
    fallback_used: bool = False
    fallback_reason: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class HealthRecordDraftInput(ToolContractModel):
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_document_id: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class HealthRecordDraftOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = "health_record_events"
    evidence_present: bool = True
    event_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    status: Literal["draft"] = "draft"
    need_human_confirmation: bool = True
    confirmed_at: str
    local_confirmation_recorded: bool = True
    external_action_status: Literal["not_submitted"] = "not_submitted"
    idempotent_replay: bool = False
    source_refs: list[SourceRef] = Field(default_factory=list)


def register_business_tools(
    registry: ToolRegistry,
    db: Session,
    *,
    provider_registry: ProviderRegistry | None = None,
    knowledge_retriever: Retriever | None = None,
) -> None:
    providers = provider_registry or build_mock_provider_registry()
    retriever = knowledge_retriever or create_knowledge_retriever(db)

    provider_specs: tuple[
        tuple[str, str, str, list[AgentRole], str],
        ...,
    ] = (
        (
            "hospital_list_departments",
            "hospital",
            "list_departments",
            ["Planner"],
            "读取医院科室候选，不生成诊断。",
        ),
        (
            "hospital_list_slots",
            "hospital",
            "list_slots",
            ["Planner"],
            "读取可选就诊时段，不执行挂号。",
        ),
        (
            "consultation_prepare_draft",
            "online_consultation",
            "prepare_draft",
            ["RefillAgent"],
            "整理线上复诊材料草稿，不提交问诊。",
        ),
        (
            "pharmacy_search_inventory",
            "pharmacy",
            "search_inventory",
            ["PharmacyAgent"],
            "查询购药候选和履约方式，不创建订单。",
        ),
        (
            "geo_resolve",
            "geo",
            "resolve",
            ["Planner", "PharmacyAgent"],
            "解析服务区域，用于候选服务筛选。",
        ),
        (
            "notification_prepare_reminder",
            "notification",
            "prepare_reminder",
            ["ReminderAgent"],
            "生成用药提醒草稿，不直接创建系统提醒。",
        ),
        (
            "parse_medical_document",
            "medical_document_parser",
            "parse",
            ["ProfileAgent"],
            "解析医疗文档内容，不输出诊断结论。",
        ),
        (
            "inspect_medical_image",
            "medical_vision",
            "inspect_quality",
            ["ProfileAgent"],
            "检查医疗图片可读性和可观察内容，不输出诊断结论。",
        ),
    )

    for tool_name, provider_name, operation, roles, description in provider_specs:
        registry.register(
            ToolSpec(
                name=tool_name,
                description=description,
                input_schema=ProviderToolInput,
                output_schema=ProviderToolOutput,
                permission_scope=f"provider:{provider_name}:{operation}",
                allowed_agent_roles=roles,
                timeout_ms=3000,
                retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
                requires_human_confirmation=False,
                read_only=True,
            ),
            _provider_handler(
                providers,
                provider_name=provider_name,
                expected_operation=operation,
            ),
        )

    registry.register(
        ToolSpec(
            name="search_business_knowledge",
            description="检索业务流程、医疗安全和报告解释知识，返回可追溯来源。",
            input_schema=KnowledgeSearchInput,
            output_schema=KnowledgeSearchOutput,
            permission_scope="knowledge:read",
            allowed_agent_roles=[
                "Planner",
                "ProfileAgent",
                "RefillAgent",
                "PharmacyAgent",
                "ReminderAgent",
                "SafetyAgent",
            ],
            timeout_ms=3000,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
            read_only=True,
        ),
        _knowledge_handler(retriever),
    )

    registry.register(
        ToolSpec(
            name="create_health_record_draft",
            description="在用户确认后创建健康档案事件草稿，不写入外部医院系统。",
            input_schema=HealthRecordDraftInput,
            output_schema=HealthRecordDraftOutput,
            permission_scope="health_record:draft:create",
            allowed_agent_roles=["ProfileAgent"],
            timeout_ms=2000,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=True,
            read_only=False,
        ),
        _health_record_draft_handler(db),
    )


def _provider_handler(
    providers: ProviderRegistry,
    *,
    provider_name: str,
    expected_operation: str,
):
    def handler(
        raw_input: ToolContractModel,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        tool_input = cast(ProviderToolInput, raw_input)
        _validate_scope(
            context,
            user_id=tool_input.user_id,
            member_id=tool_input.member_id,
        )
        if tool_input.operation != expected_operation:
            raise ToolExecutionError(
                f"operation must be {expected_operation}",
                error_type="input_scope_error",
                fallback_action="fix_tool_input",
            )

        request = ProviderRequest(
            operation=tool_input.operation,
            business_domain=tool_input.business_domain,
            provider_mode=context.provider_mode,
            user_id=tool_input.user_id,
            member_id=tool_input.member_id,
            payload=tool_input.payload,
        )
        try:
            response = providers.invoke(provider_name, request)
        except KeyError as exc:
            raise ToolExecutionError(
                str(exc),
                error_type="provider_unavailable",
                fallback_action="use_local_draft_or_manual_review",
            ) from exc

        response_payload = response.model_dump(mode="json")
        return {
            "source_name": provider_name,
            "evidence_present": bool(response.source_refs),
            **response_payload,
            "provider_call": {
                "provider_name": provider_name,
                "provider_mode": response.provider_mode,
                "operation": request.operation,
                "request_payload": request.model_dump(mode="json"),
                "response_payload": response_payload,
                "success": response.success,
                "retryable": response.retryable,
                "degraded": response.degraded,
                "fallback_reason": response.fallback_reason,
            },
        }

    return handler


def _knowledge_handler(retriever: Retriever):
    def handler(
        raw_input: ToolContractModel,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        tool_input = cast(KnowledgeSearchInput, raw_input)
        result = retriever.retrieve(
            RetrievalRequest(
                query=tool_input.query,
                purpose=tool_input.purpose,
                mode=tool_input.mode,
                limit=tool_input.limit,
            )
        )
        source_refs = [
            SourceRef(
                source_id=source.source_id,
                source_type="knowledge_base",
                document_id=source.document_id,
                document_version=source.document_version,
                chunk_id=source.chunk_id,
                retrieval_mode=result.effective_mode,
                provider=result.retrieval_provider,
                member_id=context.member_id,
                verified=True,
                source_metadata={
                    "matched_by": list(source.matched_by),
                    "fallback_used": result.fallback_used,
                    "fallback_reason": result.fallback_reason,
                    "embedding_model": result.embedding_model,
                    "embedding_dimension": result.embedding_dimension,
                    "embedding_schema_version": result.embedding_schema_version,
                },
            )
            for source in result.sources
        ]
        return {
            "source_name": "knowledge_base",
            "evidence_present": result.evidence_present,
            "requested_mode": result.requested_mode,
            "effective_mode": result.effective_mode,
            "fallback_used": result.fallback_used,
            "fallback_reason": result.fallback_reason,
            "sources": [
                source.model_dump(mode="json") for source in result.sources
            ],
            "source_refs": [
                source_ref.model_dump(mode="json")
                for source_ref in source_refs
            ],
        }

    return handler


def _health_record_draft_handler(db: Session):
    def handler(
        raw_input: ToolContractModel,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        tool_input = cast(HealthRecordDraftInput, raw_input)
        _validate_scope(
            context,
            user_id=tool_input.user_id,
            member_id=tool_input.member_id,
        )
        if not context.human_confirmation_granted:
            raise ToolExecutionError(
                "health record draft requires explicit user confirmation",
                error_type="human_confirmation_required",
                fallback_action="require_human_confirmation",
            )

        existing = db.scalar(
            select(HealthRecordEvent).where(
                HealthRecordEvent.user_id == tool_input.user_id,
                HealthRecordEvent.member_id == tool_input.member_id,
                HealthRecordEvent.idempotency_key == tool_input.idempotency_key,
            )
        )
        if existing is not None:
            return _health_record_output(
                existing,
                source_refs=tool_input.source_refs,
                idempotent_replay=True,
            )

        now = datetime.now(timezone.utc)
        event = HealthRecordEvent(
            user_id=tool_input.user_id,
            member_id=tool_input.member_id,
            source_document_id=tool_input.source_document_id,
            event_type=tool_input.event_type,
            summary=tool_input.summary,
            idempotency_key=tool_input.idempotency_key,
            structured_data=tool_input.payload,
            source_refs=[
                source.model_dump(mode="json")
                for source in tool_input.source_refs
            ],
            status="draft",
            need_human_confirmation=True,
            confirmed_at=now,
            external_action_status="not_submitted",
        )
        db.add(event)
        db.flush()
        result = _health_record_output(
            event,
            source_refs=tool_input.source_refs,
            idempotent_replay=False,
        )
        db.commit()
        return result

    return handler


def _health_record_output(
    event: HealthRecordEvent,
    *,
    source_refs: list[SourceRef],
    idempotent_replay: bool,
) -> dict[str, Any]:
    confirmed_at = event.confirmed_at or datetime.now(timezone.utc)
    event_source = SourceRef(
        source_id=f"health_record_event:{event.id}",
        source_type="structured_database",
        provider="local_database",
        member_id=event.member_id,
        verified=True,
    )
    combined_refs = [*source_refs, event_source]
    return {
        "source_id": event_source.source_id,
        "source_name": "health_record_events",
        "evidence_present": True,
        "event_id": event.id,
        "member_id": event.member_id,
        "event_type": event.event_type,
        "status": "draft",
        "need_human_confirmation": True,
        "confirmed_at": confirmed_at.isoformat(),
        "local_confirmation_recorded": True,
        "external_action_status": "not_submitted",
        "idempotent_replay": idempotent_replay,
        "source_refs": [
            source.model_dump(mode="json") for source in combined_refs
        ],
    }


def _validate_scope(
    context: ToolExecutionContext,
    *,
    user_id: str,
    member_id: str,
) -> None:
    if context.user_id is not None and context.user_id != user_id:
        raise ToolExecutionError(
            "tool user_id does not match execution context",
            error_type="scope_violation",
            fallback_action="deny_cross_user_access",
        )
    if context.member_id != member_id:
        raise ToolExecutionError(
            "tool member_id does not match execution context",
            error_type="scope_violation",
            fallback_action="deny_cross_member_access",
        )


__all__ = [
    "HealthRecordDraftInput",
    "HealthRecordDraftOutput",
    "KnowledgeSearchInput",
    "KnowledgeSearchOutput",
    "ProviderToolInput",
    "ProviderToolOutput",
    "register_business_tools",
]

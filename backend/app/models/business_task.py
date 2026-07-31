from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin


class BusinessTask(IDMixin, TimestampMixin, Base):
    __tablename__ = "business_tasks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_business_tasks_user_idempotency",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    business_domain: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_mode: Mapped[str] = mapped_column(String(20), default="mock", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    need_human_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), index=True
    )
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmation_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class ProviderCall(IDMixin, TimestampMixin, Base):
    __tablename__ = "provider_calls"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("business_tasks.id"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(160))
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class SourceReference(IDMixin, TimestampMixin, Base):
    __tablename__ = "source_references"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("business_tasks.id"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(120), index=True)
    document_version: Mapped[str | None] = mapped_column(String(40))
    chunk_id: Mapped[str | None] = mapped_column(String(120))
    retrieval_mode: Mapped[str | None] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(120))
    member_id: Mapped[str | None] = mapped_column(
        ForeignKey("family_members.id"), index=True
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class MedicalDocument(IDMixin, TimestampMixin, Base):
    __tablename__ = "medical_documents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    object_uri: Mapped[str | None] = mapped_column(String(500))
    source_text: Mapped[str | None] = mapped_column(Text)
    parser_provider: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="uploaded", nullable=False)
    extracted_content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    document_version: Mapped[str] = mapped_column(String(40), default="1.0", nullable=False)
    need_human_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HealthRecordEvent(IDMixin, TimestampMixin, Base):
    __tablename__ = "health_record_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "member_id",
            "idempotency_key",
            name="uq_health_record_events_member_idempotency",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("medical_documents.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    structured_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_refs: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    need_human_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_action_status: Mapped[str] = mapped_column(
        String(40), default="not_submitted", nullable=False
    )

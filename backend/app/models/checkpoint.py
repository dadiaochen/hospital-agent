"""Authoritative task checkpoint, confirmation, and preference models.

These rows are the durable boundary between one run's working state and a
later continuation run.  Redis only receives the serialized checkpoint
projection; it is never the source of truth for any of these records.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin


class TaskCheckpoint(IDMixin, TimestampMixin, Base):
    """One immutable, versioned checkpoint produced by a completed run."""

    __tablename__ = "task_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "checkpoint_version",
            name="uq_task_checkpoints_task_version",
        ),
        UniqueConstraint(
            "task_id",
            "run_id",
            name="uq_task_checkpoints_task_run",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("business_tasks.id"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), index=True
    )
    checkpoint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confirmation_state: Mapped[str] = mapped_column(String(40), nullable=False)
    confirmation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    step_progress: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    run_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    frozen_artifacts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_refs: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)


class TaskConfirmationRecord(IDMixin, TimestampMixin, Base):
    """Auditable state transition for a task's confirmation state machine."""

    __tablename__ = "task_confirmation_records"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "action",
            "idempotency_key",
            "draft_version",
            name="uq_task_confirmation_action_idempotency",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("business_tasks.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    draft_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_state: Mapped[str] = mapped_column(String(40), nullable=False)
    next_state: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False
    )
    human_confirmation_present: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ConfirmedPreference(IDMixin, TimestampMixin, Base):
    """A user-confirmed, member-scoped preference with an audit trail."""

    __tablename__ = "confirmed_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_confirmed_preferences_user_idempotency",
        ),
        UniqueConstraint(
            "user_id",
            "member_id",
            "preference_type",
            "preference_version",
            name="uq_confirmed_preferences_member_type_version",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(
        ForeignKey("family_members.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("business_tasks.id"), nullable=False, index=True
    )
    created_by_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    confirmation_record_id: Mapped[str] = mapped_column(
        ForeignKey("task_confirmation_records.id"), nullable=False, index=True
    )
    preference_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    preference_value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    preference_version: Mapped[int] = mapped_column(Integer, nullable=False)
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    revocable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

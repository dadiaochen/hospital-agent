from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.user import FamilyMember, User


class AgentMemory(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_memories"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("family_members.id"), index=True)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str | None] = mapped_column(String(120))

    user: Mapped["User"] = relationship(back_populates="agent_memories")
    member: Mapped["FamilyMember | None"] = relationship(back_populates="agent_memories")


class AgentRun(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("family_members.id"), index=True)
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text)
    need_human_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    step_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_success: Mapped[bool | None] = mapped_column(Boolean)
    groundedness_score: Mapped[float | None] = mapped_column(Float)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_confirmation_rate: Mapped[float | None] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="agent_runs")
    member: Mapped["FamilyMember | None"] = relationship(back_populates="agent_runs")
    tool_calls: Mapped[list["AgentToolCall"]] = relationship(back_populates="run")


class AgentToolCall(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_tool_calls"

    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    agent_role: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tool_input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tool_output: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(80))
    fallback_action: Mapped[str | None] = mapped_column(String(120))
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")

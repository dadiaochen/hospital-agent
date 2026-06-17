from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.agent_log import AgentMemory, AgentRun
    from app.models.medication import MedicineBoxItem, Prescription, PurchaseRecord
    from app.models.plans import ConsultationDraft, FollowUpTask, MedicationReminder, PurchasePlan, RefillPlan


class User(IDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    family_members: Mapped[list["FamilyMember"]] = orm_relationship(back_populates="user")
    agent_memories: Mapped[list["AgentMemory"]] = orm_relationship(back_populates="user")
    agent_runs: Mapped[list["AgentRun"]] = orm_relationship(back_populates="user")


class FamilyMember(IDMixin, TimestampMixin, Base):
    __tablename__ = "family_members"
    __table_args__ = (UniqueConstraint("user_id", "relationship", name="uq_family_member_user_relationship"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    birthday: Mapped[date | None] = mapped_column(Date)
    default_address: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = orm_relationship(back_populates="family_members")
    health_profile: Mapped["HealthProfile | None"] = orm_relationship(back_populates="member", uselist=False)
    medicine_box_items: Mapped[list["MedicineBoxItem"]] = orm_relationship(back_populates="member")
    prescriptions: Mapped[list["Prescription"]] = orm_relationship(back_populates="member")
    purchase_records: Mapped[list["PurchaseRecord"]] = orm_relationship(back_populates="member")
    refill_plans: Mapped[list["RefillPlan"]] = orm_relationship(back_populates="member")
    consultation_drafts: Mapped[list["ConsultationDraft"]] = orm_relationship(back_populates="member")
    purchase_plans: Mapped[list["PurchasePlan"]] = orm_relationship(back_populates="member")
    medication_reminders: Mapped[list["MedicationReminder"]] = orm_relationship(back_populates="member")
    follow_up_tasks: Mapped[list["FollowUpTask"]] = orm_relationship(back_populates="member")
    agent_memories: Mapped[list["AgentMemory"]] = orm_relationship(back_populates="member")
    agent_runs: Mapped[list["AgentRun"]] = orm_relationship(back_populates="member")


class HealthProfile(IDMixin, TimestampMixin, Base):
    __tablename__ = "health_profiles"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), unique=True, nullable=False)
    chronic_disease_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    current_medications: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    health_notes: Mapped[str | None] = mapped_column(Text)
    safety_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    member: Mapped["FamilyMember"] = orm_relationship(back_populates="health_profile")

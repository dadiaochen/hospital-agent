from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.medication import MedicineBoxItem, Prescription
    from app.models.pharmacy import Pharmacy
    from app.models.user import FamilyMember


class HumanConfirmationMixin:
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    need_human_confirmation: Mapped[bool] = mapped_column(default=True, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_note: Mapped[str | None] = mapped_column(Text)


class RefillPlan(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    __tablename__ = "refill_plans"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    prescription_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    remaining_days: Mapped[int | None] = mapped_column(Integer)
    plan_detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    safety_note: Mapped[str | None] = mapped_column(Text)
    doctor_confirmation_required: Mapped[bool] = mapped_column(default=True, nullable=False)

    member: Mapped["FamilyMember"] = relationship(back_populates="refill_plans")
    prescription: Mapped["Prescription | None"] = relationship(back_populates="refill_plans")


class ConsultationDraft(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    __tablename__ = "consultation_drafts"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    prescription_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    material_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text)
    doctor_confirmation_required: Mapped[bool] = mapped_column(default=True, nullable=False)

    member: Mapped["FamilyMember"] = relationship(back_populates="consultation_drafts")
    prescription: Mapped["Prescription | None"] = relationship(back_populates="consultation_drafts")


class PurchasePlan(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    __tablename__ = "purchase_plans"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pharmacy_id: Mapped[str | None] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    plan_detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    delivery_option: Mapped[str | None] = mapped_column(String(80))
    safety_note: Mapped[str | None] = mapped_column(Text)
    doctor_confirmation_required: Mapped[bool] = mapped_column(default=True, nullable=False)

    member: Mapped["FamilyMember"] = relationship(back_populates="purchase_plans")
    pharmacy: Mapped["Pharmacy | None"] = relationship(back_populates="purchase_plans")


class MedicationReminder(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    __tablename__ = "medication_reminders"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    medicine_box_item_id: Mapped[str | None] = mapped_column(ForeignKey("medicine_box_items.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(40), default="medication", nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text)

    member: Mapped["FamilyMember"] = relationship(back_populates="medication_reminders")
    medicine_box_item: Mapped["MedicineBoxItem | None"] = relationship(back_populates="medication_reminders")


class FollowUpTask(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    __tablename__ = "follow_up_tasks"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    task_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text)

    member: Mapped["FamilyMember"] = relationship(back_populates="follow_up_tasks")


from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.pharmacy import Pharmacy
    from app.models.plans import ConsultationDraft, MedicationReminder, RefillPlan
    from app.models.user import FamilyMember


class MedicineBoxItem(IDMixin, TimestampMixin, Base):
    __tablename__ = "medicine_box_items"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    specification: Mapped[str | None] = mapped_column(String(120))
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dosage: Mapped[str] = mapped_column(String(120), nullable=False)
    frequency: Mapped[str] = mapped_column(String(120), nullable=False)
    purchased_at: Mapped[date | None] = mapped_column(Date)
    estimated_remaining_days: Mapped[int | None] = mapped_column(Integer)
    safety_note: Mapped[str | None] = mapped_column(Text)

    member: Mapped["FamilyMember"] = relationship(back_populates="medicine_box_items")
    medication_reminders: Mapped[list["MedicationReminder"]] = relationship(back_populates="medicine_box_item")


class Prescription(IDMixin, TimestampMixin, Base):
    __tablename__ = "prescriptions"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    prescription_no: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    doctor_name: Mapped[str | None] = mapped_column(String(80))
    hospital_name: Mapped[str | None] = mapped_column(String(120))
    doctor_diagnosis_summary: Mapped[str | None] = mapped_column(Text)
    medicine_items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="valid", nullable=False)
    doctor_confirmation_required: Mapped[bool] = mapped_column(default=True, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text)

    member: Mapped["FamilyMember"] = relationship(back_populates="prescriptions")
    purchase_records: Mapped[list["PurchaseRecord"]] = relationship(back_populates="prescription")
    refill_plans: Mapped[list["RefillPlan"]] = relationship(back_populates="prescription")
    consultation_drafts: Mapped[list["ConsultationDraft"]] = relationship(back_populates="prescription")


class PurchaseRecord(IDMixin, TimestampMixin, Base):
    __tablename__ = "purchase_records"

    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    prescription_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    pharmacy_id: Mapped[str | None] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(120))
    frequency: Mapped[str | None] = mapped_column(String(120))
    pharmacy_name: Mapped[str | None] = mapped_column(String(120))
    purchased_at: Mapped[date | None] = mapped_column(Date)
    purchase_channel: Mapped[str | None] = mapped_column(String(80))

    member: Mapped["FamilyMember"] = relationship(back_populates="purchase_records")
    prescription: Mapped["Prescription | None"] = relationship(back_populates="purchase_records")
    pharmacy: Mapped["Pharmacy | None"] = relationship(back_populates="purchase_records")


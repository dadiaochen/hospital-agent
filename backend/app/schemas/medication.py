from datetime import date
from typing import Any

from app.schemas.common import ApiSchema


class MedicineBoxItemResponse(ApiSchema):
    id: str
    member_id: str
    medicine_name: str
    specification: str | None
    total_quantity: int
    remaining_quantity: int
    dosage: str
    frequency: str
    purchased_at: date | None
    estimated_remaining_days: int | None
    safety_note: str | None


class MedicineBoxListResponse(ApiSchema):
    items: list[MedicineBoxItemResponse]


class PrescriptionResponse(ApiSchema):
    id: str
    member_id: str
    prescription_no: str | None
    doctor_name: str | None
    hospital_name: str | None
    doctor_diagnosis_summary: str | None
    medicine_items: list[dict[str, Any]]
    issued_at: date | None
    expires_at: date | None
    status: str
    doctor_confirmation_required: bool
    safety_note: str | None


class PrescriptionListResponse(ApiSchema):
    items: list[PrescriptionResponse]


class PurchaseRecordResponse(ApiSchema):
    id: str
    member_id: str
    prescription_id: str | None
    pharmacy_id: str | None
    medicine_name: str
    quantity: int
    dosage: str | None
    frequency: str | None
    pharmacy_name: str | None
    purchased_at: date | None
    purchase_channel: str | None


class PurchaseRecordListResponse(ApiSchema):
    items: list[PurchaseRecordResponse]

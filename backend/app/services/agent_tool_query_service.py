from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FamilyMember,
    HealthProfile,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    PurchaseRecord,
)
from app.rag import RetrievalRequest, create_knowledge_retriever


def get_health_profile_context(
    db: Session,
    user_id: str,
    member_id: str,
) -> dict[str, Any] | None:
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.user_id == user_id,
        )
    )
    if member is None:
        return None

    profile = db.scalar(select(HealthProfile).where(HealthProfile.member_id == member_id))
    if profile is None:
        return None

    return {
        "source_id": f"health_profile:{profile.id}",
        "source_name": "health_profiles",
        "evidence_present": True,
        "member_id": member.id,
        "profile": {
            "member_id": member.id,
            "user_id": member.user_id,
            "name": member.name,
            "relationship": member.relationship,
            "gender": member.gender,
            "birthday": _date_to_str(member.birthday),
            "default_address": member.default_address,
            "chronic_disease_tags": list(profile.chronic_disease_tags or []),
            "allergies": list(profile.allergies or []),
            "current_medications": list(profile.current_medications or []),
            "health_notes": profile.health_notes,
            "safety_notes": list(profile.safety_notes or []),
        },
    }


def get_prescription_context(db: Session, member_id: str) -> dict[str, Any] | None:
    prescriptions = list(
        db.scalars(
            select(Prescription)
            .where(Prescription.member_id == member_id)
            .order_by(Prescription.issued_at.desc())
        )
    )
    purchase_records = list(
        db.scalars(
            select(PurchaseRecord)
            .where(PurchaseRecord.member_id == member_id)
            .order_by(PurchaseRecord.purchased_at.desc())
        )
    )
    if not prescriptions and not purchase_records:
        return None

    return {
        "source_id": f"prescriptions:{member_id}",
        "source_name": "prescriptions",
        "evidence_present": True,
        "member_id": member_id,
        "prescriptions": [
            {
                "prescription_id": item.id,
                "prescription_no": item.prescription_no,
                "doctor_name": item.doctor_name,
                "hospital_name": item.hospital_name,
                "doctor_diagnosis_summary": item.doctor_diagnosis_summary,
                "medicine_items": list(item.medicine_items or []),
                "issued_at": _date_to_str(item.issued_at),
                "expires_at": _date_to_str(item.expires_at),
                "status": item.status,
                "doctor_confirmation_required": item.doctor_confirmation_required,
                "safety_note": item.safety_note,
            }
            for item in prescriptions
        ],
        "purchase_records": [
            {
                "purchase_record_id": item.id,
                "prescription_id": item.prescription_id,
                "pharmacy_id": item.pharmacy_id,
                "medicine_name": item.medicine_name,
                "quantity": item.quantity,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "pharmacy_name": item.pharmacy_name,
                "purchased_at": _date_to_str(item.purchased_at),
                "purchase_channel": item.purchase_channel,
            }
            for item in purchase_records
        ],
    }


def get_medicine_box_context(db: Session, member_id: str) -> dict[str, Any] | None:
    items = list(
        db.scalars(
            select(MedicineBoxItem)
            .where(MedicineBoxItem.member_id == member_id)
            .order_by(MedicineBoxItem.medicine_name)
        )
    )
    if not items:
        return None

    return {
        "source_id": f"medicine_box:{member_id}",
        "source_name": "medicine_box_items",
        "evidence_present": True,
        "member_id": member_id,
        "items": [
            {
                "medicine_box_item_id": item.id,
                "medicine_name": item.medicine_name,
                "specification": item.specification,
                "total_quantity": item.total_quantity,
                "remaining_quantity": item.remaining_quantity,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "purchased_at": _date_to_str(item.purchased_at),
                "estimated_remaining_days": item.estimated_remaining_days,
                "safety_note": item.safety_note,
            }
            for item in items
        ],
    }


def get_pharmacy_inventory_context(
    db: Session,
    medicine_name: str | None = None,
    city: str | None = None,
) -> dict[str, Any] | None:
    statement = (
        select(PharmacyInventory, Pharmacy)
        .join(Pharmacy, PharmacyInventory.pharmacy_id == Pharmacy.id)
        .order_by(Pharmacy.city, Pharmacy.name, PharmacyInventory.medicine_name)
    )
    if medicine_name:
        statement = statement.where(PharmacyInventory.medicine_name.ilike(f"%{medicine_name}%"))
    if city:
        statement = statement.where(Pharmacy.city == city)

    rows = list(db.execute(statement))
    if not rows:
        return None

    return {
        "source_id": f"pharmacy_inventory:{medicine_name or 'all'}:{city or 'all'}",
        "source_name": "pharmacy_inventory",
        "evidence_present": True,
        "medicine_name": medicine_name,
        "city": city,
        "inventory_items": [
            {
                "inventory_id": inventory.id,
                "pharmacy_id": pharmacy.id,
                "pharmacy_name": pharmacy.name,
                "city": pharmacy.city,
                "address": pharmacy.address,
                "supports_delivery": pharmacy.supports_delivery,
                "supports_pickup": pharmacy.supports_pickup,
                "contact_phone": pharmacy.contact_phone,
                "medicine_name": inventory.medicine_name,
                "stock_quantity": inventory.stock_quantity,
                "delivery_options": list(inventory.delivery_options or []),
                "safety_note": inventory.safety_note,
            }
            for inventory, pharmacy in rows
        ],
    }


def search_safety_knowledge_context(db: Session, query: str) -> dict[str, Any] | None:
    result = create_knowledge_retriever(db).retrieve(
        RetrievalRequest(
            query=query,
            purpose="safety_and_workflow_grounding",
        )
    )
    if not result.evidence_present:
        return None

    matches = [source.model_dump() for source in result.sources]

    return {
        "source_id": "knowledge_search:" + ",".join(item["source_id"] for item in matches),
        "source_name": "knowledge_chunks",
        "evidence_present": True,
        "query": result.query,
        "requested_mode": result.requested_mode,
        "effective_mode": result.effective_mode,
        "fallback_used": result.fallback_used,
        "fallback_reason": result.fallback_reason,
        "sources": matches,
    }


def _date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None

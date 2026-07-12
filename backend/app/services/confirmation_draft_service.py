from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    ConsultationDraft,
    FamilyMember,
    MedicationReminder,
    MedicineBoxItem,
    Pharmacy,
    Prescription,
    PurchasePlan,
    RefillPlan,
)
from app.models.base import utc_now


ConfirmationDraftAction = Literal[
    "refill_request",
    "consultation_request",
    "pharmacy_option",
    "reminder_create",
]

_AUDIT_KEY = "_agent_audit"
_NO_EXTERNAL_ACTION_NOTE = (
    "User confirmed local draft creation only; no external action was submitted."
)
_FORBIDDEN_MEDICAL_ACTIONS = (
    "auto_prescribe",
    "diagnosis_by_ai",
    "ai_dosage_change",
    "automatic prescription",
    "increase dose",
    "decrease dose",
    "stop medication",
    "switch medication",
    "自动开方",
    "ai诊断",
    "加量",
    "减量",
    "停药",
    "换药",
)


class ConfirmationDraftServiceError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        fallback_action: str,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.fallback_action = fallback_action


def create_confirmation_draft(
    db: Session,
    *,
    user_id: str,
    member_id: str,
    action_type: ConfirmationDraftAction,
    idempotency_key: str,
    run_id: str,
    summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Flush one local draft; the calling tool owns output validation and commit."""
    _require_member_scope(db, user_id=user_id, member_id=member_id)
    _reject_unsafe_medical_actions(summary, payload)

    existing = _find_existing_draft(
        db,
        action_type=action_type,
        member_id=member_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _serialize_draft(existing, action_type, idempotent_replay=True)

    audit = {
        "action_type": action_type,
        "created_by_run_id": run_id,
        "idempotency_key": idempotency_key,
        "user_id": user_id,
        "member_id": member_id,
        "summary": summary,
        "local_confirmation_recorded": True,
        "external_action_status": "not_submitted",
    }

    try:
        draft = _build_draft(
            db,
            action_type=action_type,
            member_id=member_id,
            summary=summary,
            payload=payload,
            audit=audit,
        )
        db.add(draft)
        db.flush()
        db.refresh(draft)
    except ConfirmationDraftServiceError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise ConfirmationDraftServiceError(
            "failed to persist confirmation draft",
            error_type="database_write_error",
            fallback_action="manual_review",
        ) from exc

    return _serialize_draft(draft, action_type, idempotent_replay=False)


def _build_draft(
    db: Session,
    *,
    action_type: ConfirmationDraftAction,
    member_id: str,
    summary: str,
    payload: dict[str, Any],
    audit: dict[str, Any],
):
    confirmed_at = utc_now()
    common = {
        "status": "draft",
        "need_human_confirmation": True,
        "confirmed_at": confirmed_at,
        "confirmation_note": _NO_EXTERNAL_ACTION_NOTE,
    }

    if action_type == "refill_request":
        medicine_name = _required_text(payload, "medicine_name", action_type)
        prescription_id = _optional_text(payload, "prescription_id")
        _require_prescription(db, prescription_id, member_id)
        return RefillPlan(
            member_id=member_id,
            prescription_id=prescription_id,
            medicine_name=medicine_name,
            remaining_days=_optional_int(payload, "remaining_days"),
            plan_detail=_with_audit(payload.get("plan_detail"), audit),
            suggestion=summary,
            safety_note=_NO_EXTERNAL_ACTION_NOTE,
            doctor_confirmation_required=True,
            **common,
        )

    if action_type == "consultation_request":
        prescription_id = _optional_text(payload, "prescription_id")
        _require_prescription(db, prescription_id, member_id)
        return ConsultationDraft(
            member_id=member_id,
            prescription_id=prescription_id,
            draft_content=_optional_text(payload, "draft_content") or summary,
            material_summary=_with_audit(payload.get("material_summary"), audit),
            safety_note=_NO_EXTERNAL_ACTION_NOTE,
            doctor_confirmation_required=True,
            **common,
        )

    if action_type == "pharmacy_option":
        medicine_name = _required_text(payload, "medicine_name", action_type)
        pharmacy_id = _optional_text(payload, "pharmacy_id")
        _require_pharmacy(db, pharmacy_id)
        return PurchasePlan(
            member_id=member_id,
            medicine_name=medicine_name,
            pharmacy_id=pharmacy_id,
            plan_detail=_with_audit(payload.get("plan_detail"), audit),
            delivery_option=_optional_text(payload, "delivery_option"),
            safety_note=_NO_EXTERNAL_ACTION_NOTE,
            doctor_confirmation_required=True,
            **common,
        )

    medicine_name = _required_text(payload, "medicine_name", action_type)
    medicine_box_item_id = _optional_text(payload, "medicine_box_item_id")
    _require_medicine_box_item(db, medicine_box_item_id, member_id)
    schedule = _required_mapping(payload, "schedule", action_type)
    return MedicationReminder(
        member_id=member_id,
        medicine_box_item_id=medicine_box_item_id,
        medicine_name=medicine_name,
        schedule=_with_audit(schedule, audit),
        reminder_type=_optional_text(payload, "reminder_type") or "medication",
        safety_note=_NO_EXTERNAL_ACTION_NOTE,
        **common,
    )


def _find_existing_draft(
    db: Session,
    *,
    action_type: ConfirmationDraftAction,
    member_id: str,
    idempotency_key: str,
):
    model, metadata_field = _draft_model_and_metadata_field(action_type)
    rows = db.scalars(select(model).where(model.member_id == member_id))
    for row in rows:
        metadata = getattr(row, metadata_field) or {}
        audit = metadata.get(_AUDIT_KEY, {}) if isinstance(metadata, dict) else {}
        if audit.get("idempotency_key") == idempotency_key:
            return row
    return None


def _serialize_draft(
    draft,
    action_type: ConfirmationDraftAction,
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    _, metadata_field = _draft_model_and_metadata_field(action_type)
    metadata = getattr(draft, metadata_field) or {}
    audit = metadata.get(_AUDIT_KEY, {}) if isinstance(metadata, dict) else {}
    return {
        "source_id": f"draft:{action_type}:{draft.id}",
        "source_name": draft.__tablename__,
        "evidence_present": True,
        "draft_id": draft.id,
        "draft_type": action_type,
        "member_id": draft.member_id,
        "status": draft.status,
        "need_human_confirmation": draft.need_human_confirmation,
        "confirmed_at": _datetime_to_str(draft.confirmed_at),
        "created_by_run_id": audit.get("created_by_run_id"),
        "local_confirmation_recorded": True,
        "external_action_status": "not_submitted",
        "idempotent_replay": idempotent_replay,
    }


def _draft_model_and_metadata_field(action_type: ConfirmationDraftAction):
    if action_type == "refill_request":
        return RefillPlan, "plan_detail"
    if action_type == "consultation_request":
        return ConsultationDraft, "material_summary"
    if action_type == "pharmacy_option":
        return PurchasePlan, "plan_detail"
    return MedicationReminder, "schedule"


def _require_member_scope(db: Session, *, user_id: str, member_id: str) -> None:
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.user_id == user_id,
        )
    )
    if member is None:
        raise ConfirmationDraftServiceError(
            "member does not belong to the execution user",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )


def _require_prescription(
    db: Session,
    prescription_id: str | None,
    member_id: str,
) -> None:
    if prescription_id is None:
        return
    prescription = db.scalar(
        select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.member_id == member_id,
        )
    )
    if prescription is None:
        raise ConfirmationDraftServiceError(
            "prescription does not belong to the selected member",
            error_type="related_record_not_found",
            fallback_action="ask_user_clarification",
        )


def _require_medicine_box_item(
    db: Session,
    item_id: str | None,
    member_id: str,
) -> None:
    if item_id is None:
        return
    item = db.scalar(
        select(MedicineBoxItem).where(
            MedicineBoxItem.id == item_id,
            MedicineBoxItem.member_id == member_id,
        )
    )
    if item is None:
        raise ConfirmationDraftServiceError(
            "medicine box item does not belong to the selected member",
            error_type="related_record_not_found",
            fallback_action="ask_user_clarification",
        )


def _require_pharmacy(db: Session, pharmacy_id: str | None) -> None:
    if pharmacy_id is None:
        return
    if db.get(Pharmacy, pharmacy_id) is None:
        raise ConfirmationDraftServiceError(
            "pharmacy does not exist",
            error_type="related_record_not_found",
            fallback_action="ask_user_clarification",
        )


def _with_audit(value: Any, audit: dict[str, Any]) -> dict[str, Any]:
    result = dict(value) if isinstance(value, dict) else {}
    result[_AUDIT_KEY] = dict(audit)
    return result


def _required_text(
    payload: dict[str, Any],
    field: str,
    action_type: str,
) -> str:
    value = _optional_text(payload, field)
    if value is None:
        raise ConfirmationDraftServiceError(
            f"{field} is required for {action_type}",
            error_type="draft_payload_invalid",
            fallback_action="ask_user_clarification",
        )
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfirmationDraftServiceError(
            f"{field} must be a non-empty string",
            error_type="draft_payload_invalid",
            fallback_action="ask_user_clarification",
        )
    return value.strip()


def _optional_int(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfirmationDraftServiceError(
            f"{field} must be a non-negative integer",
            error_type="draft_payload_invalid",
            fallback_action="ask_user_clarification",
        )
    return value


def _required_mapping(
    payload: dict[str, Any],
    field: str,
    action_type: str,
) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict) or not value:
        raise ConfirmationDraftServiceError(
            f"{field} is required for {action_type}",
            error_type="draft_payload_invalid",
            fallback_action="ask_user_clarification",
        )
    return value


def _reject_unsafe_medical_actions(summary: str, payload: dict[str, Any]) -> None:
    rendered = f"{summary} {payload}".lower()
    matched = next(
        (phrase for phrase in _FORBIDDEN_MEDICAL_ACTIONS if phrase in rendered),
        None,
    )
    if matched is not None:
        raise ConfirmationDraftServiceError(
            f"draft contains forbidden medical action language: {matched}",
            error_type="medical_safety_violation",
            fallback_action="route_to_safety_agent",
        )


def _datetime_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = [
    "ConfirmationDraftAction",
    "ConfirmationDraftServiceError",
    "create_confirmation_draft",
]

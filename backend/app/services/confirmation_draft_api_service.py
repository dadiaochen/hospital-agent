from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NoReturn

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError, ResourceNotFoundError
from app.models import (
    AgentRun,
    ConsultationDraft,
    FamilyMember,
    MedicationReminder,
    PurchasePlan,
    RefillPlan,
)
from app.models.base import utc_now
from app.services.confirmation_draft_service import (
    ConfirmationDraftAction,
    ConfirmationDraftServiceError,
    create_confirmation_draft,
)


DraftStatus = Literal["draft", "confirmed", "rejected"]
DecisionStatus = Literal["confirmed", "rejected"]

_AUDIT_KEY = "_agent_audit"
_DRAFT_CONFIG: dict[str, tuple[type[Any], str]] = {
    "refill_request": (RefillPlan, "plan_detail"),
    "consultation_request": (ConsultationDraft, "material_summary"),
    "pharmacy_option": (PurchasePlan, "plan_detail"),
    "reminder_create": (MedicationReminder, "schedule"),
}


class ConfirmationDraftApiService:
    """HTTP use cases for local draft state, scoped to one demo user."""

    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def create_draft(
        self,
        *,
        member_id: str,
        draft_type: ConfirmationDraftAction,
        idempotency_key: str,
        run_id: str | None,
        summary: str,
        payload: dict[str, Any],
        human_confirmation_granted: bool,
    ) -> dict[str, Any]:
        if not human_confirmation_granted:
            raise ApiError(
                status_code=409,
                code="human_confirmation_required",
                message="human confirmation is required before creating a local draft",
            )
        if run_id is not None:
            self._require_scoped_run(run_id, member_id)

        try:
            result = create_confirmation_draft(
                self.db,
                user_id=self.user_id,
                member_id=member_id,
                action_type=draft_type,
                idempotency_key=idempotency_key,
                run_id=run_id,
                summary=summary,
                payload=payload,
            )
            self.db.commit()
        except ConfirmationDraftServiceError as exc:
            self.db.rollback()
            self._raise_service_error(exc)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiError(
                status_code=500,
                code="database_write_error",
                message="failed to persist confirmation draft",
            ) from exc

        draft = self._get_scoped_draft(draft_type, result["draft_id"])
        return self._serialize_draft(
            draft,
            draft_type,
            idempotent_replay=bool(result["idempotent_replay"]),
        )

    def list_drafts(
        self,
        *,
        member_id: str | None,
        draft_type: ConfirmationDraftAction | None,
        status: DraftStatus | None,
    ) -> list[dict[str, Any]]:
        if member_id is not None:
            self._get_scoped_member(member_id)

        draft_types = [draft_type] if draft_type is not None else list(_DRAFT_CONFIG)
        rows: list[tuple[Any, ConfirmationDraftAction]] = []
        for current_type in draft_types:
            model, _ = _DRAFT_CONFIG[current_type]
            statement = (
                select(model)
                .join(FamilyMember, model.member_id == FamilyMember.id)
                .where(FamilyMember.user_id == self.user_id)
            )
            if member_id is not None:
                statement = statement.where(model.member_id == member_id)
            if status is not None:
                statement = statement.where(model.status == status)
            rows.extend((row, current_type) for row in self.db.scalars(statement))

        rows.sort(key=lambda item: item[0].created_at, reverse=True)
        return [
            self._serialize_draft(row, current_type, idempotent_replay=False)
            for row, current_type in rows
        ]

    def get_draft(
        self,
        draft_type: ConfirmationDraftAction,
        draft_id: str,
    ) -> dict[str, Any]:
        draft = self._get_scoped_draft(draft_type, draft_id, for_update=True)
        return self._serialize_draft(draft, draft_type, idempotent_replay=False)

    def decide_draft(
        self,
        *,
        draft_type: ConfirmationDraftAction,
        draft_id: str,
        target_status: DecisionStatus,
        idempotency_key: str,
        human_confirmation_present: bool,
        note: str | None,
    ) -> dict[str, Any]:
        draft = self._get_scoped_draft(draft_type, draft_id)
        if not human_confirmation_present:
            raise ApiError(
                status_code=409,
                code="human_confirmation_required",
                message="an explicit human decision is required",
            )

        if draft.status == target_status:
            return self._serialize_draft(
                draft,
                draft_type,
                idempotent_replay=True,
            )
        if draft.status != "draft":
            raise ApiError(
                status_code=409,
                code="invalid_state_transition",
                message=f"cannot change a {draft.status} draft to {target_status}",
            )

        _, metadata_field = _DRAFT_CONFIG[draft_type]
        metadata = dict(getattr(draft, metadata_field) or {})
        audit = dict(metadata.get(_AUDIT_KEY) or {})
        transitions = list(audit.get("status_transitions") or [])
        resolved_at = utc_now()
        transitions.append(
            {
                "from_status": "draft",
                "to_status": target_status,
                "resolved_at": resolved_at.isoformat(),
                "idempotency_key": idempotency_key,
                "user_id": self.user_id,
                "note": note,
                "external_action_status": "not_submitted",
            }
        )
        audit.update(
            {
                "status_transitions": transitions,
                "final_decision": target_status,
                "final_decision_at": resolved_at.isoformat(),
                "final_decision_by_user_id": self.user_id,
                "final_decision_idempotency_key": idempotency_key,
                "final_decision_note": note,
                "external_action_status": "not_submitted",
            }
        )
        metadata[_AUDIT_KEY] = audit
        setattr(draft, metadata_field, metadata)
        draft.status = target_status

        try:
            self.db.commit()
            self.db.refresh(draft)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiError(
                status_code=500,
                code="database_write_error",
                message="failed to update confirmation draft",
            ) from exc

        return self._serialize_draft(draft, draft_type, idempotent_replay=False)

    def _get_scoped_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member was not found")
        return member

    def _get_scoped_draft(
        self,
        draft_type: ConfirmationDraftAction,
        draft_id: str,
        *,
        for_update: bool = False,
    ):
        model, _ = _DRAFT_CONFIG[draft_type]
        statement = (
            select(model)
            .join(FamilyMember, model.member_id == FamilyMember.id)
            .where(
                model.id == draft_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        draft = self.db.scalar(statement)
        if draft is None:
            raise ResourceNotFoundError("confirmation draft was not found")
        return draft

    def _require_scoped_run(self, run_id: str, member_id: str) -> None:
        run = self.db.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.user_id == self.user_id,
                AgentRun.member_id == member_id,
            )
        )
        if run is None:
            raise ResourceNotFoundError("agent run was not found")

    @staticmethod
    def _raise_service_error(exc: ConfirmationDraftServiceError) -> NoReturn:
        if exc.error_type in {
            "context_isolation_violation",
            "related_record_not_found",
        }:
            raise ResourceNotFoundError("confirmation draft dependency was not found") from exc
        if exc.error_type == "database_write_error":
            raise ApiError(
                status_code=500,
                code=exc.error_type,
                message="failed to persist confirmation draft",
            ) from exc
        raise ApiError(
            status_code=422,
            code=exc.error_type,
            message=str(exc),
        ) from exc

    @staticmethod
    def _serialize_draft(
        draft,
        draft_type: ConfirmationDraftAction,
        *,
        idempotent_replay: bool,
    ) -> dict[str, Any]:
        _, metadata_field = _DRAFT_CONFIG[draft_type]
        metadata = dict(getattr(draft, metadata_field) or {})
        audit = dict(metadata.pop(_AUDIT_KEY, {}) or {})
        return {
            "source_id": f"draft:{draft_type}:{draft.id}",
            "draft_id": draft.id,
            "draft_type": draft_type,
            "member_id": draft.member_id,
            "status": draft.status,
            "need_human_confirmation": draft.need_human_confirmation,
            "local_confirmation_recorded": draft.confirmed_at is not None,
            "confirmed_at": draft.confirmed_at,
            "resolved_at": _parse_datetime(audit.get("final_decision_at")),
            "decision_note": audit.get("final_decision_note"),
            "summary": audit.get("summary"),
            "created_by_run_id": audit.get("created_by_run_id"),
            "idempotency_key": audit.get("idempotency_key"),
            "external_action_status": "not_submitted",
            "content": _public_content(draft, draft_type, metadata),
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
            "idempotent_replay": idempotent_replay,
        }


def _public_content(
    draft,
    draft_type: ConfirmationDraftAction,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if draft_type == "refill_request":
        return {
            "prescription_id": draft.prescription_id,
            "medicine_name": draft.medicine_name,
            "remaining_days": draft.remaining_days,
            "plan_detail": metadata,
            "suggestion": draft.suggestion,
            "safety_note": draft.safety_note,
            "doctor_confirmation_required": draft.doctor_confirmation_required,
        }
    if draft_type == "consultation_request":
        return {
            "prescription_id": draft.prescription_id,
            "draft_content": draft.draft_content,
            "material_summary": metadata,
            "safety_note": draft.safety_note,
            "doctor_confirmation_required": draft.doctor_confirmation_required,
        }
    if draft_type == "pharmacy_option":
        return {
            "medicine_name": draft.medicine_name,
            "pharmacy_id": draft.pharmacy_id,
            "plan_detail": metadata,
            "delivery_option": draft.delivery_option,
            "safety_note": draft.safety_note,
            "doctor_confirmation_required": draft.doctor_confirmation_required,
        }
    return {
        "medicine_box_item_id": draft.medicine_box_item_id,
        "medicine_name": draft.medicine_name,
        "schedule": metadata,
        "reminder_type": draft.reminder_type,
        "safety_note": draft.safety_note,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


__all__ = ["ConfirmationDraftApiService"]

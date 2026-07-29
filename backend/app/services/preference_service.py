"""Explicitly confirmed, versioned preference persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError, InvalidRequestError, ResourceNotFoundError
from app.models import (
    AgentRun,
    BusinessTask,
    ConfirmedPreference,
    FamilyMember,
    SourceReference,
    TaskConfirmationRecord,
)
from app.models.base import utc_now


@dataclass(frozen=True)
class PreferenceWriteExecution:
    preference: ConfirmedPreference
    idempotent_replay: bool = False


class ConfirmedPreferenceService:
    """Persist only non-medical preferences backed by an explicit confirmation."""

    _FORBIDDEN_TERMS = {
        "diagnosis",
        "prescription",
        "dosage",
        "dose",
        "medication",
        "medicine",
        "allergy",
        "report",
        "inventory",
        "symptom",
    }

    def __init__(self, db: Session, *, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def write(
        self,
        *,
        task_id: str,
        member_id: str,
        preference_type: str,
        preference_value: dict[str, Any],
        source_id: str,
        source_version: str,
        confirmation_version: int,
        preference_version: int | None,
        idempotency_key: str,
        human_confirmation_granted: bool,
    ) -> PreferenceWriteExecution:
        if not human_confirmation_granted:
            raise InvalidRequestError("explicit human confirmation is required for preference writes")
        if not self._safe_preference_type(preference_type):
            raise InvalidRequestError("medical facts cannot be stored as preferences")
        if not self._safe_value(preference_value):
            raise InvalidRequestError("preference value contains a medical fact or working inference")
        if not source_version.strip():
            raise InvalidRequestError("preference source version is required")

        task = self.db.scalar(
            select(BusinessTask)
            .where(BusinessTask.id == task_id, BusinessTask.user_id == self.user_id)
            .with_for_update()
        )
        if task is None:
            raise ResourceNotFoundError("business task not found")
        if task.member_id != member_id:
            raise ApiError(
                status_code=409,
                code="context_isolation_violation",
                message="preference member does not match the task member",
            )
        self._require_member(member_id)

        request_fingerprint = self._fingerprint(
            task_id=task_id,
            member_id=member_id,
            preference_type=preference_type,
            preference_value=preference_value,
            source_id=source_id,
            source_version=source_version,
            confirmation_version=confirmation_version,
            preference_version=preference_version,
        )
        existing = self.db.scalar(
            select(ConfirmedPreference).where(
                ConfirmedPreference.user_id == self.user_id,
                ConfirmedPreference.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise ApiError(
                    status_code=409,
                    code="idempotency_conflict",
                    message="preference idempotency key was used for a different request",
                )
            return PreferenceWriteExecution(preference=existing, idempotent_replay=True)

        if task.status != "completed" or task.confirmation_version < 1:
            raise ApiError(
                status_code=409,
                code="confirmation_required",
                message="a completed, confirmed task is required before preference write",
            )
        if task.confirmation_version != confirmation_version:
            raise ApiError(
                status_code=409,
                code="confirmation_version_conflict",
                message="preference confirmation version is stale",
            )

        confirmation = self.db.scalar(
            select(TaskConfirmationRecord)
            .where(
                TaskConfirmationRecord.task_id == task.id,
                TaskConfirmationRecord.user_id == self.user_id,
                TaskConfirmationRecord.member_id == member_id,
                TaskConfirmationRecord.next_state == "EXECUTED",
                TaskConfirmationRecord.confirmation_version == confirmation_version,
            )
            .order_by(TaskConfirmationRecord.created_at.desc())
        )
        if confirmation is None or not confirmation.human_confirmation_present:
            raise ApiError(
                status_code=409,
                code="confirmation_record_missing",
                message="explicit confirmation record is required before preference write",
            )

        source = self.db.scalar(
            select(SourceReference).where(
                SourceReference.source_id == source_id,
                SourceReference.user_id == self.user_id,
                SourceReference.task_id == task.id,
                SourceReference.member_id == member_id,
            )
        )
        if source is None:
            raise ApiError(
                status_code=409,
                code="preference_source_conflict",
                message="preference source is not present in the confirmed task scope",
            )
        if source_version not in self._source_versions(source):
            raise ApiError(
                status_code=409,
                code="preference_source_version_conflict",
                message="preference source version does not match the recorded source",
            )

        current = self.db.scalar(
            select(ConfirmedPreference)
            .where(
                ConfirmedPreference.user_id == self.user_id,
                ConfirmedPreference.member_id == member_id,
                ConfirmedPreference.preference_type == preference_type,
                ConfirmedPreference.status == "active",
            )
            .order_by(ConfirmedPreference.preference_version.desc())
            .with_for_update()
        )
        current_version = current.preference_version if current is not None else 0
        if preference_version is not None:
            expected_current = 0 if current is None else current_version
            if preference_version != expected_current:
                raise ApiError(
                    status_code=409,
                    code="preference_version_conflict",
                    message="preference version is stale",
                )

        if current is not None:
            current.status = "superseded"
            current.revoked_at = utc_now()
        row = ConfirmedPreference(
            user_id=self.user_id,
            member_id=member_id,
            task_id=task.id,
            created_by_run_id=task.current_run_id or confirmation.run_id,
            confirmation_record_id=confirmation.id,
            preference_type=preference_type,
            preference_value=self._json_safe(preference_value),
            preference_version=current_version + 1,
            consent_version=confirmation_version,
            source_id=source.source_id,
            source_version=source_version,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="active",
            revocable=True,
            metadata_payload={"confirmation_record_id": confirmation.id},
        )
        self.db.add(row)
        try:
            self.db.commit()
            self.db.refresh(row)
        except IntegrityError as exc:
            self.db.rollback()
            raise ApiError(
                status_code=409,
                code="preference_write_conflict",
                message="preference write conflicted with another version",
            ) from exc
        return PreferenceWriteExecution(preference=row)

    def _require_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member not found")
        return member

    @classmethod
    def _safe_preference_type(cls, value: str) -> bool:
        normalized = value.casefold().replace("-", "_")
        return bool(normalized) and not any(term in normalized for term in cls._FORBIDDEN_TERMS)

    @classmethod
    def _safe_value(cls, value: Any) -> bool:
        if isinstance(value, Mapping):
            return all(
                not any(term in str(key).casefold() for term in cls._FORBIDDEN_TERMS)
                and cls._safe_value(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return all(cls._safe_value(item) for item in value)
        if isinstance(value, str):
            return not any(term in value.casefold() for term in cls._FORBIDDEN_TERMS)
        return True

    @staticmethod
    def _source_versions(source: SourceReference) -> set[str]:
        versions = {str(source.document_version)} if source.document_version else set()
        for key in ("version", "source_version", "document_version"):
            value = source.source_metadata.get(key) if isinstance(source.source_metadata, dict) else None
            if value:
                versions.add(str(value))
        return versions

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @staticmethod
    def _fingerprint(**values: Any) -> str:
        rendered = json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(rendered.encode("utf-8")).hexdigest()


__all__ = ["ConfirmedPreferenceService", "PreferenceWriteExecution"]

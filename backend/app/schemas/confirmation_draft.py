from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiSchema


ConfirmationDraftType = Literal[
    "refill_request",
    "consultation_request",
    "pharmacy_option",
    "reminder_create",
]
ConfirmationDraftStatus = Literal["draft", "confirmed", "rejected"]


class ConfirmationDraftCreateRequest(ApiSchema):
    member_id: str = Field(min_length=1, max_length=64)
    draft_type: ConfirmationDraftType
    idempotency_key: str = Field(min_length=1, max_length=120)
    run_id: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    human_confirmation_granted: bool = False

    @field_validator("member_id", "idempotency_key", "summary", "run_id")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class ConfirmationDraftDecisionRequest(ApiSchema):
    idempotency_key: str = Field(min_length=1, max_length=120)
    human_confirmation_present: bool = False
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("idempotency_key", "note")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class ConfirmationDraftResponse(ApiSchema):
    source_id: str
    draft_id: str
    draft_type: ConfirmationDraftType
    member_id: str
    status: ConfirmationDraftStatus
    need_human_confirmation: bool
    local_confirmation_recorded: bool
    confirmed_at: datetime | None
    resolved_at: datetime | None
    decision_note: str | None
    summary: str | None
    created_by_run_id: str | None
    idempotency_key: str | None
    external_action_status: Literal["not_submitted"]
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class ConfirmationDraftListResponse(ApiSchema):
    items: list[ConfirmationDraftResponse]


__all__ = [
    "ConfirmationDraftCreateRequest",
    "ConfirmationDraftDecisionRequest",
    "ConfirmationDraftListResponse",
    "ConfirmationDraftResponse",
    "ConfirmationDraftStatus",
    "ConfirmationDraftType",
]

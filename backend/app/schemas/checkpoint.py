"""Pydantic contracts for the durable task-state boundary."""

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiSchema


class CheckpointSourcePointer(ApiSchema):
    """A source pointer retained by a checkpoint, never the source content."""

    source_id: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=40)
    document_id: str | None = Field(default=None, max_length=120)
    document_version: str | None = Field(default=None, max_length=80)
    chunk_id: str | None = Field(default=None, max_length=120)
    retrieval_mode: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=120)
    member_id: str = Field(min_length=1, max_length=64)
    verified: bool = False


class TaskCheckpointPayload(ApiSchema):
    """The allow-listed projection that may cross a run boundary."""

    schema_version: Literal["4b.task8.v1"] = "4b.task8.v1"
    task_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    member_id: str = Field(min_length=1, max_length=64)
    thread_id: str = Field(min_length=1, max_length=120)
    run_id: str = Field(min_length=1, max_length=64)
    parent_run_id: str | None = Field(default=None, max_length=64)
    checkpoint_version: int = Field(ge=1)
    status: str = Field(min_length=1, max_length=40)
    business_domain: str = Field(min_length=1, max_length=40)
    intent: str = Field(min_length=1, max_length=80)
    confirmation_state: str = Field(min_length=1, max_length=40)
    confirmation_version: int = Field(ge=0)
    request_fingerprint: str = Field(min_length=1, max_length=64)
    step_progress: dict[str, Any] = Field(default_factory=dict)
    run_summary: dict[str, Any] = Field(default_factory=dict)
    frozen_artifacts: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[CheckpointSourcePointer] = Field(default_factory=list)


CheckpointRestoreSource = Literal["redis", "postgresql", "legacy"]


class ConfirmedPreferenceWriteRequest(ApiSchema):
    """Explicit user action required before a preference is persisted."""

    task_id: str = Field(min_length=1, max_length=64)
    member_id: str = Field(min_length=1, max_length=64)
    preference_type: str = Field(min_length=1, max_length=80)
    preference_value: dict[str, Any] = Field(default_factory=dict)
    source_id: str = Field(min_length=1, max_length=255)
    source_version: str = Field(min_length=1, max_length=80)
    confirmation_version: int = Field(ge=1)
    preference_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=120)
    human_confirmation_granted: Literal[True] = True


class ConfirmedPreferenceResponse(ApiSchema):
    id: str
    user_id: str
    member_id: str
    task_id: str
    preference_type: str
    preference_value: dict[str, Any]
    preference_version: int
    consent_version: int
    source_id: str
    source_version: str
    status: str
    revocable: bool
    revoked_at: Any = None
    created_at: Any
    updated_at: Any
    idempotent_replay: bool = False

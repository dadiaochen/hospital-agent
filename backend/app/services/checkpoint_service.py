"""PostgreSQL-backed task checkpoints and their Redis read-through cache."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import AgentRun, BusinessTask, TaskCheckpoint, TaskConfirmationRecord
from app.schemas.checkpoint import (
    CheckpointRestoreSource,
    CheckpointSourcePointer,
    TaskCheckpointPayload,
)
from app.services.task_checkpoint_cache import TaskCheckpointCache


_FORBIDDEN_WORKING_KEYS = {
    "raw_conversation",
    "conversation_history",
    "scratchpad",
    "candidate_inferences",
    "role_views",
    "working_state",
    "provider_raw_response",
    "api_key",
}


@dataclass(frozen=True)
class CheckpointRestore:
    payload: TaskCheckpointPayload
    source: CheckpointRestoreSource


class TaskCheckpointService:
    """Persist and restore only the allow-listed cross-run state."""

    def __init__(
        self,
        db: Session,
        *,
        cache: TaskCheckpointCache | None = None,
    ) -> None:
        self.db = db
        self.cache = cache or TaskCheckpointCache()

    def persist(
        self,
        *,
        task: BusinessTask,
        run: AgentRun,
        state: Mapping[str, Any],
        parent_run_id: str | None = None,
        previous_confirmation_state: str | None = None,
    ) -> tuple[TaskCheckpoint, TaskCheckpointPayload]:
        """Write one immutable checkpoint and confirmation audit rows.

        The caller commits the surrounding transaction before publishing the
        returned payload to Redis.  This ordering prevents a rolled-back
        checkpoint from becoming visible as a cache hit.
        """

        checkpoint_version = int(task.checkpoint_version or 0) + 1
        confirmation_version = self._next_confirmation_version(task, state, parent_run_id)
        task.checkpoint_version = checkpoint_version
        task.confirmation_version = confirmation_version

        payload = self._project_payload(
            task=task,
            run=run,
            state=state,
            checkpoint_version=checkpoint_version,
            confirmation_version=confirmation_version,
            parent_run_id=parent_run_id,
        )
        row = TaskCheckpoint(
            id=str(uuid4()),
            user_id=payload.user_id,
            member_id=payload.member_id,
            task_id=payload.task_id,
            thread_id=payload.thread_id,
            run_id=payload.run_id,
            parent_run_id=payload.parent_run_id,
            checkpoint_version=payload.checkpoint_version,
            status=payload.status,
            confirmation_state=payload.confirmation_state,
            confirmation_version=payload.confirmation_version,
            request_fingerprint=payload.request_fingerprint,
            step_progress=payload.step_progress,
            run_summary=payload.run_summary,
            frozen_artifacts=payload.frozen_artifacts,
            source_refs=[item.model_dump(mode="json") for item in payload.source_refs],
        )
        self.db.add(row)
        self.db.flush()
        self._persist_confirmation_records(
            task=task,
            run=run,
            state=state,
            confirmation_version=confirmation_version,
            parent_run_id=parent_run_id,
            previous_confirmation_state=previous_confirmation_state,
        )
        return row, payload

    def restore(self, *, task: BusinessTask) -> CheckpointRestore:
        """Read Redis first and fall back to the PostgreSQL authority."""

        expected_version = int(task.checkpoint_version or 0)
        if expected_version < 1:
            raise ApiError(
                status_code=409,
                code="checkpoint_unavailable",
                message="task has no durable checkpoint",
            )

        cached = self.cache.get(
            user_id=task.user_id,
            member_id=task.member_id,
            task_id=task.id,
            thread_id=task.thread_id,
            checkpoint_version=expected_version,
        )
        if cached is not None and self._matches_task(cached, task):
            return CheckpointRestore(payload=cached, source="redis")

        row = self.db.scalar(
            select(TaskCheckpoint).where(
                TaskCheckpoint.task_id == task.id,
                TaskCheckpoint.user_id == task.user_id,
                TaskCheckpoint.member_id == task.member_id,
                TaskCheckpoint.thread_id == task.thread_id,
                TaskCheckpoint.checkpoint_version == expected_version,
            )
        )
        if row is None:
            raise ApiError(
                status_code=409,
                code="checkpoint_unavailable",
                message="authoritative task checkpoint is unavailable",
            )
        payload = self._payload_from_row(row)
        if not self._matches_task(payload, task):
            raise ApiError(
                status_code=409,
                code="checkpoint_scope_conflict",
                message="task checkpoint scope or version does not match the task",
            )
        # A miss, expiry, malformed value, or Redis outage all converge here.
        self.cache.set(payload)
        return CheckpointRestore(payload=payload, source="postgresql")

    def restore_state_for_continuation(
        self,
        *,
        task: BusinessTask,
        payload: TaskCheckpointPayload,
    ) -> dict[str, Any]:
        """Build a new working state without reviving old scratchpad data."""

        confirmation = payload.frozen_artifacts.get("confirmation", {})
        if not isinstance(confirmation, Mapping):
            confirmation = {}
        return {
            "task_id": task.id,
            "user_id": task.user_id,
            "member_id": task.member_id,
            "business_domain": task.business_domain,
            "intent": task.intent,
            "user_goal": task.user_input,
            "user_input": task.user_input,
            "input_payload": dict(task.input_payload or {}),
            "provider_mode": task.provider_mode,
            "human_confirmation_granted": True,
            "idempotency_key": task.idempotency_key,
            "status": "running",
            "final_answer": "",
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "model_call_trace": {},
            "degraded": False,
            "errors": [],
            "confirmation_request": self._mapping_value(confirmation, "request"),
            "confirmation_result": {},
            "confirmation_state": payload.confirmation_state,
            "confirmation_scope": self._mapping_value(confirmation, "scope"),
            "confirmation_draft": self._mapping_value(confirmation, "draft"),
            "safety_decisions": [],
            "final_output_safety": {},
            "final_answer_quality": {},
        }

    def restore_state_for_clarification(
        self,
        *,
        task: BusinessTask,
        payload: TaskCheckpointPayload,
    ) -> dict[str, Any]:
        """Restore only structured Triage slots for a new user turn."""

        triage_state = payload.frozen_artifacts.get("triage_state", {})
        if not isinstance(triage_state, Mapping):
            triage_state = {}
        return {
            "task_id": task.id,
            "user_id": task.user_id,
            "member_id": task.member_id,
            "business_domain": task.business_domain,
            "intent": payload.intent,
            "user_goal": task.user_input,
            "user_input": task.user_input,
            "input_payload": dict(task.input_payload or {}),
            "provider_mode": task.provider_mode,
            "human_confirmation_granted": False,
            "idempotency_key": task.idempotency_key,
            "status": "running",
            "final_answer": "",
            "final_claims": [],
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "model_call_trace": {},
            "degraded": False,
            "errors": [],
            "confirmation_request": {},
            "confirmation_result": {},
            "confirmation_state": "NONE",
            "confirmation_scope": {},
            "confirmation_draft": {},
            "safety_decisions": [],
            "final_output_safety": {},
            "final_answer_quality": {},
            "triage_state": dict(triage_state),
        }

    def restore_state_for_replay(
        self,
        *,
        task: BusinessTask,
        run: AgentRun | None,
        payload: TaskCheckpointPayload,
    ) -> dict[str, Any]:
        """Project frozen checkpoint artifacts back into an API replay state."""

        state = dict(payload.frozen_artifacts)
        state.update(
            {
                "run_id": payload.run_id,
                "task_id": task.id,
                "user_id": task.user_id,
                "member_id": task.member_id,
                "business_domain": task.business_domain,
                "intent": payload.intent,
                "user_input": task.user_input,
                "input_payload": dict(task.input_payload or {}),
                "provider_mode": task.provider_mode,
                "status": payload.status,
                "confirmation_state": payload.confirmation_state,
                "checkpoint_version": payload.checkpoint_version,
                "confirmation_version": payload.confirmation_version,
            }
        )
        # Tool/provider outputs remain in PostgreSQL audit rows and may be
        # reused for a replay response, but never enter the Redis projection.
        if run is not None and isinstance(run.raw_state, dict):
            for key in ("tool_calls", "provider_calls"):
                value = run.raw_state.get(key)
                if isinstance(value, list):
                    state[key] = value
        state.setdefault("source_refs", [item.model_dump(mode="json") for item in payload.source_refs])
        return state

    def latest_execution_record(
        self,
        *,
        task_id: str,
        user_id: str,
    ) -> TaskConfirmationRecord | None:
        return self.db.scalar(
            select(TaskConfirmationRecord)
            .where(
                TaskConfirmationRecord.task_id == task_id,
                TaskConfirmationRecord.user_id == user_id,
                TaskConfirmationRecord.next_state == "EXECUTED",
            )
            .order_by(TaskConfirmationRecord.created_at.desc())
        )

    def publish(self, payload: TaskCheckpointPayload) -> bool:
        """Best-effort cache refresh after the database transaction commits."""

        return self.cache.set(payload)

    def _project_payload(
        self,
        *,
        task: BusinessTask,
        run: AgentRun,
        state: Mapping[str, Any],
        checkpoint_version: int,
        confirmation_version: int,
        parent_run_id: str | None,
    ) -> TaskCheckpointPayload:
        confirmation_scope = state.get("confirmation_scope")
        if not isinstance(confirmation_scope, Mapping):
            confirmation_scope = {}
        confirmation_state = str(state.get("confirmation_state") or "NONE")
        confirmation = {
            "state": confirmation_state,
            "version": confirmation_version,
            "scope": self._drop_forbidden(dict(confirmation_scope)),
            "draft": self._drop_forbidden(self._as_dict(state.get("confirmation_draft"))),
            "request": self._drop_forbidden(self._as_dict(state.get("confirmation_request"))),
        }
        source_refs = self._source_pointers(state.get("source_refs"), task.member_id)
        frozen = {
            "business_domain": task.business_domain,
            "intent": str(state.get("intent") or task.intent),
            "final_answer": self._json_safe(state.get("final_answer", "")),
            "confirmation": confirmation,
            "confirmation_result": self._json_safe(state.get("confirmation_result", {})),
            "safety_flags": self._json_safe(state.get("safety_flags", [])),
            "safety_decisions": self._json_safe(state.get("safety_decisions", [])),
            "final_output_safety": self._json_safe(state.get("final_output_safety", {})),
            "final_answer_quality": self._json_safe(state.get("final_answer_quality", {})),
            "errors": self._json_safe(state.get("errors", [])),
            "degraded": bool(state.get("degraded", False)),
            "model_call_trace": self._json_safe(state.get("model_call_trace", {})),
            "run_trace": self._json_safe(state.get("run_trace", {})),
            "evaluation_result": self._json_safe(state.get("evaluation_result", {})),
            "run_summary": self._json_safe(state.get("run_summary", {})),
            "tool_evidence_refs": self._json_safe(
                state.get("context_envelope", {}).get("tool_evidence_refs", [])
                if isinstance(state.get("context_envelope"), Mapping)
                else []
            ),
            "rag_source_refs": self._json_safe(
                state.get("context_envelope", {}).get("rag_source_refs", [])
                if isinstance(state.get("context_envelope"), Mapping)
                else []
            ),
            "triage_state": self._json_safe(state.get("triage_state", {})),
            "external_action_status": "not_submitted",
        }
        return TaskCheckpointPayload(
            task_id=task.id,
            user_id=task.user_id,
            member_id=task.member_id,
            thread_id=task.thread_id,
            run_id=run.id,
            parent_run_id=parent_run_id,
            checkpoint_version=checkpoint_version,
            status=str(state.get("status") or "failed"),
            business_domain=task.business_domain,
            intent=str(state.get("intent") or task.intent),
            confirmation_state=confirmation_state,
            confirmation_version=confirmation_version,
            request_fingerprint=task.request_fingerprint,
            step_progress={
                "tool_call_count": len(state.get("tool_calls", [])),
                "provider_call_count": len(state.get("provider_calls", [])),
                "status": str(state.get("status") or "failed"),
                "completed": str(state.get("status")) in {"completed", "blocked", "failed"},
            },
            run_summary=self._json_safe(state.get("run_summary", {})),
            frozen_artifacts=self._drop_forbidden(frozen),
            source_refs=source_refs,
        )

    def _persist_confirmation_records(
        self,
        *,
        task: BusinessTask,
        run: AgentRun,
        state: Mapping[str, Any],
        confirmation_version: int,
        parent_run_id: str | None,
        previous_confirmation_state: str | None,
    ) -> None:
        scope = state.get("confirmation_scope")
        if not isinstance(scope, Mapping) or not scope.get("draft_id"):
            return
        current_state = str(state.get("confirmation_state") or "NONE")
        draft_version = int(scope.get("draft_version") or 1)
        draft_id = str(scope["draft_id"])
        if current_state == "DRAFT" and parent_run_id is None:
            self._add_confirmation_record(
                task=task,
                run=run,
                scope=scope,
                draft_version=draft_version,
                confirmation_version=confirmation_version,
                action="create_draft",
                previous_state="NONE",
                next_state="DRAFT",
                human_confirmation_present=False,
            )
        elif parent_run_id is not None and current_state == "EXECUTED":
            prior = previous_confirmation_state or "DRAFT"
            self._add_confirmation_record(
                task=task,
                run=run,
                scope=scope,
                draft_version=draft_version,
                confirmation_version=confirmation_version,
                action="confirm",
                previous_state=prior,
                next_state="CONFIRMED",
                human_confirmation_present=True,
            )
            self._add_confirmation_record(
                task=task,
                run=run,
                scope=scope,
                draft_version=draft_version,
                confirmation_version=confirmation_version,
                action="execute",
                previous_state="CONFIRMED",
                next_state="EXECUTED",
                human_confirmation_present=True,
            )

    def _add_confirmation_record(
        self,
        *,
        task: BusinessTask,
        run: AgentRun,
        scope: Mapping[str, Any],
        draft_version: int,
        confirmation_version: int,
        action: str,
        previous_state: str,
        next_state: str,
        human_confirmation_present: bool,
    ) -> None:
        self.db.add(
            TaskConfirmationRecord(
                id=str(uuid4()),
                user_id=task.user_id,
                member_id=task.member_id,
                task_id=task.id,
                run_id=run.id,
                draft_id=str(scope["draft_id"]),
                draft_version=draft_version,
                confirmation_version=confirmation_version,
                action=action,
                previous_state=previous_state,
                next_state=next_state,
                idempotency_key=str(scope.get("idempotency_key") or task.idempotency_key),
                request_fingerprint=str(scope.get("request_fingerprint") or task.request_fingerprint),
                actor_user_id=task.user_id,
                actor_member_id=task.member_id,
                human_confirmation_present=human_confirmation_present,
                metadata_payload={"external_action_status": "not_submitted"},
            )
        )

    @staticmethod
    def _next_confirmation_version(
        task: BusinessTask,
        state: Mapping[str, Any],
        parent_run_id: str | None,
    ) -> int:
        current = int(task.confirmation_version or 0)
        scope = state.get("confirmation_scope")
        scope_version = int(scope.get("draft_version") or 0) if isinstance(scope, Mapping) else 0
        if current == 0 and scope_version:
            return scope_version
        if parent_run_id is not None and str(state.get("confirmation_state")) in {
            "CONFIRMED",
            "EXECUTED",
        }:
            return max(current + 1, scope_version + 1, 1)
        return current

    @staticmethod
    def _payload_from_row(row: TaskCheckpoint) -> TaskCheckpointPayload:
        return TaskCheckpointPayload(
            task_id=row.task_id,
            user_id=row.user_id,
            member_id=row.member_id,
            thread_id=row.thread_id,
            run_id=row.run_id,
            parent_run_id=row.parent_run_id,
            checkpoint_version=row.checkpoint_version,
            status=row.status,
            business_domain=str(row.frozen_artifacts.get("business_domain") or "unknown"),
            intent=str(row.frozen_artifacts.get("intent") or "unknown"),
            confirmation_state=row.confirmation_state,
            confirmation_version=row.confirmation_version,
            request_fingerprint=row.request_fingerprint,
            step_progress=row.step_progress or {},
            run_summary=row.run_summary or {},
            frozen_artifacts=row.frozen_artifacts or {},
            source_refs=[CheckpointSourcePointer.model_validate(item) for item in row.source_refs or []],
        )

    @staticmethod
    def _matches_task(payload: TaskCheckpointPayload, task: BusinessTask) -> bool:
        return not any(
            (
                payload.task_id != task.id,
                payload.user_id != task.user_id,
                payload.member_id != task.member_id,
                payload.thread_id != task.thread_id,
                payload.checkpoint_version != int(task.checkpoint_version or 0),
                payload.request_fingerprint != task.request_fingerprint,
            )
        )

    @staticmethod
    def _source_pointers(value: Any, default_member_id: str) -> list[CheckpointSourcePointer]:
        pointers: list[CheckpointSourcePointer] = []
        if not isinstance(value, list):
            return pointers
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, Mapping) or not item.get("source_id"):
                continue
            source_id = str(item["source_id"])
            if source_id in seen:
                continue
            seen.add(source_id)
            pointers.append(
                CheckpointSourcePointer(
                    source_id=source_id,
                    source_type=str(item.get("source_type") or "agent_inference"),
                    document_id=_optional_str(item.get("document_id")),
                    document_version=_optional_str(item.get("document_version")),
                    chunk_id=_optional_str(item.get("chunk_id")),
                    retrieval_mode=_optional_str(item.get("retrieval_mode")),
                    provider=_optional_str(item.get("provider")),
                    member_id=_optional_str(item.get("member_id")) or default_member_id,
                    verified=bool(item.get("verified", False)),
                )
            )
        return pointers

    @staticmethod
    def _mapping_value(value: Mapping[str, Any], key: str) -> dict[str, Any]:
        item = value.get(key)
        return dict(item) if isinstance(item, Mapping) else {}

    @classmethod
    def _as_dict(cls, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        try:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            return str(value)

    @classmethod
    def _drop_forbidden(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): cls._drop_forbidden(item)
                for key, item in value.items()
                if str(key).casefold() not in _FORBIDDEN_WORKING_KEYS
            }
        if isinstance(value, list):
            return [cls._drop_forbidden(item) for item in value]
        if isinstance(value, tuple):
            return [cls._drop_forbidden(item) for item in value]
        return cls._json_safe(value)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


__all__ = ["CheckpointRestore", "TaskCheckpointService"]

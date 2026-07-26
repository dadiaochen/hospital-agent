"""Application service for the 4B business-task runtime.

The service owns the task lifecycle and persistence boundary.  API routes do not
invoke the graph or write runtime trace rows directly, while the graph does not
need to know how its state is persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.product_workflow import FamilyHealthProductWorkflow
from app.agent.product_artifacts import add_product_artifacts
from app.core.exceptions import ApiError, InvalidRequestError, ResourceNotFoundError
from app.models import (
    AgentRun,
    AgentToolCall,
    BusinessTask,
    FamilyMember,
    ProviderCall,
    SourceReference,
)
from app.models.base import utc_now
from app.schemas.business import BusinessDomain, ProviderMode


@dataclass(frozen=True)
class BusinessTaskExecution:
    """A service result containing the persisted task and graph state."""

    task: BusinessTask
    run: AgentRun | None
    state: dict[str, Any]
    idempotent_replay: bool = False


class BusinessTaskService:
    """Coordinate a business task without leaking ORM details into the API."""

    def __init__(self, db: Session, *, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def create_task(
        self,
        *,
        business_domain: BusinessDomain,
        member_id: str,
        user_input: str,
        input_payload: dict[str, Any] | None,
        idempotency_key: str,
        provider_mode: ProviderMode,
        human_confirmation_granted: bool = False,
    ) -> BusinessTaskExecution:
        """Create and execute a task, or replay the same idempotent request."""

        self._get_member(member_id)
        payload = input_payload or {}
        request_fingerprint = self._fingerprint(
            business_domain=business_domain,
            member_id=member_id,
            user_input=user_input,
            input_payload=payload,
            provider_mode=provider_mode,
        )

        existing = self.db.scalar(
            select(BusinessTask).where(
                BusinessTask.user_id == self.user_id,
                BusinessTask.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise ApiError(
                    status_code=409,
                    code="idempotency_conflict",
                    message="idempotency_key already used with a different request",
                )
            return self._replay(existing)

        task_id = str(uuid4())
        run_id = str(uuid4())
        task = BusinessTask(
            id=task_id,
            user_id=self.user_id,
            member_id=member_id,
            business_domain=business_domain,
            intent="pending",
            status="running",
            user_input=user_input,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            input_payload=payload,
            output_payload={},
            need_human_confirmation=False,
            degraded=False,
            current_run_id=run_id,
        )
        run = AgentRun(
            id=run_id,
            user_id=self.user_id,
            member_id=member_id,
            user_goal=user_input,
            intent="pending",
            status="running",
            safety_result={},
            raw_state={},
        )
        self.db.add(task)
        self.db.add(run)
        try:
            self.db.flush()
            state = FamilyHealthProductWorkflow(self.db).invoke(
                run_id=run_id,
                task_id=task_id,
                user_id=self.user_id,
                member_id=member_id,
                business_domain=business_domain,
                user_input=user_input,
                input_payload=payload,
                provider_mode=provider_mode,
                human_confirmation_granted=human_confirmation_granted,
                idempotency_key=idempotency_key,
            )
            self._persist_state(task, run, state)
            self.db.commit()
            self.db.refresh(task)
            self.db.refresh(run)
            return BusinessTaskExecution(task=task, run=run, state=state)
        except ApiError:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiError(
                status_code=503,
                code="persistence_error",
                message="business task persistence failed",
                details=[{"type": exc.__class__.__name__}],
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive production boundary
            self.db.rollback()
            self.db.add_all([task, run])
            self._mark_failed(task, run, exc)
            self.db.commit()
            self.db.refresh(task)
            self.db.refresh(run)
            return BusinessTaskExecution(
                task=task,
                run=run,
                state=self._failure_state(task, run),
            )

    def confirm_task(
        self,
        *,
        task_id: str,
        idempotency_key: str,
    ) -> BusinessTaskExecution:
        """Resume a confirmation-gated task after explicit user confirmation."""

        task = self._get_task(task_id)
        if task.idempotency_key != idempotency_key:
            raise ApiError(
                status_code=409,
                code="idempotency_conflict",
                message="confirmation idempotency_key does not match the task",
            )
        if task.status == "completed":
            return self._replay(task)
        if task.status != "needs_confirmation" or not task.need_human_confirmation:
            raise InvalidRequestError("task is not waiting for human confirmation")

        previous_run = self.db.scalar(
            select(AgentRun).where(
                AgentRun.id == task.current_run_id,
                AgentRun.user_id == self.user_id,
            )
        )
        if previous_run is None or not isinstance(previous_run.raw_state, dict):
            raise ApiError(
                status_code=409,
                code="missing_runtime_state",
                message="task cannot be resumed because its runtime state is unavailable",
            )

        run_id = str(uuid4())
        run = AgentRun(
            id=run_id,
            user_id=self.user_id,
            member_id=task.member_id,
            user_goal=task.user_input,
            intent=task.intent,
            status="running",
            safety_result={},
            raw_state={},
        )
        task.current_run_id = run_id
        task.status = "running"
        task.need_human_confirmation = False
        self.db.add(run)
        try:
            self.db.flush()
            state = FamilyHealthProductWorkflow(self.db).resume_confirmation(
                previous_run.raw_state,
                run_id=run_id,
                human_confirmation_granted=True,
            )
            self._persist_state(task, run, state, confirmed_at=utc_now())
            self.db.commit()
            self.db.refresh(task)
            self.db.refresh(run)
            return BusinessTaskExecution(task=task, run=run, state=state)
        except ApiError:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiError(
                status_code=503,
                code="persistence_error",
                message="business task confirmation persistence failed",
                details=[{"type": exc.__class__.__name__}],
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive production boundary
            self.db.rollback()
            self._mark_failed(task, run, exc)
            self.db.commit()
            self.db.refresh(task)
            self.db.refresh(run)
            return BusinessTaskExecution(
                task=task,
                run=run,
                state=self._failure_state(task, run),
            )

    def get_task(self, task_id: str) -> BusinessTask:
        return self._get_task(task_id)

    def get_execution(self, task_id: str) -> BusinessTaskExecution:
        """Return the latest frozen execution artifacts for a task."""

        return self._replay(self._get_task(task_id))

    def list_tasks(
        self,
        *,
        member_id: str | None = None,
        status: str | None = None,
        business_domain: str | None = None,
    ) -> list[BusinessTask]:
        statement = select(BusinessTask).where(BusinessTask.user_id == self.user_id)
        if member_id is not None:
            self._get_member(member_id)
            statement = statement.where(BusinessTask.member_id == member_id)
        if status is not None:
            statement = statement.where(BusinessTask.status == status)
        if business_domain is not None:
            statement = statement.where(BusinessTask.business_domain == business_domain)
        return list(
            self.db.scalars(
                statement.order_by(BusinessTask.created_at.desc())
            ).all()
        )

    def list_sources(self, task_id: str) -> list[SourceReference]:
        self._get_task(task_id)
        return list(
            self.db.scalars(
                select(SourceReference)
                .where(
                    SourceReference.task_id == task_id,
                    SourceReference.user_id == self.user_id,
                )
                .order_by(SourceReference.created_at.asc())
            ).all()
        )

    def _get_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member not found")
        return member

    def _get_task(self, task_id: str) -> BusinessTask:
        task = self.db.scalar(
            select(BusinessTask).where(
                BusinessTask.id == task_id,
                BusinessTask.user_id == self.user_id,
            )
        )
        if task is None:
            raise ResourceNotFoundError("business task not found")
        return task

    def _replay(self, task: BusinessTask) -> BusinessTaskExecution:
        run = None
        if task.current_run_id:
            run = self.db.scalar(
                select(AgentRun).where(
                    AgentRun.id == task.current_run_id,
                    AgentRun.user_id == self.user_id,
                )
            )
        state = self._state_for_replay(task, run)
        return BusinessTaskExecution(
            task=task,
            run=run,
            state=state,
            idempotent_replay=True,
        )

    def _persist_state(
        self,
        task: BusinessTask,
        run: AgentRun,
        state: dict[str, Any],
        *,
        confirmed_at: datetime | None = None,
    ) -> None:
        state.setdefault("latency_ms", self._duration_ms(run.started_at, utc_now()))
        add_product_artifacts(state)
        safe_state = self._json_safe(state)
        output_payload = self._output_payload(state)
        status = str(state.get("status") or "failed")
        now = utc_now()

        task.intent = str(state.get("intent") or task.intent)
        task.status = status
        task.output_payload = output_payload
        task.need_human_confirmation = bool(
            state.get("need_human_confirmation", False)
        )
        task.degraded = bool(state.get("degraded", False))
        task.last_error = self._last_error(state)
        if confirmed_at is not None:
            task.confirmed_at = confirmed_at

        run.intent = task.intent
        run.status = status
        run.final_answer = self._optional_text(state.get("final_answer"))
        run.need_human_confirmation = task.need_human_confirmation
        run.safety_result = {
            "flags": self._json_safe(state.get("safety_flags", [])),
            "errors": self._json_safe(state.get("errors", [])),
        }
        run.raw_state = safe_state
        run.ended_at = now
        run.duration_ms = self._duration_ms(run.started_at, now)
        run.step_count = self._step_count(state)
        run.task_success = status == "completed"
        evaluation = state.get("evaluation_result")
        if isinstance(evaluation, dict):
            run.task_success = bool(evaluation.get("task_success"))
            run.groundedness_score = self._optional_float(
                evaluation.get("groundedness")
            )
            run.hallucination_flag = bool(
                evaluation.get("hallucination_detected", False)
            )
            if evaluation.get("human_confirmation_required"):
                run.human_confirmation_rate = float(
                    bool(evaluation.get("human_confirmation_present"))
                )

        self.db.execute(delete(AgentToolCall).where(AgentToolCall.run_id == run.id))
        self.db.execute(delete(ProviderCall).where(ProviderCall.run_id == run.id))
        self.db.execute(
            delete(SourceReference).where(SourceReference.run_id == run.id)
        )

        for item in state.get("tool_calls", []):
            if not isinstance(item, dict):
                continue
            self.db.add(
                AgentToolCall(
                    id=str(uuid4()),
                    run_id=run.id,
                    agent_role=self._optional_text(item.get("agent_role")),
                    tool_name=str(item.get("tool_name") or "unknown"),
                    tool_input=self._json_safe(item.get("tool_input", {})),
                    tool_output=self._json_safe(
                        item.get("tool_output", item.get("output", {}))
                    ),
                    latency_ms=self._optional_int(item.get("latency_ms")),
                    success=bool(item.get("success", False)),
                    error_message=self._optional_text(item.get("error_message")),
                    error_type=self._optional_text(item.get("error_type")),
                    fallback_action=self._optional_text(item.get("fallback_action")),
                    schema_valid=bool(item.get("schema_valid", False)),
                )
            )

        for item in state.get("provider_calls", []):
            if not isinstance(item, dict):
                continue
            self.db.add(
                ProviderCall(
                    id=str(uuid4()),
                    task_id=task.id,
                    run_id=run.id,
                    provider_name=self._optional_text(
                        item.get("provider_name", item.get("provider"))
                    ),
                    provider_mode=self._optional_text(
                        item.get("provider_mode", item.get("mode"))
                    ),
                    operation=self._optional_text(item.get("operation")),
                    request_payload=self._json_safe(
                        item.get("request_payload", item.get("request", {}))
                    ),
                    response_payload=self._json_safe(
                        item.get("response_payload", item.get("response", {}))
                    ),
                    success=bool(item.get("success", False)),
                    retryable=bool(item.get("retryable", False)),
                    degraded=bool(item.get("degraded", False)),
                    fallback_reason=self._optional_text(item.get("fallback_reason")),
                    latency_ms=self._optional_int(item.get("latency_ms")),
                )
            )

        source_rows: set[tuple[str, str]] = set()
        for item in state.get("source_refs", []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "")
            source_type = str(item.get("source_type") or "agent_inference")
            if not source_id or (source_id, source_type) in source_rows:
                continue
            source_rows.add((source_id, source_type))
            metadata = dict(item.get("source_metadata") or {})
            for key in ("title", "category", "score", "source_name", "safety_level"):
                if key in item and key not in metadata:
                    metadata[key] = self._json_safe(item[key])
            self.db.add(
                SourceReference(
                    id=str(uuid4()),
                    user_id=self.user_id,
                    task_id=task.id,
                    run_id=run.id,
                    source_id=source_id,
                    source_type=source_type,
                    document_id=self._optional_text(item.get("document_id")),
                    document_version=self._optional_text(item.get("document_version")),
                    chunk_id=self._optional_text(item.get("chunk_id")),
                    retrieval_mode=self._optional_text(item.get("retrieval_mode")),
                    provider=self._optional_text(item.get("provider")),
                    member_id=self._optional_text(item.get("member_id"))
                    or task.member_id,
                    verified=bool(item.get("verified", False)),
                    source_metadata=metadata,
                )
            )

    def _mark_failed(self, task: BusinessTask, run: AgentRun, exc: Exception) -> None:
        task.status = "failed"
        task.last_error = "business task execution failed"
        task.output_payload = {
            "final_answer": "Task could not be completed. Please retry or contact support.",
            "errors": ["execution_failed"],
        }
        run.status = "failed"
        run.final_answer = task.output_payload["final_answer"]
        run.safety_result = {"errors": ["execution_failed"]}
        run.raw_state = self._failure_state(task, run, error_type=exc.__class__.__name__)
        run.ended_at = utc_now()
        run.duration_ms = self._duration_ms(run.started_at, run.ended_at)
        run.task_success = False

    def _failure_state(
        self,
        task: BusinessTask,
        run: AgentRun,
        *,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "task_id": task.id,
            "user_id": self.user_id,
            "member_id": task.member_id,
            "business_domain": task.business_domain,
            "intent": task.intent,
            "user_input": task.user_input,
            "status": "failed",
            "final_answer": task.output_payload.get("final_answer", ""),
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "degraded": False,
            "errors": [error_type or "execution_failed"],
        }

    @staticmethod
    def _state_for_replay(
        task: BusinessTask,
        run: AgentRun | None,
    ) -> dict[str, Any]:
        if run is not None and isinstance(run.raw_state, dict) and run.raw_state:
            return run.raw_state
        payload = task.output_payload if isinstance(task.output_payload, dict) else {}
        return {
            "run_id": task.current_run_id,
            "task_id": task.id,
            "user_id": task.user_id,
            "member_id": task.member_id,
            "business_domain": task.business_domain,
            "intent": task.intent,
            "user_input": task.user_input,
            "input_payload": task.input_payload,
            "status": task.status,
            "final_answer": payload.get("final_answer", ""),
            "need_human_confirmation": task.need_human_confirmation,
            "confirmation_request": payload.get("confirmation_request"),
            "confirmation_result": payload.get("confirmation_result"),
            "safety_flags": payload.get("safety_flags", []),
            "source_refs": payload.get("source_refs", []),
            "tool_calls": [],
            "provider_calls": [],
            "degraded": task.degraded,
            "errors": payload.get("errors", []),
        }

    @staticmethod
    def _output_payload(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "final_answer": state.get("final_answer"),
            "confirmation_request": state.get("confirmation_request"),
            "confirmation_result": state.get("confirmation_result"),
            "safety_flags": state.get("safety_flags", []),
            "source_refs": state.get("source_refs", []),
            "errors": state.get("errors", []),
        }

    @staticmethod
    def _last_error(state: dict[str, Any]) -> str | None:
        errors = state.get("errors")
        if not isinstance(errors, list) or not errors:
            return None
        return str(errors[-1])

    @staticmethod
    def _step_count(state: dict[str, Any]) -> int:
        return len(state.get("tool_calls", [])) + len(state.get("provider_calls", []))

    @staticmethod
    def _fingerprint(
        *,
        business_domain: str,
        member_id: str,
        user_input: str,
        input_payload: dict[str, Any],
        provider_mode: str,
    ) -> str:
        normalized = json.dumps(
            {
                "business_domain": business_domain,
                "member_id": member_id,
                "user_input": user_input,
                "input_payload": input_payload,
                "provider_mode": provider_mode,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return cls._json_safe(value.model_dump(mode="json"))
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text else None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
        if started_at is None or ended_at is None:
            return None
        try:
            return max(0, int((ended_at - started_at).total_seconds() * 1000))
        except TypeError:
            start = started_at.replace(tzinfo=None)
            end = ended_at.replace(tzinfo=None)
            return max(0, int((end - start).total_seconds() * 1000))

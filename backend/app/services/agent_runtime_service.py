from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from time import perf_counter
from typing import Any
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.langgraph_workflow import LangGraphAgentWorkflow
from app.agent.run_trace_schemas import build_tool_call_id
from app.agent.runtime_schemas import PersistedRunArtifacts, RuntimeRequestContext
from app.agent.workflow_schemas import WorkflowRunRequest
from app.core.exceptions import ApiError, ResourceNotFoundError
from app.models import AgentRun, AgentToolCall, FamilyMember
from app.models.base import utc_now
from app.tools.db_tools import create_db_tool_registry
from app.tools.tool_schemas import ToolResult


_RUNTIME_NAMESPACE = UUID("c7471de5-b087-4d72-af40-e847e080bd85")


@dataclass(frozen=True)
class AgentRuntimeExecution:
    run: AgentRun
    artifacts: PersistedRunArtifacts
    idempotent_replay: bool


class AgentRuntimeService:
    """Execute and persist one scoped Agent workflow run."""

    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def create_run(
        self,
        *,
        member_id: str,
        idempotency_key: str,
        user_input: str,
        medication_name: str | None,
        city: str | None,
        human_confirmation_granted: bool,
    ) -> AgentRuntimeExecution:
        if human_confirmation_granted:
            raise ApiError(
                status_code=422,
                code="confirmation_requires_continuation",
                message="initial runs cannot grant action confirmation",
            )
        self._require_scoped_member(member_id)
        run_id = self._stable_run_id(idempotency_key)
        task_id = f"task:{run_id}"
        request_values = {
            "kind": "create",
            "member_id": member_id,
            "user_input": user_input,
            "medication_name": medication_name,
            "city": city,
            "human_confirmation_granted": human_confirmation_granted,
        }
        return self._execute(
            run_id=run_id,
            task_id=task_id,
            member_id=member_id,
            user_goal=user_input,
            request_fingerprint=_fingerprint(request_values),
            medication_name=medication_name,
            city=city,
            human_confirmation_granted=human_confirmation_granted,
            resumed_from=None,
        )

    def continue_run(
        self,
        previous_run_id: str,
        *,
        idempotency_key: str,
        confirmation_message: str,
    ) -> AgentRuntimeExecution:
        previous_run = self._get_scoped_run(previous_run_id)
        run_id = self._continuation_run_id(previous_run_id)
        request_values = {
            "kind": "continue",
            "previous_run_id": previous_run_id,
            "idempotency_key": idempotency_key,
            "confirmation_message": confirmation_message,
        }
        request_fingerprint = _fingerprint(request_values)
        existing = self.db.get(AgentRun, run_id)
        if existing is not None:
            return self._replay_existing(existing, request_fingerprint)
        if previous_run.status != "needs_confirmation":
            raise ApiError(
                status_code=409,
                code="run_not_continuable",
                message="only a needs_confirmation run can be continued",
            )

        previous_artifacts = self._load_artifacts(previous_run)
        return self._execute(
            run_id=run_id,
            task_id=previous_artifacts.task_id,
            member_id=previous_artifacts.run_summary.member_id,
            user_goal=confirmation_message,
            request_fingerprint=request_fingerprint,
            medication_name=previous_artifacts.request_context.medication_name,
            city=previous_artifacts.request_context.city,
            human_confirmation_granted=True,
            resumed_from=previous_artifacts,
        )

    def get_artifacts(self, run_id: str) -> tuple[AgentRun, PersistedRunArtifacts]:
        run = self._get_scoped_run(run_id)
        return run, self._load_artifacts(run)

    def _execute(
        self,
        *,
        run_id: str,
        task_id: str,
        member_id: str,
        user_goal: str,
        request_fingerprint: str,
        medication_name: str | None,
        city: str | None,
        human_confirmation_granted: bool,
        resumed_from: PersistedRunArtifacts | None,
    ) -> AgentRuntimeExecution:
        existing = self.db.get(AgentRun, run_id)
        if existing is not None:
            return self._replay_existing(existing, request_fingerprint)

        started_at = utc_now()
        run = AgentRun(
            id=run_id,
            user_id=self.user_id,
            member_id=member_id,
            user_goal=user_goal,
            status="running",
            need_human_confirmation=False,
            safety_result={},
            raw_state={
                "schema_version": "2g2.pending",
                "task_id": task_id,
                "request_fingerprint": request_fingerprint,
            },
            started_at=started_at,
        )
        self.db.add(run)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.get(AgentRun, run_id)
            if existing is None:
                raise
            return self._replay_existing(existing, request_fingerprint)

        restored_source_ids = _restored_source_ids(resumed_from)
        workflow_request = WorkflowRunRequest(
            run_id=run_id,
            task_id=task_id,
            user_id=self.user_id,
            member_id=member_id,
            user_input=user_goal,
            medication_name=medication_name,
            city=city,
            human_confirmation_granted=human_confirmation_granted,
            resume_context=(
                resumed_from.to_resume_context()
                if resumed_from is not None
                else None
            ),
        )

        started = perf_counter()
        workflow: LangGraphAgentWorkflow | None = None
        try:
            workflow = LangGraphAgentWorkflow(
                tool_registry=create_db_tool_registry(
                    self.db,
                    include_confirmation_tools=True,
                )
            )
            result = workflow.run(workflow_request)
            artifacts = PersistedRunArtifacts(
                task_id=task_id,
                plan=result.plan,
                run_trace=result.run_trace,
                model_call_trace=result.model_result.trace,
                run_summary=result.run_summary,
                tool_evidence_refs=tuple(result.context_envelope.tool_evidence_refs),
                rag_source_refs=tuple(result.context_envelope.rag_source_refs),
                evaluation_result=result.evaluation_result,
                request_context=RuntimeRequestContext(
                    medication_name=medication_name,
                    city=city,
                ),
                request_fingerprint=request_fingerprint,
                resumed_from_run_id=(
                    resumed_from.run_trace.run_id
                    if resumed_from is not None
                    else None
                ),
                restored_source_ids=restored_source_ids,
            )
            self._persist_success(
                run,
                result.tool_results,
                artifacts,
                duration_ms=_elapsed_ms(started),
                step_count=len(result.visited_nodes),
            )
            return AgentRuntimeExecution(
                run=run,
                artifacts=artifacts,
                idempotent_replay=False,
            )
        except Exception as exc:
            self._mark_failed(run, task_id, request_fingerprint, exc)
            raise ApiError(
                status_code=500,
                code="agent_run_failed",
                message="agent workflow execution failed",
            ) from exc
        finally:
            if workflow is not None:
                workflow.close()

    def _persist_success(
        self,
        run: AgentRun,
        tool_results: Sequence[ToolResult],
        artifacts: PersistedRunArtifacts,
        *,
        duration_ms: int,
        step_count: int,
    ) -> None:
        self.db.execute(delete(AgentToolCall).where(AgentToolCall.run_id == run.id))
        self.db.add_all(
            [
                AgentToolCall(
                    id=build_tool_call_id(run.id, index, result.tool_name),
                    run_id=run.id,
                    agent_role=result.agent_role or "unknown",
                    tool_name=result.tool_name,
                    tool_input=result.tool_input,
                    tool_output=result.output if result.success else None,
                    latency_ms=result.latency_ms,
                    success=result.success,
                    error_message=result.error_message,
                    error_type=result.error_type,
                    fallback_action=result.fallback_action,
                    schema_valid=result.schema_valid,
                )
                for index, result in enumerate(tool_results, start=1)
            ]
        )
        evaluation = artifacts.evaluation_result
        safety = artifacts.run_trace.safety_trace
        run.intent = artifacts.plan.intent
        run.status = artifacts.run_summary.final_status
        run.final_answer = artifacts.run_trace.final_answer.content
        run.need_human_confirmation = run.status == "needs_confirmation"
        run.safety_result = {
            "flags": list(safety.flags),
            "blocked": safety.blocked,
            "requires_human_confirmation": safety.requires_human_confirmation,
            "safety_recall": evaluation.safety_recall,
            "context_isolation_passed": evaluation.context_isolation_passed,
        }
        run.raw_state = artifacts.model_dump(mode="json")
        run.ended_at = utc_now()
        run.duration_ms = duration_ms
        run.step_count = step_count
        run.task_success = evaluation.task_success
        run.groundedness_score = evaluation.groundedness
        run.hallucination_flag = evaluation.hallucination_detected
        run.human_confirmation_rate = (
            1.0
            if not evaluation.human_confirmation_required
            or evaluation.human_confirmation_present
            else 0.0
        )
        try:
            self.db.commit()
            self.db.refresh(run)
        except SQLAlchemyError as exc:
            self.db.rollback()
            self._mark_failed(
                run,
                artifacts.task_id,
                artifacts.request_fingerprint,
                exc,
            )
            raise

    def _mark_failed(
        self,
        run: AgentRun,
        task_id: str,
        request_fingerprint: str,
        exc: Exception,
    ) -> None:
        self.db.rollback()
        persisted = self.db.get(AgentRun, run.id)
        if persisted is None:
            return
        persisted.status = "failed"
        persisted.ended_at = utc_now()
        persisted.raw_state = {
            "schema_version": "2g2.failure.v1",
            "task_id": task_id,
            "request_fingerprint": request_fingerprint,
            "error_type": type(exc).__name__,
        }
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()

    def _replay_existing(
        self,
        run: AgentRun,
        request_fingerprint: str,
    ) -> AgentRuntimeExecution:
        if run.user_id != self.user_id:
            raise ResourceNotFoundError("agent run was not found")
        stored_fingerprint = run.raw_state.get("request_fingerprint")
        if stored_fingerprint != request_fingerprint:
            raise ApiError(
                status_code=409,
                code="idempotency_conflict",
                message="idempotency key was already used for a different request",
            )
        artifacts = self._load_artifacts(run)
        return AgentRuntimeExecution(
            run=run,
            artifacts=artifacts,
            idempotent_replay=True,
        )

    def _load_artifacts(self, run: AgentRun) -> PersistedRunArtifacts:
        try:
            return PersistedRunArtifacts.model_validate(run.raw_state)
        except ValidationError as exc:
            raise ApiError(
                status_code=409 if run.status in {"running", "failed"} else 500,
                code="runtime_artifact_unavailable",
                message="frozen runtime artifacts are not available for this run",
            ) from exc

    def _get_scoped_run(self, run_id: str) -> AgentRun:
        run = self.db.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.user_id == self.user_id,
            )
        )
        if run is None:
            raise ResourceNotFoundError("agent run was not found")
        return run

    def _require_scoped_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member was not found")
        return member

    def _stable_run_id(self, idempotency_key: str) -> str:
        return str(uuid5(_RUNTIME_NAMESPACE, f"{self.user_id}:{idempotency_key}"))

    def _continuation_run_id(self, previous_run_id: str) -> str:
        return str(
            uuid5(
                _RUNTIME_NAMESPACE,
                f"{self.user_id}:continue:{previous_run_id}",
            )
        )


def _restored_source_ids(
    artifacts: PersistedRunArtifacts | None,
) -> tuple[str, ...]:
    if artifacts is None:
        return ()
    return tuple(
        dict.fromkeys(
            [
                *(ref.source_id for ref in artifacts.tool_evidence_refs),
                *(ref.source_id for ref in artifacts.rag_source_refs),
            ]
        )
    )


def _fingerprint(values: dict[str, Any]) -> str:
    rendered = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(rendered.encode("utf-8")).hexdigest()


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


__all__ = ["AgentRuntimeExecution", "AgentRuntimeService"]

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.agent.runtime_schemas import PersistedRunArtifacts
from app.api.dependencies import DbSession, DemoUser
from app.schemas.agent_audit import (
    AgentRunListQuery,
    AgentRunListResponse,
    AgentRunResponse,
    AgentToolCallListResponse,
    AgentToolCallResponse,
)
from app.schemas.agent_runtime import (
    AgentRunArtifactsResponse,
    AgentRunContinueRequest,
    AgentRunCreateRequest,
    AgentRunExecutionResponse,
)
from app.schemas.common import ApiErrorResponse
from app.services.agent_runtime_service import (
    AgentRuntimeExecution,
    AgentRuntimeService,
)
from app.services.read_api_service import ReadApiService


router = APIRouter(prefix="/agent-runs")


@router.post(
    "",
    response_model=AgentRunExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
    },
)
def create_agent_run(
    request: AgentRunCreateRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> AgentRunExecutionResponse:
    execution = AgentRuntimeService(db, demo_user.id).create_run(
        member_id=request.member_id,
        idempotency_key=request.idempotency_key,
        user_input=request.user_input,
        medication_name=request.medication_name,
        city=request.city,
        human_confirmation_granted=request.human_confirmation_granted,
    )
    return _execution_response(execution)


@router.get("", response_model=AgentRunListResponse)
def list_agent_runs(
    query: Annotated[AgentRunListQuery, Depends()],
    db: DbSession,
    demo_user: DemoUser,
) -> AgentRunListResponse:
    runs = ReadApiService(db, demo_user.id).list_agent_runs(query.member_id)
    return AgentRunListResponse(
        items=[AgentRunResponse.model_validate(run) for run in runs]
    )


@router.get(
    "/{run_id}",
    response_model=AgentRunResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_agent_run(
    run_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> AgentRunResponse:
    run = ReadApiService(db, demo_user.id).get_agent_run(run_id)
    return AgentRunResponse.model_validate(run)


@router.get(
    "/{run_id}/tool-calls",
    response_model=AgentToolCallListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def list_agent_tool_calls(
    run_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> AgentToolCallListResponse:
    calls = ReadApiService(db, demo_user.id).list_agent_tool_calls(run_id)
    return AgentToolCallListResponse(
        items=[AgentToolCallResponse.model_validate(call) for call in calls]
    )


@router.get(
    "/{run_id}/artifacts",
    response_model=AgentRunArtifactsResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
    },
)
def get_agent_run_artifacts(
    run_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> AgentRunArtifactsResponse:
    run, artifacts = AgentRuntimeService(db, demo_user.id).get_artifacts(run_id)
    return _artifacts_response(run.status, artifacts)


@router.post(
    "/{run_id}/continue",
    response_model=AgentRunExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
    },
)
def continue_agent_run(
    run_id: str,
    request: AgentRunContinueRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> AgentRunExecutionResponse:
    execution = AgentRuntimeService(db, demo_user.id).continue_run(
        run_id,
        idempotency_key=request.idempotency_key,
        confirmation_message=request.confirmation_message,
    )
    return _execution_response(execution)


def _execution_response(
    execution: AgentRuntimeExecution,
) -> AgentRunExecutionResponse:
    return AgentRunExecutionResponse(
        run=AgentRunResponse.model_validate(execution.run),
        artifacts=_artifacts_response(
            execution.run.status,
            execution.artifacts,
        ),
        idempotent_replay=execution.idempotent_replay,
    )


def _artifacts_response(
    status_value: str,
    artifacts: PersistedRunArtifacts,
) -> AgentRunArtifactsResponse:
    return AgentRunArtifactsResponse(
        run_id=artifacts.run_trace.run_id,
        task_id=artifacts.task_id,
        status=status_value,
        run_trace=artifacts.run_trace,
        model_call_trace=artifacts.model_call_trace,
        run_summary=artifacts.run_summary,
        tool_evidence_refs=artifacts.tool_evidence_refs,
        rag_source_refs=artifacts.rag_source_refs,
        safety_trace=artifacts.run_trace.safety_trace,
        evaluation_result=artifacts.evaluation_result,
        resumed_from_run_id=artifacts.resumed_from_run_id,
        restored_source_ids=artifacts.restored_source_ids,
        external_action_status=artifacts.external_action_status,
    )

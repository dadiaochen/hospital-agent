from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import DbSession, DemoUser
from app.schemas.agent_audit import (
    AgentRunListQuery,
    AgentRunListResponse,
    AgentRunResponse,
    AgentToolCallListResponse,
    AgentToolCallResponse,
)
from app.schemas.common import ApiErrorResponse
from app.services.read_api_service import ReadApiService


router = APIRouter(prefix="/agent-runs")


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

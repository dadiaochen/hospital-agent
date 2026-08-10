from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies import DbSession, DemoUser
from app.agent.context_schemas import RunSummary
from app.agent.eval_schemas import EvaluationResult
from app.agent.model_gateway_schemas import ModelCallTrace
from app.agent.run_trace_schemas import RunTrace
from app.schemas.business import BusinessDomain, SourceRef
from app.schemas.business_task import (
    BusinessTaskClarificationRequest,
    BusinessTaskConfirmRequest,
    BusinessTaskCreateRequest,
    BusinessTaskExecutionResponse,
    BusinessTaskListResponse,
    BusinessTaskSummaryResponse,
    SourceReferenceResponse,
)
from app.schemas.common import ApiErrorResponse
from app.services.business_task_service import BusinessTaskExecution, BusinessTaskService


router = APIRouter(prefix="/business-tasks")


def _summary(task: object) -> BusinessTaskSummaryResponse:
    return BusinessTaskSummaryResponse.model_validate(task)


def _execution_response(
    execution: BusinessTaskExecution,
) -> BusinessTaskExecutionResponse:
    state = execution.state
    source_refs = [
        SourceRef.model_validate(item)
        for item in state.get("source_refs", [])
        if isinstance(item, dict)
    ]
    return BusinessTaskExecutionResponse(
        task=_summary(execution.task),
        run_id=execution.run.id if execution.run is not None else state.get("run_id"),
        final_answer=str(state.get("final_answer") or ""),
        status=str(state.get("status") or execution.task.status),
        need_human_confirmation=bool(
            state.get("need_human_confirmation", execution.task.need_human_confirmation)
        ),
        confirmation_request=state.get("confirmation_request") or {},
        confirmation_result=state.get("confirmation_result") or {},
        confirmation_state=str(state.get("confirmation_state") or "NONE"),
        confirmation_draft=state.get("confirmation_draft") or {},
        safety_flags=[str(item) for item in state.get("safety_flags", [])],
        scope_decision=(
            state.get("scope_decision")
            if isinstance(state.get("scope_decision"), dict)
            else None
        ),
        source_refs=source_refs,
        tool_calls=[item for item in state.get("tool_calls", []) if isinstance(item, dict)],
        provider_calls=[
            item for item in state.get("provider_calls", []) if isinstance(item, dict)
        ],
        model_call_trace=(
            ModelCallTrace.model_validate(state["model_call_trace"])
            if isinstance(state.get("model_call_trace"), dict)
            and state.get("model_call_trace")
            else None
        ),
        degraded=bool(state.get("degraded", execution.task.degraded)),
        run_trace=(
            RunTrace.model_validate(state["run_trace"])
            if isinstance(state.get("run_trace"), dict)
            else None
        ),
        run_summary=(
            RunSummary.model_validate(state["run_summary"])
            if isinstance(state.get("run_summary"), dict)
            else None
        ),
        evaluation_result=(
            EvaluationResult.model_validate(state["evaluation_result"])
            if isinstance(state.get("evaluation_result"), dict)
            else None
        ),
        idempotent_replay=execution.idempotent_replay,
        checkpoint_version=execution.checkpoint_version,
        confirmation_version=execution.confirmation_version,
        checkpoint_source=execution.checkpoint_source,
        resumed_from_run_id=execution.resumed_from_run_id,
        restored_source_ids=execution.restored_source_ids,
    )


@router.post(
    "",
    response_model=BusinessTaskExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
def create_business_task(
    request: BusinessTaskCreateRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> BusinessTaskExecutionResponse:
    execution = BusinessTaskService(db, user_id=demo_user.id).create_task(
        business_domain=request.business_domain,
        member_id=request.member_id,
        user_input=request.user_input,
        input_payload=request.input_payload,
        idempotency_key=request.idempotency_key,
        provider_mode=request.provider_mode,
        thread_id=request.thread_id,
        human_confirmation_granted=request.human_confirmation_granted,
    )
    return _execution_response(execution)


@router.get("", response_model=BusinessTaskListResponse)
def list_business_tasks(
    db: DbSession,
    demo_user: DemoUser,
    member_id: Annotated[str | None, Query(min_length=1)] = None,
    task_status: Annotated[str | None, Query(alias="status", min_length=1)] = None,
    business_domain: BusinessDomain | None = None,
) -> BusinessTaskListResponse:
    tasks = BusinessTaskService(db, user_id=demo_user.id).list_tasks(
        member_id=member_id,
        status=task_status,
        business_domain=business_domain,
    )
    return BusinessTaskListResponse(
        items=[_summary(task) for task in tasks],
        total=len(tasks),
    )


@router.get(
    "/{task_id}/sources",
    response_model=list[SourceReferenceResponse],
    responses={404: {"model": ApiErrorResponse}},
)
def list_business_task_sources(
    task_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> list[SourceReferenceResponse]:
    sources = BusinessTaskService(db, user_id=demo_user.id).list_sources(task_id)
    return [SourceReferenceResponse.model_validate(source) for source in sources]


@router.get(
    "/{task_id}/artifacts",
    response_model=BusinessTaskExecutionResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_business_task_artifacts(
    task_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> BusinessTaskExecutionResponse:
    execution = BusinessTaskService(db, user_id=demo_user.id).get_execution(task_id)
    return _execution_response(execution)


@router.post(
    "/{task_id}/confirm",
    response_model=BusinessTaskExecutionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
def confirm_business_task(
    task_id: str,
    request: BusinessTaskConfirmRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> BusinessTaskExecutionResponse:
    execution = BusinessTaskService(db, user_id=demo_user.id).confirm_task(
        task_id=task_id,
        idempotency_key=request.idempotency_key,
        checkpoint_version=request.checkpoint_version,
        confirmation_version=request.confirmation_version,
    )
    return _execution_response(execution)


@router.post(
    "/{task_id}/clarify",
    response_model=BusinessTaskExecutionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
def clarify_business_task(
    task_id: str,
    request: BusinessTaskClarificationRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> BusinessTaskExecutionResponse:
    execution = BusinessTaskService(db, user_id=demo_user.id).clarify_task(
        task_id=task_id,
        user_input=request.user_input,
        input_payload=request.input_payload,
        idempotency_key=request.idempotency_key,
        checkpoint_version=request.checkpoint_version,
    )
    return _execution_response(execution)


@router.get(
    "/{task_id}",
    response_model=BusinessTaskSummaryResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_business_task(
    task_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> BusinessTaskSummaryResponse:
    task = BusinessTaskService(db, user_id=demo_user.id).get_task(task_id)
    return _summary(task)

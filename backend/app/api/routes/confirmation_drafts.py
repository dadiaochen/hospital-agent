from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.confirmation_draft import (
    ConfirmationDraftCreateRequest,
    ConfirmationDraftDecisionRequest,
    ConfirmationDraftListResponse,
    ConfirmationDraftResponse,
    ConfirmationDraftStatus,
    ConfirmationDraftType,
)
from app.services.confirmation_draft_api_service import ConfirmationDraftApiService


router = APIRouter(prefix="/confirmation-drafts")


@router.post(
    "",
    response_model=ConfirmationDraftResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
def create_confirmation_draft(
    request: ConfirmationDraftCreateRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> ConfirmationDraftResponse:
    result = ConfirmationDraftApiService(db, demo_user.id).create_draft(
        member_id=request.member_id,
        draft_type=request.draft_type,
        idempotency_key=request.idempotency_key,
        run_id=request.run_id,
        summary=request.summary,
        payload=request.payload,
        human_confirmation_granted=request.human_confirmation_granted,
    )
    return ConfirmationDraftResponse.model_validate(result)


@router.get("", response_model=ConfirmationDraftListResponse)
def list_confirmation_drafts(
    db: DbSession,
    demo_user: DemoUser,
    member_id: Annotated[str | None, Query(min_length=1)] = None,
    draft_type: ConfirmationDraftType | None = None,
    draft_status: Annotated[
        ConfirmationDraftStatus | None,
        Query(alias="status"),
    ] = None,
) -> ConfirmationDraftListResponse:
    items = ConfirmationDraftApiService(db, demo_user.id).list_drafts(
        member_id=member_id,
        draft_type=draft_type,
        status=draft_status,
    )
    return ConfirmationDraftListResponse(
        items=[ConfirmationDraftResponse.model_validate(item) for item in items]
    )


@router.get(
    "/{draft_type}/{draft_id}",
    response_model=ConfirmationDraftResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_confirmation_draft(
    draft_type: ConfirmationDraftType,
    draft_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> ConfirmationDraftResponse:
    result = ConfirmationDraftApiService(db, demo_user.id).get_draft(
        draft_type,
        draft_id,
    )
    return ConfirmationDraftResponse.model_validate(result)


@router.post(
    "/{draft_type}/{draft_id}/confirm",
    response_model=ConfirmationDraftResponse,
    responses={404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}},
)
def confirm_confirmation_draft(
    draft_type: ConfirmationDraftType,
    draft_id: str,
    request: ConfirmationDraftDecisionRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> ConfirmationDraftResponse:
    result = ConfirmationDraftApiService(db, demo_user.id).decide_draft(
        draft_type=draft_type,
        draft_id=draft_id,
        target_status="confirmed",
        idempotency_key=request.idempotency_key,
        human_confirmation_present=request.human_confirmation_present,
        note=request.note,
    )
    return ConfirmationDraftResponse.model_validate(result)


@router.post(
    "/{draft_type}/{draft_id}/reject",
    response_model=ConfirmationDraftResponse,
    responses={404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}},
)
def reject_confirmation_draft(
    draft_type: ConfirmationDraftType,
    draft_id: str,
    request: ConfirmationDraftDecisionRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> ConfirmationDraftResponse:
    result = ConfirmationDraftApiService(db, demo_user.id).decide_draft(
        draft_type=draft_type,
        draft_id=draft_id,
        target_status="rejected",
        idempotency_key=request.idempotency_key,
        human_confirmation_present=request.human_confirmation_present,
        note=request.note,
    )
    return ConfirmationDraftResponse.model_validate(result)

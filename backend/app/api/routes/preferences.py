from fastapi import APIRouter, status

from app.api.dependencies import DbSession, DemoUser
from app.schemas.checkpoint import ConfirmedPreferenceResponse, ConfirmedPreferenceWriteRequest
from app.schemas.common import ApiErrorResponse
from app.services.preference_service import ConfirmedPreferenceService


router = APIRouter(prefix="/preferences")


@router.post(
    "",
    response_model=ConfirmedPreferenceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
def write_confirmed_preference(
    request: ConfirmedPreferenceWriteRequest,
    db: DbSession,
    demo_user: DemoUser,
) -> ConfirmedPreferenceResponse:
    execution = ConfirmedPreferenceService(db, user_id=demo_user.id).write(
        task_id=request.task_id,
        member_id=request.member_id,
        preference_type=request.preference_type,
        preference_value=request.preference_value,
        source_id=request.source_id,
        source_version=request.source_version,
        confirmation_version=request.confirmation_version,
        preference_version=request.preference_version,
        idempotency_key=request.idempotency_key,
        human_confirmation_granted=request.human_confirmation_granted,
    )
    return ConfirmedPreferenceResponse(
        id=execution.preference.id,
        user_id=execution.preference.user_id,
        member_id=execution.preference.member_id,
        task_id=execution.preference.task_id,
        preference_type=execution.preference.preference_type,
        preference_value=execution.preference.preference_value,
        preference_version=execution.preference.preference_version,
        consent_version=execution.preference.consent_version,
        source_id=execution.preference.source_id,
        source_version=execution.preference.source_version,
        status=execution.preference.status,
        revocable=execution.preference.revocable,
        revoked_at=execution.preference.revoked_at,
        created_at=execution.preference.created_at,
        updated_at=execution.preference.updated_at,
        idempotent_replay=execution.idempotent_replay,
    )

from fastapi import APIRouter

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.family import (
    FamilyMemberHealthProfileResponse,
    FamilyMemberListResponse,
    FamilyMemberResponse,
    HealthProfileResponse,
)
from app.services.read_api_service import ReadApiService


router = APIRouter(prefix="/family-members")


@router.get("", response_model=FamilyMemberListResponse)
def list_family_members(db: DbSession, demo_user: DemoUser) -> FamilyMemberListResponse:
    members = ReadApiService(db, demo_user.id).list_family_members()
    return FamilyMemberListResponse(
        items=[FamilyMemberResponse.model_validate(member) for member in members]
    )


@router.get(
    "/{member_id}/health-profile",
    response_model=FamilyMemberHealthProfileResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_health_profile(
    member_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> FamilyMemberHealthProfileResponse:
    member, profile = ReadApiService(db, demo_user.id).get_member_health_profile(member_id)
    return FamilyMemberHealthProfileResponse(
        member=FamilyMemberResponse.model_validate(member),
        profile=HealthProfileResponse.model_validate(profile),
    )

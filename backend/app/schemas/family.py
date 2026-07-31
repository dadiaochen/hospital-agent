from datetime import date
from typing import Any

from app.schemas.common import ApiSchema


class FamilyMemberResponse(ApiSchema):
    id: str
    name: str
    relationship: str
    gender: str | None
    birthday: date | None
    default_address: str | None


class FamilyMemberListResponse(ApiSchema):
    items: list[FamilyMemberResponse]


class HealthProfileResponse(ApiSchema):
    member_id: str
    chronic_disease_tags: list[str]
    allergies: list[str]
    current_medications: list[dict[str, Any]]
    health_notes: str | None
    safety_notes: list[str]


class FamilyMemberHealthProfileResponse(ApiSchema):
    member: FamilyMemberResponse
    profile: HealthProfileResponse

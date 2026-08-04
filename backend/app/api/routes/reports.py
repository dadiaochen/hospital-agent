from fastapi import APIRouter

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.reports import ReportDetailResponse, ReportListResponse
from app.services.report_read_service import ReportReadService


router = APIRouter(prefix="/family-members/{member_id}/reports")


@router.get(
    "",
    response_model=ReportListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def list_reports(
    member_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> ReportListResponse:
    return ReportReadService(db, demo_user.id).list_reports(member_id)


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_report(
    member_id: str,
    report_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> ReportDetailResponse:
    return ReportReadService(db, demo_user.id).get_report(member_id, report_id)

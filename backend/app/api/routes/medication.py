from fastapi import APIRouter

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.medication import (
    MedicineBoxItemResponse,
    MedicineBoxListResponse,
    PrescriptionListResponse,
    PrescriptionResponse,
    PurchaseRecordListResponse,
    PurchaseRecordResponse,
)
from app.services.read_api_service import ReadApiService


router = APIRouter(prefix="/family-members/{member_id}")


@router.get(
    "/medicine-box",
    response_model=MedicineBoxListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def list_medicine_box_items(
    member_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> MedicineBoxListResponse:
    items = ReadApiService(db, demo_user.id).list_medicine_box_items(member_id)
    return MedicineBoxListResponse(
        items=[MedicineBoxItemResponse.model_validate(item) for item in items]
    )


@router.get(
    "/prescriptions",
    response_model=PrescriptionListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def list_prescriptions(
    member_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> PrescriptionListResponse:
    items = ReadApiService(db, demo_user.id).list_prescriptions(member_id)
    return PrescriptionListResponse(
        items=[PrescriptionResponse.model_validate(item) for item in items]
    )


@router.get(
    "/purchase-records",
    response_model=PurchaseRecordListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def list_purchase_records(
    member_id: str,
    db: DbSession,
    demo_user: DemoUser,
) -> PurchaseRecordListResponse:
    items = ReadApiService(db, demo_user.id).list_purchase_records(member_id)
    return PurchaseRecordListResponse(
        items=[PurchaseRecordResponse.model_validate(item) for item in items]
    )

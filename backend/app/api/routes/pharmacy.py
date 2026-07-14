from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.pharmacy import (
    PharmacyInventoryItemResponse,
    PharmacyInventoryListResponse,
    PharmacyInventoryQuery,
)
from app.services.read_api_service import ReadApiService


router = APIRouter(prefix="/pharmacy-inventory")


@router.get(
    "",
    response_model=PharmacyInventoryListResponse,
    responses={422: {"model": ApiErrorResponse}},
)
def list_pharmacy_inventory(
    query: Annotated[PharmacyInventoryQuery, Depends()],
    db: DbSession,
    demo_user: DemoUser,
) -> PharmacyInventoryListResponse:
    rows = ReadApiService(db, demo_user.id).list_pharmacy_inventory(
        medicine_name=query.medicine_name,
        city=query.city,
    )
    return PharmacyInventoryListResponse(
        items=[
            PharmacyInventoryItemResponse(
                inventory_id=inventory.id,
                pharmacy_id=pharmacy.id,
                pharmacy_name=pharmacy.name,
                city=pharmacy.city,
                address=pharmacy.address,
                supports_delivery=pharmacy.supports_delivery,
                supports_pickup=pharmacy.supports_pickup,
                contact_phone=pharmacy.contact_phone,
                medicine_name=inventory.medicine_name,
                stock_quantity=inventory.stock_quantity,
                delivery_options=list(inventory.delivery_options or []),
                safety_note=inventory.safety_note,
            )
            for inventory, pharmacy in rows
        ]
    )

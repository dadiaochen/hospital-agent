from pydantic import Field

from app.schemas.common import ApiSchema


class PharmacyInventoryQuery(ApiSchema):
    medicine_name: str | None = Field(default=None, min_length=1)
    city: str | None = Field(default=None, min_length=1)


class PharmacyInventoryItemResponse(ApiSchema):
    inventory_id: str
    pharmacy_id: str
    pharmacy_name: str
    city: str
    address: str | None
    supports_delivery: bool
    supports_pickup: bool
    contact_phone: str | None
    medicine_name: str
    stock_quantity: int
    delivery_options: list[str]
    safety_note: str | None


class PharmacyInventoryListResponse(ApiSchema):
    items: list[PharmacyInventoryItemResponse]

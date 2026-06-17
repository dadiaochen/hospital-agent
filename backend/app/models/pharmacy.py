from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.medication import PurchaseRecord
    from app.models.plans import PurchasePlan


class Pharmacy(IDMixin, TimestampMixin, Base):
    __tablename__ = "pharmacies"
    __table_args__ = (UniqueConstraint("name", "city", name="uq_pharmacy_name_city"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    supports_delivery: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_pickup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(32))

    inventory_items: Mapped[list["PharmacyInventory"]] = relationship(back_populates="pharmacy")
    purchase_records: Mapped[list["PurchaseRecord"]] = relationship(back_populates="pharmacy")
    purchase_plans: Mapped[list["PurchasePlan"]] = relationship(back_populates="pharmacy")


class PharmacyInventory(IDMixin, TimestampMixin, Base):
    __tablename__ = "pharmacy_inventory"
    __table_args__ = (UniqueConstraint("pharmacy_id", "medicine_name", name="uq_pharmacy_inventory_medicine"),)

    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), nullable=False, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_options: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(String(255))

    pharmacy: Mapped["Pharmacy"] = relationship(back_populates="inventory_items")


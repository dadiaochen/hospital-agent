from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidRequestError, ResourceNotFoundError
from app.models import (
    AgentRun,
    AgentToolCall,
    FamilyMember,
    HealthProfile,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    PurchaseRecord,
)


class ReadApiService:
    """Read-only API use cases scoped to the configured demo user."""

    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def list_family_members(self) -> list[FamilyMember]:
        return list(
            self.db.scalars(
                select(FamilyMember)
                .where(FamilyMember.user_id == self.user_id)
                .order_by(FamilyMember.relationship, FamilyMember.name)
            )
        )

    def get_member_health_profile(
        self,
        member_id: str,
    ) -> tuple[FamilyMember, HealthProfile]:
        member = self._get_scoped_member(member_id)
        profile = self.db.scalar(
            select(HealthProfile).where(HealthProfile.member_id == member.id)
        )
        if profile is None:
            raise ResourceNotFoundError("health profile was not found for this member")
        return member, profile

    def list_medicine_box_items(self, member_id: str) -> list[MedicineBoxItem]:
        self._get_scoped_member(member_id)
        return list(
            self.db.scalars(
                select(MedicineBoxItem)
                .where(MedicineBoxItem.member_id == member_id)
                .order_by(MedicineBoxItem.medicine_name)
            )
        )

    def list_prescriptions(self, member_id: str) -> list[Prescription]:
        self._get_scoped_member(member_id)
        return list(
            self.db.scalars(
                select(Prescription)
                .where(Prescription.member_id == member_id)
                .order_by(Prescription.issued_at.desc())
            )
        )

    def list_purchase_records(self, member_id: str) -> list[PurchaseRecord]:
        self._get_scoped_member(member_id)
        return list(
            self.db.scalars(
                select(PurchaseRecord)
                .where(PurchaseRecord.member_id == member_id)
                .order_by(PurchaseRecord.purchased_at.desc())
            )
        )

    def list_pharmacy_inventory(
        self,
        *,
        medicine_name: str | None,
        city: str | None,
    ) -> list[tuple[PharmacyInventory, Pharmacy]]:
        if medicine_name is None and city is None:
            raise InvalidRequestError("medicine_name or city is required")

        statement: Select[tuple[PharmacyInventory, Pharmacy]] = (
            select(PharmacyInventory, Pharmacy)
            .join(Pharmacy, PharmacyInventory.pharmacy_id == Pharmacy.id)
            .order_by(Pharmacy.city, Pharmacy.name, PharmacyInventory.medicine_name)
        )
        if medicine_name is not None:
            statement = statement.where(
                PharmacyInventory.medicine_name.ilike(f"%{medicine_name}%")
            )
        if city is not None:
            statement = statement.where(Pharmacy.city == city)
        return list(self.db.execute(statement).all())

    def list_agent_runs(self, member_id: str | None = None) -> list[AgentRun]:
        if member_id is not None:
            self._get_scoped_member(member_id)

        statement = (
            select(AgentRun)
            .where(AgentRun.user_id == self.user_id)
            .order_by(AgentRun.started_at.desc())
        )
        if member_id is not None:
            statement = statement.where(AgentRun.member_id == member_id)
        return list(self.db.scalars(statement))

    def get_agent_run(self, run_id: str) -> AgentRun:
        run = self.db.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.user_id == self.user_id,
            )
        )
        if run is None:
            raise ResourceNotFoundError("agent run was not found")
        return run

    def list_agent_tool_calls(self, run_id: str) -> list[AgentToolCall]:
        self.get_agent_run(run_id)
        return list(
            self.db.scalars(
                select(AgentToolCall)
                .where(AgentToolCall.run_id == run_id)
                .order_by(AgentToolCall.created_at)
            )
        )

    def _get_scoped_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member was not found")
        return member

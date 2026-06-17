"""处方和购药记录服务"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models import Prescription, PurchaseRecord


class PrescriptionService:
    """处方服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_prescriptions(self, member_id: str) -> list[Prescription]:
        """获取家庭成员的所有处方"""
        return (
            self.db.query(Prescription)
            .filter(Prescription.member_id == member_id)
            .order_by(Prescription.issued_at.desc())
            .all()
        )

    def get_valid_prescriptions(self, member_id: str) -> list[Prescription]:
        """获取有效的处方"""
        today = date.today()
        return (
            self.db.query(Prescription)
            .filter(
                Prescription.member_id == member_id,
                Prescription.status == "valid",
                Prescription.expires_at >= today
            )
            .all()
        )

    def check_prescription_validity(self, prescription_id: str) -> dict:
        """
        检查处方有效性

        返回：
        {
            "is_valid": bool,
            "expires_at": date,
            "days_until_expiry": int,
            "doctor_confirmation_required": bool,
            "reason": str
        }
        """
        prescription = self.db.query(Prescription).filter(Prescription.id == prescription_id).first()

        if not prescription:
            return {
                "is_valid": False,
                "reason": "处方不存在"
            }

        today = date.today()

        if prescription.status != "valid":
            return {
                "is_valid": False,
                "expires_at": prescription.expires_at,
                "reason": f"处方状态为 {prescription.status}"
            }

        if prescription.expires_at and prescription.expires_at < today:
            return {
                "is_valid": False,
                "expires_at": prescription.expires_at,
                "reason": "处方已过期"
            }

        days_until_expiry = (prescription.expires_at - today).days if prescription.expires_at else None

        return {
            "is_valid": True,
            "expires_at": prescription.expires_at,
            "days_until_expiry": days_until_expiry,
            "doctor_confirmation_required": prescription.doctor_confirmation_required,
            "reason": "处方有效"
        }

    def get_purchase_history(self, member_id: str, limit: int = 10) -> list[PurchaseRecord]:
        """获取购药历史"""
        return (
            self.db.query(PurchaseRecord)
            .filter(PurchaseRecord.member_id == member_id)
            .order_by(PurchaseRecord.purchased_at.desc())
            .limit(limit)
            .all()
        )

    def get_latest_purchase(self, member_id: str, medicine_name: str) -> PurchaseRecord | None:
        """获取指定药品的最近一次购药记录"""
        return (
            self.db.query(PurchaseRecord)
            .filter(
                PurchaseRecord.member_id == member_id,
                PurchaseRecord.medicine_name == medicine_name
            )
            .order_by(PurchaseRecord.purchased_at.desc())
            .first()
        )

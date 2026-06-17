"""用户和家庭成员服务"""
from sqlalchemy.orm import Session
from app.models import User, FamilyMember, HealthProfile


class UserService:
    """用户服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_user_by_phone(self, phone: str) -> User | None:
        """根据手机号获取用户"""
        return self.db.query(User).filter(User.phone == phone).first()

    def get_family_members(self, user_id: str) -> list[FamilyMember]:
        """获取用户的所有家庭成员"""
        return (
            self.db.query(FamilyMember)
            .filter(FamilyMember.user_id == user_id)
            .all()
        )

    def get_family_member(self, member_id: str) -> FamilyMember | None:
        """获取指定家庭成员"""
        return self.db.query(FamilyMember).filter(FamilyMember.id == member_id).first()

    def get_health_profile(self, member_id: str) -> HealthProfile | None:
        """获取健康档案"""
        return (
            self.db.query(HealthProfile)
            .filter(HealthProfile.member_id == member_id)
            .first()
        )

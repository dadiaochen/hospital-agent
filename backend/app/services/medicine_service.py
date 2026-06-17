"""药品和药箱服务"""
import re
from datetime import date
from sqlalchemy.orm import Session
from app.models import MedicineBoxItem, Prescription, PurchaseRecord


class MedicineService:
    """药品服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_medicine_box(self, member_id: str) -> list[MedicineBoxItem]:
        """获取家庭成员的药箱"""
        return (
            self.db.query(MedicineBoxItem)
            .filter(MedicineBoxItem.member_id == member_id)
            .all()
        )

    def calculate_remaining_days(self, item: MedicineBoxItem) -> int | None:
        """
        动态计算剩余天数

        注意：这个方法用于替代存储在数据库中的 estimated_remaining_days 字段
        """
        if not item.remaining_quantity or not item.dosage or not item.frequency:
            return None

        daily_usage = self._parse_daily_usage(item.dosage, item.frequency)
        if daily_usage <= 0:
            return None

        return item.remaining_quantity // daily_usage

    def _parse_daily_usage(self, dosage: str, frequency: str) -> int:
        """
        解析每日用量

        示例：
        - dosage="每次1片", frequency="每日3次" -> 3
        - dosage="每次2袋", frequency="早晚各1次" -> 4
        """
        # 简化实现：提取频次中的数字
        if "每日" in frequency:
            match = re.search(r'(\d+)次', frequency)
            if match:
                times_per_day = int(match.group(1))
                # 提取剂量中的数字
                dosage_match = re.search(r'(\d+)', dosage)
                if dosage_match:
                    amount = int(dosage_match.group(1))
                    return times_per_day * amount
                return times_per_day

        # 处理"早晚各1次"这种情况
        if "早晚" in frequency:
            dosage_match = re.search(r'(\d+)', dosage)
            if dosage_match:
                amount = int(dosage_match.group(1))
                return 2 * amount  # 早晚各一次 = 2次
            return 2

        return 1

    def check_low_stock(self, member_id: str, threshold_days: int = 7) -> list[dict]:
        """检查低库存药品"""
        items = self.get_medicine_box(member_id)
        low_stock_items = []

        for item in items:
            remaining_days = self.calculate_remaining_days(item)
            if remaining_days and remaining_days <= threshold_days:
                low_stock_items.append({
                    "medicine_name": item.medicine_name,
                    "remaining_quantity": item.remaining_quantity,
                    "remaining_days": remaining_days,
                    "item_id": item.id,
                    "member_id": member_id,
                })

        return low_stock_items

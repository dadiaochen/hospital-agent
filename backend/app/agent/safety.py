from __future__ import annotations

from pydantic import BaseModel, Field

from app.safety.policies import needs_medical_safety_interception


class SafetyDecision(BaseModel):
    blocked: bool = False
    flags: list[str] = Field(default_factory=list)
    message: str | None = None
    requires_human_confirmation: bool = False


URGENT_SYMPTOM_PATTERNS = (
    "胸痛",
    "呼吸困难",
    "昏迷",
    "意识不清",
    "抽搐",
    "大出血",
    "严重过敏",
    "chest pain",
    "difficulty breathing",
    "unconscious",
)


def evaluate_safety(message: str) -> SafetyDecision:
    """在业务动作和用户可见输出前执行医疗安全检查。"""

    normalized = (message or "").casefold()
    if any(pattern.casefold() in normalized for pattern in URGENT_SYMPTOM_PATTERNS):
        return SafetyDecision(
            blocked=True,
            flags=["urgent_symptom", "manual_review_required"],
            message=(
                "检测到可能需要立即处理的严重症状。系统不能继续常规流程，"
                "请立即联系急救服务或尽快前往有急诊能力的医疗机构。"
            ),
            requires_human_confirmation=True,
        )

    if needs_medical_safety_interception(message):
        return SafetyDecision(
            blocked=True,
            flags=["medication_adjustment", "doctor_confirmation_required"],
            message=(
                "该请求涉及自行停药、加量、减量、换药或修改处方。"
                "系统不能替代医生作出决定，请联系接诊医生确认。"
            ),
            requires_human_confirmation=True,
        )

    return SafetyDecision()

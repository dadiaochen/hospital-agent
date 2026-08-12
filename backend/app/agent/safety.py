from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.safety.policies import needs_medical_safety_interception


SafetyStage = Literal["request", "action", "final_output"]
SafetyOutcome = Literal["allow", "block", "require_human_confirmation"]


class SafetyDecision(ContractModel):
    stage: SafetyStage = "request"
    outcome: SafetyOutcome | None = None
    blocked: bool = False
    flags: list[NonEmptyStr] = Field(default_factory=list)
    message: str | None = None
    requires_human_confirmation: bool = False
    member_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def normalize_outcome(self) -> "SafetyDecision":
        expected: SafetyOutcome = (
            "block"
            if self.blocked
            else "require_human_confirmation"
            if self.requires_human_confirmation
            else "allow"
        )
        if self.outcome is None:
            self.outcome = expected
        elif self.outcome != expected:
            raise ValueError(
                "outcome must match blocked and requires_human_confirmation"
            )
        return self


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

CROSS_MEMBER_ACCESS_PATTERNS = (
    "另一个家庭成员",
    "其他家庭成员",
    "别的家庭成员",
    "读取他人",
    "查看他人",
    "他人的健康资料",
    "other family member",
)

STALE_SOURCE_BYPASS_PATTERNS = (
    "使用过期的旧版",
    "过期的旧版规则",
    "使用过期规则",
    "使用旧版规则",
    "忽略最新版本",
    "跳过版本校验",
    "expired rule",
    "stale source",
)


def evaluate_safety(
    message: str,
    *,
    stage: SafetyStage = "request",
) -> SafetyDecision:
    """在业务动作和用户可见输出前执行医疗安全检查。"""

    normalized = (message or "").casefold()
    if any(
        pattern.casefold() in normalized
        for pattern in CROSS_MEMBER_ACCESS_PATTERNS
    ):
        return SafetyDecision(
            stage=stage,
            blocked=True,
            flags=["member_isolation_violation", "manual_review_required"],
            message="该请求试图读取其他家庭成员的医疗信息，系统已按成员隔离规则阻断。",
            requires_human_confirmation=True,
        )

    if any(
        pattern.casefold() in normalized
        for pattern in STALE_SOURCE_BYPASS_PATTERNS
    ):
        return SafetyDecision(
            stage=stage,
            blocked=True,
            flags=["stale_source_rejected", "manual_review_required"],
            message="该请求试图绕过知识版本校验，系统已拒绝使用过期来源。",
            requires_human_confirmation=True,
        )

    if any(pattern.casefold() in normalized for pattern in URGENT_SYMPTOM_PATTERNS):
        return SafetyDecision(
            stage=stage,
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
            stage=stage,
            blocked=True,
            flags=["medication_adjustment", "doctor_confirmation_required"],
            message=(
                "该请求涉及自行停药、加量、减量、换药或修改处方。"
                "系统不能替代医生作出决定，请联系接诊医生确认。"
            ),
            requires_human_confirmation=True,
        )

    return SafetyDecision(stage=stage)


__all__ = ["SafetyDecision", "SafetyOutcome", "SafetyStage", "evaluate_safety"]

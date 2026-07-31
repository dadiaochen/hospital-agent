from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ModelOutputSafetyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    blocked: bool
    requires_human_confirmation: bool
    flags: tuple[str, ...] = Field(default_factory=tuple)


@runtime_checkable
class ModelOutputSafetyChecker(Protocol):
    def check(self, output: BaseModel) -> ModelOutputSafetyResult:
        """Check parsed model output before it can reach an Agent node."""


class RuleBasedModelOutputSafetyChecker:
    _PATTERNS = {
        "unsafe_medication_instruction": (
            re.compile(r"(建议|可以|应该|请|直接).{0,12}(自行)?(加量|减量|停药|换药)"),
            re.compile(
                r"\byou\s+(?:can|should)\b.{0,30}\b(?:increase|decrease|stop|switch)\b",
                re.IGNORECASE,
            ),
        ),
        "confirmation_bypass": (
            re.compile(r"(无需|不用|跳过).{0,10}(医生|人工|用户)?(确认|审核)"),
            re.compile(
                r"\b(?:without|skip)\b.{0,20}\b(?:doctor|human|user)?\s*confirmation\b",
                re.IGNORECASE,
            ),
        ),
        "auto_prescription_claim": (
            re.compile(r"自动开方"),
            re.compile(r"\bauto[- ]?prescrib", re.IGNORECASE),
        ),
        "external_action_claim": (
            re.compile(r"已(?:经)?(?:替你)?(?:下单|提交医院|创建提醒|完成支付)"),
            re.compile(
                r"\b(?:placed the order|submitted to the hospital|completed payment)\b",
                re.IGNORECASE,
            ),
        ),
    }

    def check(self, output: BaseModel) -> ModelOutputSafetyResult:
        text = json.dumps(output.model_dump(mode="json"), ensure_ascii=False)
        flags = tuple(
            flag
            for flag, patterns in self._PATTERNS.items()
            if any(pattern.search(text) for pattern in patterns)
        )
        return ModelOutputSafetyResult(
            passed=not flags,
            blocked=bool(flags),
            requires_human_confirmation=bool(flags),
            flags=flags,
        )


__all__ = [
    "ModelOutputSafetyChecker",
    "ModelOutputSafetyResult",
    "RuleBasedModelOutputSafetyChecker",
]

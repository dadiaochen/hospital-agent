from __future__ import annotations


HIGH_RISK_MEDICATION_PATTERNS = (
    "加量",
    "减量",
    "停药",
    "换药",
    "换成",
    "替代",
    "多吃",
    "少吃",
    "修改剂量",
    "修改处方",
    "increase dose",
    "decrease dose",
    "stop medication",
    "switch medication",
)

NEGATION_PREFIXES = (
    "不要",
    "不需要",
    "无需",
    "不能",
    "不得",
    "禁止",
    "不修改",
    "不调整",
)


def needs_medical_safety_interception(message: str) -> bool:
    normalized = (message or "").casefold()
    for pattern in HIGH_RISK_MEDICATION_PATTERNS:
        normalized_pattern = pattern.casefold()
        start = normalized.find(normalized_pattern)
        if start < 0:
            continue
        prefix = normalized[max(0, start - 6) : start]
        negated = any(negation in prefix for negation in NEGATION_PREFIXES)
        if "不能" in prefix and prefix.endswith("能"):
            # "能不能加量" is a question about a risky action, not a
            # statement that the user refuses or forbids that action.
            negated = False
        if negated:
            continue
        return True
    return False

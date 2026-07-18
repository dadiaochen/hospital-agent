HIGH_RISK_MEDICATION_PATTERNS = [
    "加量",
    "减量",
    "停药",
    "换药",
    "换成",
    "替代",
    "能不能多吃",
]


def needs_medical_safety_interception(message: str) -> bool:
    return any(pattern in message for pattern in HIGH_RISK_MEDICATION_PATTERNS)


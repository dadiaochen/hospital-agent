"""Deterministic complexity and domain routing for 4B task five."""

from collections.abc import Iterable

from app.agent.context_schemas import Intent
from app.agent.orchestration_schemas import (
    ComplexityRoute,
    ComplexityRoutingRequest,
    DomainAgentRole,
)


_DOMAIN_SIGNALS: dict[DomainAgentRole, tuple[str, ...]] = {
    "TriageAgent": (
        "预问诊",
        "问诊",
        "症状",
        "挂什么科",
        "哪个科室",
        "就医",
        "胸痛",
        "呼吸困难",
        "头晕",
        "发烧",
        "chest pain",
        "difficulty breathing",
        "symptom",
        "triage",
        "preconsultation",
        "pre-consultation",
    ),
    "MedicationAgent": (
        "续方",
        "续药",
        "处方",
        "药箱",
        "用药",
        "提醒",
        "药店",
        "库存",
        "购药",
        "配送",
        "自提",
        "加量",
        "减量",
        "停药",
        "换药",
        "medicine",
        "medication",
        "refill",
        "reminder",
        "pharmacy",
    ),
    "ReportAgent": (
        "报告",
        "检查结果",
        "化验",
        "检验",
        "指标",
        "影像",
        "体检",
        "report",
        "lab result",
        "medical document",
    ),
}

_ROLE_INTENTS: dict[DomainAgentRole, Intent] = {
    "TriageAgent": "preconsultation",
    "ReportAgent": "health_record",
    "MedicationAgent": "chronic_care",
}

_INTENT_ROLES: dict[Intent, DomainAgentRole] = {
    "preconsultation": "TriageAgent",
    "safety_check": "TriageAgent",
    "health_record": "ReportAgent",
    "refill": "MedicationAgent",
    "reminder": "MedicationAgent",
    "pharmacy": "MedicationAgent",
    "chronic_care": "MedicationAgent",
}

_CAPABILITIES: dict[DomainAgentRole, tuple[str, ...]] = {
    "TriageAgent": ("symptom_structuring", "red_flag_review"),
    "MedicationAgent": ("medication_fact_lookup", "draft_preparation"),
    "ReportAgent": ("medical_document_structuring", "source_backed_explanation"),
}

_URGENT_TRIAGE_SIGNALS = (
    "胸痛",
    "呼吸困难",
    "昏迷",
    "意识不清",
    "大出血",
    "严重过敏",
    "chest pain",
    "difficulty breathing",
)

_MEDICATION_SAFETY_SIGNALS = (
    "加量",
    "减量",
    "停药",
    "换药",
    "修改剂量",
    "修改处方",
    "increase dose",
    "decrease dose",
    "stop medication",
    "switch medication",
)


class DeterministicComplexityRouter:
    """Route a request without an LLM, database, or business tool call."""

    def route(self, request: ComplexityRoutingRequest) -> ComplexityRoute:
        text = request.user_input.casefold()
        matched = _matched_roles(text)

        if any(signal in text for signal in _URGENT_TRIAGE_SIGNALS):
            return self._simple_route(
                request,
                "TriageAgent",
                "safety_sensitive_single_domain",
                matched_signals=_matching_signals(text, "TriageAgent"),
                intent="safety_check",
            )

        if any(signal in text for signal in _MEDICATION_SAFETY_SIGNALS):
            return self._simple_route(
                request,
                "MedicationAgent",
                "safety_sensitive_single_domain",
                matched_signals=_matching_signals(text, "MedicationAgent"),
                intent="safety_check",
            )

        if len(matched) >= 2:
            roles = tuple(matched)
            return ComplexityRoute(
                task_id=request.task_id,
                user_id=request.user_id,
                member_id=request.member_id,
                route_mode="complex_cross_domain",
                intent=request.intent or _ROLE_INTENTS[roles[0]],
                target_roles=roles,
                reason_code="multiple_domain_signals",
                matched_signals=_matching_signals_for_roles(text, roles),
                required_capabilities=_capabilities_for_roles(roles),
                requires_planner=True,
            )

        role = matched[0] if matched else _role_from_intent(request.intent)
        reason = "single_domain_signal" if matched else "ambiguous_input"
        return self._simple_route(
            request,
            role,
            reason,
            matched_signals=_matching_signals(text, role),
            intent=request.intent or _ROLE_INTENTS[role],
        )

    @staticmethod
    def _simple_route(
        request: ComplexityRoutingRequest,
        role: DomainAgentRole,
        reason_code: str,
        *,
        matched_signals: tuple[str, ...],
        intent: Intent,
    ) -> ComplexityRoute:
        return ComplexityRoute(
            task_id=request.task_id,
            user_id=request.user_id,
            member_id=request.member_id,
            route_mode="simple_single_domain",
            intent=intent,
            target_role=role,
            target_roles=(role,),
            reason_code=reason_code,
            matched_signals=matched_signals,
            required_capabilities=_CAPABILITIES[role],
            requires_planner=False,
        )


def _matched_roles(text: str) -> list[DomainAgentRole]:
    return [role for role in _DOMAIN_SIGNALS if _matching_signals(text, role)]


def _matching_signals(text: str, role: DomainAgentRole) -> tuple[str, ...]:
    return tuple(signal for signal in _DOMAIN_SIGNALS[role] if signal.casefold() in text)


def _matching_signals_for_roles(
    text: str,
    roles: Iterable[DomainAgentRole],
) -> tuple[str, ...]:
    return tuple(
        signal
        for role in roles
        for signal in _matching_signals(text, role)
    )


def _capabilities_for_roles(
    roles: Iterable[DomainAgentRole],
) -> tuple[str, ...]:
    return tuple(
        capability
        for role in roles
        for capability in _CAPABILITIES[role]
    )


def _role_from_intent(intent: Intent | None) -> DomainAgentRole:
    return _INTENT_ROLES.get(intent, "TriageAgent")


__all__ = ["DeterministicComplexityRouter"]

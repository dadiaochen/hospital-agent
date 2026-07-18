from collections.abc import Sequence
from typing import Any

from app.agent.workflow_schemas import WorkflowPlan, WorkflowRunRequest
from app.safety.policies import needs_medical_safety_interception
from app.tools.tool_registry import ToolRegistry


DEFAULT_FORBIDDEN_PHRASES = [
    "已经替你续方",
    "已自动开方",
    "可以直接停药",
    "建议加倍服用",
    "已经下单",
    "无需确认",
]


class DeterministicWorkflowPlanner:
    """Build a reproducible plan for local workflow tests."""

    def plan(self, request: WorkflowRunRequest) -> WorkflowPlan:
        text = request.user_input.casefold()
        if _is_high_risk(text):
            return self._safety_plan(text)
        if _contains_any(text, ("提醒", "reminder", "闹钟")):
            return WorkflowPlan(
                intent="reminder",
                input_category="reminder",
                action_type="draft",
                required_tools=("query_medicine_box", "create_confirmation_draft"),
                safety_flags=("reminder_confirmation_required",),
                human_confirmation_required=True,
                draft_action_type="reminder_create",
            )
        if _contains_any(text, ("自提", "配送", "药店", "库存", "有货", "下单", "购买")):
            return self._pharmacy_plan(text)
        return self._refill_plan(text)

    @staticmethod
    def _safety_plan(text: str) -> WorkflowPlan:
        flags: list[str] = []
        if _contains_any(text, ("加量", "减量", "多吃", "increase dose", "decrease dose")):
            flags.append("dosage_change_request")
        if _contains_any(text, ("停药", "stop medication")):
            flags.append("stop_medication_request")
        if _contains_any(text, ("换药", "换成", "替代", "switch medication")):
            flags.append("medication_switch_request")
        if _contains_any(text, ("胸痛", "喘不上气", "呼吸困难", "昏迷", "chest pain")):
            flags.extend(["severe_symptom", "urgent_human_escalation"])
        if "urgent_human_escalation" not in flags:
            flags.append("doctor_confirmation_required")
        return WorkflowPlan(
            intent="safety_check",
            input_category="safety",
            action_type="safety_review",
            required_tools=("search_safety_knowledge",),
            safety_flags=tuple(dict.fromkeys(flags)),
            human_confirmation_required=True,
        )

    @staticmethod
    def _pharmacy_plan(text: str) -> WorkflowPlan:
        no_source = _contains_any(text, ("没有查到", "没有来源", "肯定有货"))
        unavailable = _contains_any(text, ("不可用", "服务异常", "unavailable"))
        tools: list[str] = []
        if not no_source:
            tools.extend(["query_prescriptions", "query_medicine_box"])
        tools.append("check_pharmacy_inventory")
        create_draft = not (no_source or unavailable)
        if create_draft:
            tools.append("create_confirmation_draft")
        flags = (
            ["insufficient_source", "no_unsupported_claims"]
            if no_source
            else ["tool_unavailable", "fallback_required"]
            if unavailable
            else ["purchase_confirmation_required"]
        )
        return WorkflowPlan(
            intent="pharmacy",
            input_category=(
                "no_source"
                if no_source
                else "tool_failure"
                if unavailable
                else "pharmacy"
            ),
            action_type="draft" if create_draft else "query",
            required_tools=tuple(tools),
            safety_flags=tuple(flags),
            human_confirmation_required=create_draft,
            draft_action_type="pharmacy_option" if create_draft else None,
        )

    @staticmethod
    def _refill_plan(text: str) -> WorkflowPlan:
        consultation = _contains_any(text, ("复诊", "中药", "舌诊", "follow-up"))
        isolation = _contains_any(text, ("不要混入", "只看", "隔离"))
        tools = ["query_health_profile", "query_prescriptions"]
        if "没有新的舌诊" not in text:
            tools.append("query_medicine_box")
        if _contains_any(text, ("库存", "哪里", "附近")) or (
            "续方" in text and "快吃完" in text
        ):
            tools.append("check_pharmacy_inventory")
        if _contains_any(text, ("处方快到期", "安全规则", "sop")):
            tools.append("search_safety_knowledge")
        create_draft = not isolation
        if create_draft:
            tools.append("create_confirmation_draft")
        flags = ["doctor_confirmation_required"]
        if "没有新的舌诊" in text:
            flags.insert(0, "missing_optional_material")
        if isolation:
            flags = ["member_context_isolation_required"]
        return WorkflowPlan(
            intent="refill",
            input_category=(
                "isolation"
                if isolation
                else "consultation"
                if consultation
                else "refill"
            ),
            action_type="draft" if create_draft else "query",
            required_tools=tuple(tools),
            safety_flags=tuple(flags),
            human_confirmation_required=create_draft,
            draft_action_type=(
                "consultation_request" if consultation else "refill_request"
            )
            if create_draft
            else None,
        )


class WorkflowToolInputBuilder:
    """Project workflow request fields into each registered input schema."""

    def build(
        self,
        tool_name: str,
        *,
        request: WorkflowRunRequest,
        plan: WorkflowPlan,
        registry: ToolRegistry,
    ) -> dict[str, Any]:
        fields = registry.get_spec(tool_name).input_schema.model_fields
        values: dict[str, Any] = {
            "user_id": request.user_id,
            "member_id": request.member_id,
            "query": request.user_input,
            "medication_name": request.medication_name,
            "medicine_name": request.medication_name,
            "city": request.city,
            "action_type": plan.draft_action_type,
            "idempotency_key": f"{request.run_id}:{plan.draft_action_type or 'none'}",
            "summary": f"Local {plan.intent} draft for run {request.run_id}.",
            "payload": {
                "purpose": plan.intent,
                "source": "langgraph_workflow",
            },
        }
        return {
            name: values[name]
            for name in fields
            if name in values and values[name] is not None
        }


def _is_high_risk(text: str) -> bool:
    return needs_medical_safety_interception(text) or _contains_any(
        text,
        (
            "胸痛",
            "喘不上气",
            "呼吸困难",
            "昏迷",
            "increase dose",
            "stop medication",
            "switch medication",
            "chest pain",
        ),
    )


def _contains_any(text: str, patterns: Sequence[str]) -> bool:
    return any(pattern in text for pattern in patterns)


__all__ = [
    "DEFAULT_FORBIDDEN_PHRASES",
    "DeterministicWorkflowPlanner",
    "WorkflowToolInputBuilder",
]

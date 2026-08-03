from collections.abc import Sequence
from typing import Any

from app.agent.workflow_schemas import WorkflowPlan, WorkflowRunRequest
from app.safety.policies import needs_medical_safety_interception
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolResult


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
        tool_results: Sequence[ToolResult] = (),
    ) -> dict[str, Any]:
        fields = registry.get_spec(tool_name).input_schema.model_fields
        derived_medicine_name = (
            _medicine_name_from_tool_results(tool_results)
            if tool_name == "check_pharmacy_inventory"
            else None
        )
        values: dict[str, Any] = {
            "user_id": request.user_id,
            "member_id": request.member_id,
            "query": request.user_input,
            "medication_name": request.medication_name,
            "medicine_name": request.medication_name or derived_medicine_name,
            "city": request.city,
            "action_type": plan.draft_action_type,
            "idempotency_key": f"{request.run_id}:{plan.draft_action_type or 'none'}",
            "summary": f"Local {plan.intent} draft for run {request.run_id}.",
            "payload": self._draft_payload(request, plan, tool_results),
        }
        return {
            name: values[name]
            for name in fields
            if name in values and values[name] is not None
        }

    @staticmethod
    def _draft_payload(
        request: WorkflowRunRequest,
        plan: WorkflowPlan,
        tool_results: Sequence[ToolResult],
    ) -> dict[str, Any]:
        prescriptions = _successful_output(tool_results, "query_prescriptions")
        medicine_box = _successful_output(tool_results, "query_medicine_box")
        inventory = _successful_output(tool_results, "check_pharmacy_inventory")
        prescription = _first_mapping(prescriptions.get("prescriptions"))
        medicine = _first_mapping(
            medicine_box.get("items") or medicine_box.get("medicines")
        )
        inventory_item = _first_mapping(
            inventory.get("inventory_items") or inventory.get("candidates")
        )
        prescription_medicine = _first_mapping(prescription.get("medicine_items"))
        medicine_name = (
            request.medication_name
            or _text(medicine.get("medicine_name"))
            or _text(prescription_medicine.get("medicine_name"))
            or _text(inventory_item.get("medicine_name"))
            or "medication from verified records"
        )
        source_ids = [
            source_id
            for result in tool_results
            if result.success
            for source_id in [_text(result.output.get("source_id"))]
            if source_id is not None
        ]
        common = {
            "source_ids": list(dict.fromkeys(source_ids)),
            "purpose": plan.intent,
        }

        if plan.draft_action_type == "consultation_request":
            return {
                "prescription_id": _text(prescription.get("prescription_id")),
                "draft_content": "Organize existing follow-up materials for review.",
                "material_summary": common,
            }
        if plan.draft_action_type == "pharmacy_option":
            delivery_options = inventory_item.get("delivery_options")
            delivery_option = (
                delivery_options[0]
                if isinstance(delivery_options, list) and delivery_options
                else None
            )
            return {
                "medicine_name": medicine_name,
                "pharmacy_id": _text(inventory_item.get("pharmacy_id")),
                "delivery_option": _text(delivery_option),
                "plan_detail": common,
            }
        if plan.draft_action_type == "reminder_create":
            schedule_times = (
                ["08:00", "20:00"]
                if _twice_daily_requested(request.user_input, medicine)
                else ["08:00"]
            )
            return {
                "medicine_name": medicine_name,
                "medicine_box_item_id": _text(
                    medicine.get("medicine_box_item_id")
                ),
                "schedule": {**common, "times": schedule_times},
                "reminder_type": "medication",
            }
        remaining_days = medicine.get("estimated_remaining_days")
        if remaining_days is None:
            remaining_days = medicine.get("remaining_days")
        return {
            "medicine_name": medicine_name,
            "prescription_id": _text(prescription.get("prescription_id")),
            "remaining_days": _non_negative_int(remaining_days),
            "plan_detail": common,
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


def _successful_output(
    results: Sequence[ToolResult],
    tool_name: str,
) -> dict[str, Any]:
    return next(
        (
            result.output
            for result in results
            if result.tool_name == tool_name and result.success
        ),
        {},
    )


def _medicine_name_from_tool_results(results: Sequence[ToolResult]) -> str | None:
    medicine_box = _successful_output(results, "query_medicine_box")
    medicine = _first_mapping(
        medicine_box.get("items") or medicine_box.get("medicines")
    )
    medicine_name = _text(medicine.get("medicine_name"))
    if medicine_name:
        return medicine_name

    prescriptions = _successful_output(results, "query_prescriptions")
    prescription = _first_mapping(prescriptions.get("prescriptions"))
    prescription_medicine = _first_mapping(prescription.get("medicine_items"))
    return _text(prescription_medicine.get("medicine_name"))


def _first_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _twice_daily_requested(user_input: str, medicine: dict[str, Any]) -> bool:
    rendered = f"{user_input} {medicine.get('frequency', '')}".casefold()
    return any(
        marker in rendered
        for marker in ("早晚", "两次", "twice daily", "morning and evening")
    )


__all__ = [
    "DEFAULT_FORBIDDEN_PHRASES",
    "DeterministicWorkflowPlanner",
    "WorkflowToolInputBuilder",
]

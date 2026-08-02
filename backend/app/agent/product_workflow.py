from __future__ import annotations

import json
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agent.model_gateway import (
    DeterministicModelProvider,
    ModelGateway,
    create_model_gateway,
)
from app.agent.model_gateway_schemas import ModelCallRequest, ModelCallTrace, ModelMessage
from app.agent.final_claim_schemas import build_workflow_claims
from app.agent.safety_confirmation import (
    ConfirmationScope,
    ConfirmationState,
    ConfirmationStateMachine,
    ConfirmationTransitionRequest,
    ThreeLayerSafetyGuard,
    build_confirmation_scope,
)
from app.agent.workflow_schemas import WorkflowFinalAnswerDraft
from app.providers import build_mock_provider_registry
from app.providers.registry import ProviderRegistry
from app.rag.retriever import create_knowledge_retriever
from app.schemas.business import BusinessDomain, ProviderMode
from app.tools.business_tools import register_business_tools
from app.tools.db_tools import create_db_tool_registry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult
from app.core.config import Settings


ConfirmationAction = Literal[
    "refill_request",
    "consultation_request",
    "pharmacy_option",
    "reminder_create",
    "health_record",
]


def _deterministic_product_answer(request: ModelCallRequest) -> dict[str, Any]:
    """Create a safe offline answer from the frozen workflow summary."""

    payload: dict[str, Any] = {}
    if request.messages:
        try:
            decoded = json.loads(request.messages[-1].content)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = {}

    waiting = bool(payload.get("waiting_for_user_confirmation", False))
    confirmed = bool(payload.get("human_confirmation_present", False))
    return {
        "content": str(
            payload.get("template")
            or "已完成信息整理；当前没有执行任何外部医疗或交易动作。"
        ),
        "contains_factual_claims": bool(payload.get("contains_factual_claims", False)),
        "claims": payload.get("claims", []),
        "waiting_for_user_confirmation": waiting,
        "human_confirmation_present": confirmed,
        "action_status": (
            "awaiting_confirmation"
            if waiting
            else "draft"
            if confirmed
            else "none"
        ),
    }


class ProductWorkflowState(TypedDict, total=False):
    run_id: str
    task_id: str
    user_id: str
    member_id: str
    business_domain: BusinessDomain
    intent: str
    user_goal: str
    user_input: str
    input_payload: dict[str, Any]
    provider_mode: ProviderMode
    human_confirmation_granted: bool
    idempotency_key: str
    status: str
    final_answer: str
    final_claims: list[dict[str, Any]]
    need_human_confirmation: bool
    safety_flags: list[str]
    source_refs: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    provider_calls: list[dict[str, Any]]
    model_call_trace: dict[str, Any]
    degraded: bool
    errors: list[str]
    confirmation_request: dict[str, Any]
    confirmation_result: dict[str, Any]
    confirmation_state: ConfirmationState
    confirmation_scope: dict[str, Any]
    confirmation_draft: dict[str, Any]
    safety_decisions: list[dict[str, Any]]
    final_output_safety: dict[str, Any]
    visited_nodes: list[str]
    orchestration_run: dict[str, Any]
    unified_graph_version: str
    unified_visited_nodes: list[str]


class FamilyHealthProductWorkflow:
    """Bounded workflow for the three 4B business branches.

    The graph prepares evidence and local confirmation drafts. It never submits
    a consultation, purchase, reminder, or medical record to an external system.
    """

    def __init__(
        self,
        db: Session,
        *,
        model_gateway: ModelGateway | None = None,
        model_configuration: Settings | None = None,
        provider_registry: ProviderRegistry | None = None,
        knowledge_retriever: object | None = None,
    ):
        self.db = db
        deterministic_provider = DeterministicModelProvider(
            _deterministic_product_answer,
            model_name="deterministic-product-answer-v1",
        )
        self.model_gateway = model_gateway or create_model_gateway(
            deterministic_provider,
            configuration=model_configuration,
        )
        self.safety_guard = ThreeLayerSafetyGuard()
        self.confirmation_machine = ConfirmationStateMachine()
        self.retriever = knowledge_retriever or create_knowledge_retriever(db)
        self.registry = create_db_tool_registry(db, include_confirmation_tools=True)
        register_business_tools(
            self.registry,
            self.db,
            provider_registry=provider_registry or build_mock_provider_registry(),
            knowledge_retriever=self.retriever,
        )
        self.graph = self._build_graph()

    def close(self) -> None:
        """Release an HTTP client when a live provider was configured."""

        self.model_gateway.close()

    def _build_graph(self):
        graph = StateGraph(ProductWorkflowState)
        graph.add_node("safety_entry", self._safety_entry)
        graph.add_node("preconsultation", self._preconsultation)
        graph.add_node("chronic_care", self._chronic_care)
        graph.add_node("health_record", self._health_record)
        graph.add_node("safety_review", self._safety_review)
        graph.add_node("confirm", self._confirm)
        graph.add_node("finalize", self._finalize)

        graph.set_entry_point("safety_entry")
        graph.add_conditional_edges(
            "safety_entry",
            self._route_after_entry,
            {
                "blocked": "finalize",
                "preconsultation": "preconsultation",
                "chronic_care": "chronic_care",
                "health_record": "health_record",
            },
        )
        for node in ("preconsultation", "chronic_care", "health_record"):
            graph.add_edge(node, "safety_review")
        graph.add_conditional_edges(
            "safety_review",
            self._route_after_review,
            {"blocked": "finalize", "confirm": "confirm", "finalize": "finalize"},
        )
        graph.add_edge("confirm", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    @staticmethod
    def _data(result: ToolResult) -> dict[str, Any]:
        return cast(dict[str, Any], result.output or {})

    @staticmethod
    def _visit(state: ProductWorkflowState, node_name: str) -> None:
        state.setdefault("visited_nodes", []).append(node_name)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _context(self, state: ProductWorkflowState, agent_role: str, tool_name: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            run_id=state["run_id"],
            task_id=state["task_id"],
            user_id=state["user_id"],
            member_id=state["member_id"],
            agent_role=agent_role,
            allowed_tools=[tool_name],
            safety_flags=list(state.get("safety_flags", [])),
            human_confirmation_granted=state.get("human_confirmation_granted", False),
            provider_mode=state.get("provider_mode", "mock"),
        )

    def _call(
        self,
        state: ProductWorkflowState,
        *,
        tool_name: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> ToolResult:
        result = self.registry.call(
            tool_name,
            payload,
            self._context(state, agent_role, tool_name),
        )
        state.setdefault("tool_calls", []).append(result.model_dump(mode="json"))
        output = self._data(result)
        state.setdefault("source_refs", []).extend(
            ref.model_dump(mode="json") if hasattr(ref, "model_dump") else dict(ref)
            for ref in result.evidence_refs
        )
        provider_call = output.get("provider_call")
        if provider_call:
            state.setdefault("provider_calls", []).append(provider_call)
        if output.get("degraded"):
            state["degraded"] = True
        if not result.success or output.get("success") is False:
            state.setdefault("errors", []).append(
                result.error_message or result.error_type or f"tool_failed:{tool_name}"
            )
        return result

    def _abort_on_failure(self, state: ProductWorkflowState, result: ToolResult) -> bool:
        output = self._data(result)
        if result.success and output.get("success", True) is not False:
            return False
        state["status"] = "failed"
        state["need_human_confirmation"] = False
        state["final_answer"] = "当前信息服务暂不可用，暂未生成可执行草稿，请稍后重试或转人工处理。"
        return True

    @staticmethod
    def _record_safety_decision(
        state: ProductWorkflowState,
        decision: object,
    ) -> None:
        """Keep every gate decision in the frozen run state for audit."""

        dumped = (
            decision.model_dump(mode="json")
            if hasattr(decision, "model_dump")
            else dict(decision)
        )
        state.setdefault("safety_decisions", []).append(dumped)
        flags = [str(flag) for flag in dumped.get("flags", [])]
        state["safety_flags"] = list(
            dict.fromkeys([*state.get("safety_flags", []), *flags])
        )

    def _scope_from_state(
        self,
        state: ProductWorkflowState,
    ) -> ConfirmationScope | None:
        raw_scope = state.get("confirmation_scope")
        if not isinstance(raw_scope, dict) or not raw_scope:
            return None
        try:
            return ConfirmationScope.model_validate(raw_scope)
        except ValueError:
            return None

    def _provider_payload(
        self,
        state: ProductWorkflowState,
        *,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "operation": operation,
            "business_domain": state["business_domain"],
            "user_id": state["user_id"],
            "member_id": state["member_id"],
            "payload": payload,
        }

    def _provider_call(
        self,
        state: ProductWorkflowState,
        *,
        tool_name: str,
        agent_role: str,
        provider_name: str,
        operation: str,
        payload: dict[str, Any],
    ) -> ToolResult:
        # provider_name remains an explicit argument so the graph documents the
        # integration boundary even though the registry selects the provider.
        _ = provider_name
        return self._call(
            state,
            tool_name=tool_name,
            agent_role=agent_role,
            payload=self._provider_payload(state, operation=operation, payload=payload),
        )

    def _set_confirmation(
        self,
        state: ProductWorkflowState,
        *,
        action_type: ConfirmationAction,
        summary: str,
        payload: dict[str, Any],
        tool_name: str = "create_confirmation_draft",
        agent_role: str = "RefillAgent",
    ) -> None:
        scope = build_confirmation_scope(
            task_id=state["task_id"],
            user_id=state["user_id"],
            member_id=state["member_id"],
            action_type=action_type,
            idempotency_key=state["idempotency_key"],
            request_payload=payload,
        )
        action_decision = self.safety_guard.action(
            message=f"{state.get('user_input', '')} {summary}",
            user_id=state["user_id"],
            member_id=state["member_id"],
            expected_user_id=scope.user_id,
            expected_member_id=scope.member_id,
            confirmation_state="NONE",
            human_confirmation_present=False,
        )
        self._record_safety_decision(state, action_decision)
        action_flag = {
            "refill_request": "doctor_confirmation_required",
            "pharmacy_option": "purchase_confirmation_required",
            "reminder_create": "reminder_confirmation_required",
            "health_record": "doctor_confirmation_required",
            "consultation_request": "doctor_confirmation_required",
        }.get(action_type, "human_confirmation_required")
        state["safety_flags"] = list(
            dict.fromkeys(
                [
                    flag
                    for flag in state.get("safety_flags", [])
                    if flag != "human_confirmation_required"
                ]
                + [action_flag]
            )
        )
        draft_transition = self.confirmation_machine.transition(
            ConfirmationTransitionRequest(
                current_state="NONE",
                action="create_draft",
                scope=scope,
                actor_user_id=state["user_id"],
                actor_member_id=state["member_id"],
                safety_decision=action_decision,
            )
        )
        if not draft_transition.allowed:
            state["confirmation_state"] = "BLOCKED"
            state["status"] = "blocked"
            state["need_human_confirmation"] = False
            state["final_answer"] = (
                action_decision.message
                or "当前动作未通过安全检查，暂不生成草稿。"
            )
            state.setdefault("errors", []).append(
                draft_transition.failure_code or "confirmation_draft_blocked"
            )
            return

        state["confirmation_scope"] = scope.model_dump(mode="json")
        state["confirmation_state"] = draft_transition.state
        state["confirmation_draft"] = {
            "draft_id": scope.draft_id,
            "task_id": scope.task_id,
            "user_id": scope.user_id,
            "member_id": scope.member_id,
            "action_type": scope.action_type,
            "status": "DRAFT",
            "draft_version": scope.draft_version,
            "need_human_confirmation": True,
            "local_only": True,
            "external_action_status": "not_submitted",
        }
        state["confirmation_request"] = {
            "tool_name": tool_name,
            "agent_role": agent_role,
            "action_type": action_type,
            "summary": summary,
            "payload": payload,
            "draft_id": scope.draft_id,
            "draft_version": scope.draft_version,
            "request_fingerprint": scope.request_fingerprint,
        }
        state["need_human_confirmation"] = True
        state["status"] = "needs_confirmation"

    def _safety_entry(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "safety_entry")
        decision = self.safety_guard.request(
            message=state.get("user_input", ""),
            member_id=state["member_id"],
        )
        self._record_safety_decision(state, decision)
        state["need_human_confirmation"] = decision.requires_human_confirmation
        if decision.blocked:
            state["confirmation_state"] = "BLOCKED"
            state["status"] = "blocked"
            state["final_answer"] = decision.message
        else:
            state["confirmation_state"] = "NONE"
            state["status"] = "running"
        return state

    def _route_after_entry(self, state: ProductWorkflowState) -> str:
        if state.get("status") == "blocked":
            return "blocked"
        domain = state.get("business_domain")
        if domain in {"preconsultation", "chronic_care", "health_record"}:
            return cast(str, domain)
        state["status"] = "failed"
        state["final_answer"] = "暂时无法识别业务类型，请说明是复诊材料、续方购药、用药提醒还是报告解读。"
        return "blocked"

    def _preconsultation(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "preconsultation")
        payload = dict(state.get("input_payload", {}))
        profile = self._call(
            state,
            tool_name="query_health_profile",
            agent_role="ProfileAgent",
            payload={"user_id": state["user_id"], "member_id": state["member_id"]},
        )
        if self._abort_on_failure(state, profile):
            return state

        departments = self._provider_call(
            state,
            tool_name="hospital_list_departments",
            agent_role="Planner",
            provider_name="hospital",
            operation="list_departments",
            payload={"keyword": payload.get("department_keyword", "")},
        )
        if self._abort_on_failure(state, departments):
            return state

        slots = self._provider_call(
            state,
            tool_name="hospital_list_slots",
            agent_role="Planner",
            provider_name="hospital",
            operation="list_slots",
            payload={
                "department_candidates": self._data(departments).get("data", {}).get("candidates", []),
                "preferred_date": payload.get("preferred_date"),
            },
        )
        if self._abort_on_failure(state, slots):
            return state

        draft = self._provider_call(
            state,
            tool_name="consultation_prepare_draft",
            agent_role="RefillAgent",
            provider_name="online_consultation",
            operation="prepare_draft",
            payload={
                "member_id": state["member_id"],
                "chief_complaint": payload.get(
                    "chief_complaint", payload.get("symptoms", "")
                ),
                "symptoms": payload.get("symptoms", ""),
                "medication_changes": payload.get("medication_changes", ""),
                "materials": payload.get("materials", []),
            },
        )
        if self._abort_on_failure(state, draft):
            return state

        knowledge = self._call(
            state,
            tool_name="search_business_knowledge",
            agent_role="RefillAgent",
            payload={
                "query": payload.get("knowledge_query", "复诊材料整理和医生确认要求"),
                "purpose": "preconsultation",
                "mode": "hybrid",
                "limit": 5,
            },
        )
        if self._abort_on_failure(state, knowledge):
            return state

        self._set_confirmation(
            state,
            action_type="consultation_request",
            summary="已整理复诊材料并生成待确认的复诊申请草稿。",
            payload={
                "draft_content": self._json(self._data(draft).get("data", {})),
                "material_summary": self._data(knowledge),
                "department_candidates": self._data(departments).get("data", {}).get("candidates", []),
                "slot_candidates": self._data(slots).get("data", {}).get("slots", []),
                "prescription_id": payload.get("prescription_id"),
            },
        )
        state["final_answer"] = "已整理复诊材料、科室和可选时间，生成复诊申请草稿；提交前需要你的确认。"
        return state

    def _chronic_care(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "chronic_care")
        payload = dict(state.get("input_payload", {}))
        action_type = cast(str, payload.get("action_type", "refill_request"))
        medicine_name = str(payload.get("medicine_name", "")).strip()
        if not medicine_name:
            state["status"] = "needs_clarification"
            state["final_answer"] = "请先说明需要处理的药品名称，我再整理续方、购药或提醒草稿。"
            return state
        if action_type == "reminder_create" and not payload.get("schedule"):
            state["status"] = "needs_clarification"
            state["final_answer"] = "请补充用药时间和频次，我再生成提醒草稿。"
            return state

        profile = self._call(
            state,
            tool_name="query_health_profile",
            agent_role="ProfileAgent",
            payload={"user_id": state["user_id"], "member_id": state["member_id"]},
        )
        if self._abort_on_failure(state, profile):
            return state
        box = self._call(
            state,
            tool_name="query_medicine_box",
            agent_role="ReminderAgent" if action_type == "reminder_create" else "RefillAgent",
            payload={"member_id": state["member_id"]},
        )
        if self._abort_on_failure(state, box):
            return state

        prescriptions: ToolResult | None = None
        if action_type in {"refill_request", "pharmacy_option"}:
            prescriptions = self._call(
                state,
                tool_name="query_prescriptions",
                agent_role="RefillAgent",
                payload={"member_id": state["member_id"]},
            )
            if self._abort_on_failure(state, prescriptions):
                return state
        elif action_type == "reminder_create":
            # A reminder must be checked against the current prescription
            # snapshot too; the medicine-box row alone is not enough for a
            # clinically safe reminder draft.
            prescriptions = self._call(
                state,
                tool_name="query_prescriptions",
                agent_role="ReminderAgent",
                payload={"member_id": state["member_id"]},
            )
            if self._abort_on_failure(state, prescriptions):
                return state

        agent_role = {
            "refill_request": "RefillAgent",
            "pharmacy_option": "PharmacyAgent",
            "reminder_create": "ReminderAgent",
        }.get(action_type, "RefillAgent")
        knowledge = self._call(
            state,
            tool_name="search_business_knowledge",
            agent_role=agent_role,
            payload={
                "query": payload.get("knowledge_query", f"{medicine_name} 用药流程和安全提醒"),
                "purpose": action_type,
                "mode": "hybrid",
                "limit": 5,
            },
        )
        if self._abort_on_failure(state, knowledge):
            return state

        pharmacy_result: ToolResult | None = None
        if action_type == "pharmacy_option":
            pharmacy_result = self._provider_call(
                state,
                tool_name="pharmacy_search_inventory",
                agent_role="PharmacyAgent",
                provider_name="pharmacy",
                operation="search_inventory",
                payload={"medicine_name": medicine_name, "city": payload.get("city", "")},
            )
            if self._abort_on_failure(state, pharmacy_result):
                return state

        provider_result: ToolResult | None = None
        if action_type == "refill_request":
            provider_result = self._provider_call(
                state,
                tool_name="consultation_prepare_draft",
                agent_role="RefillAgent",
                provider_name="online_consultation",
                operation="prepare_draft",
                payload={
                    "member_id": state["member_id"],
                    "materials": ["prescription", "medicine_box"],
                    "medicine_name": medicine_name,
                },
            )
        elif action_type == "reminder_create":
            provider_result = self._provider_call(
                state,
                tool_name="notification_prepare_reminder",
                agent_role="ReminderAgent",
                provider_name="notification",
                operation="prepare_reminder",
                payload={
                    "member_id": state["member_id"],
                    "medicine_name": medicine_name,
                    "schedule": payload["schedule"],
                },
            )
        if provider_result is not None and self._abort_on_failure(state, provider_result):
            return state

        if action_type not in {"refill_request", "pharmacy_option", "reminder_create"}:
            state["status"] = "needs_clarification"
            state["final_answer"] = "当前只支持续方申请、购药方案和用药提醒草稿。"
            return state

        confirmation_payload: dict[str, Any] = {
            "medicine_name": medicine_name,
            "plan_detail": {
                "profile": self._data(profile),
                "medicine_box": self._data(box),
                "prescriptions": self._data(prescriptions) if prescriptions else {},
                "knowledge": self._data(knowledge),
            },
        }
        if action_type == "pharmacy_option":
            confirmation_payload["delivery"] = self._data(pharmacy_result) if pharmacy_result else {}
        if provider_result is not None:
            confirmation_payload["provider"] = self._data(provider_result)
        if action_type == "reminder_create":
            confirmation_payload["medicine_box_item_id"] = payload.get("medicine_box_item_id")
            confirmation_payload["schedule"] = payload["schedule"]
            confirmation_payload["message"] = payload.get("message", f"请按已确认方案服用{medicine_name}")

        self._set_confirmation(
            state,
            action_type=cast(ConfirmationAction, action_type),
            agent_role=agent_role,
            summary={
                "refill_request": "已整理续方材料，生成待确认的续方申请草稿。",
                "pharmacy_option": "已查询购药候选方案，生成待确认的购药草稿。",
                "reminder_create": "已整理用药信息，生成待确认的提醒草稿。",
            }[action_type],
            payload=confirmation_payload,
        )
        state["final_answer"] = {
            "refill_request": "已整理续方材料，生成续方申请草稿；提交前需要你的确认。",
            "pharmacy_option": "已查询购药候选方案，生成购药草稿；下单前需要你的确认。",
            "reminder_create": "已生成用药提醒草稿；创建前需要你的确认。",
        }[action_type]
        return state

    def _health_record(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "health_record")
        payload = dict(state.get("input_payload", {}))
        text = str(payload.get("text", payload.get("source_text", "")))
        if not text and not payload.get("image_uri"):
            state["status"] = "needs_clarification"
            state["final_answer"] = "请提供检查报告、体检报告、中医诊疗记录或舌诊结果的文字或图片。"
            return state

        parsed = self._provider_call(
            state,
            tool_name="parse_medical_document",
            agent_role="ProfileAgent",
            provider_name="medical_document_parser",
            operation="parse",
            payload={"text": text, "document_type": payload.get("document_type", "medical_report")},
        )
        if self._abort_on_failure(state, parsed):
            return state

        image_quality: ToolResult | None = None
        if payload.get("image_uri"):
            image_quality = self._provider_call(
                state,
                tool_name="inspect_medical_image",
                agent_role="ProfileAgent",
                provider_name="medical_vision",
                operation="inspect_quality",
                payload={"image_uri": payload["image_uri"]},
            )
            if self._abort_on_failure(state, image_quality):
                return state

        knowledge = self._call(
            state,
            tool_name="search_business_knowledge",
            agent_role="ProfileAgent",
            payload={
                "query": payload.get("knowledge_query", "检查报告和中医舌诊结果的说明边界"),
                "purpose": "health_record",
                "mode": "hybrid",
                "limit": 5,
            },
        )
        if self._abort_on_failure(state, knowledge):
            return state

        event_type = str(payload.get("event_type", "medical_report_explanation"))
        record_payload = {
            "document_type": payload.get("document_type", "medical_report"),
            "parsed_content": self._data(parsed),
            "image_quality": self._data(image_quality) if image_quality else None,
            "knowledge_evidence": self._data(knowledge),
            "explanation_boundary": "仅做信息整理和来源解释，不替代医生诊断或调整处方。",
        }
        self._set_confirmation(
            state,
            action_type="health_record",
            agent_role="ProfileAgent",
            tool_name="create_health_record_draft",
            summary="已整理报告内容，生成待确认的健康记录草稿。",
            payload={
                "user_id": state["user_id"],
                "member_id": state["member_id"],
                "idempotency_key": state["idempotency_key"],
                "summary": "报告解读结果草稿",
                "event_type": event_type,
                "payload": record_payload,
                "source_document_id": payload.get("source_document_id"),
                "source_refs": list(state.get("source_refs", [])),
            },
        )
        state["final_answer"] = "已完成报告内容整理和来源检索，生成健康记录草稿；保存前需要你的确认。"
        return state

    def _safety_review(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "safety_review")
        if state.get("status") in {"failed", "needs_clarification", "blocked"}:
            return state
        request = state.get("confirmation_request")
        decision = self.safety_guard.action(
            message=" ".join(
                [
                    state.get("user_input", ""),
                    request.get("summary", "") if isinstance(request, dict) else "",
                ]
            ),
            user_id=state["user_id"],
            member_id=state["member_id"],
            expected_user_id=state["user_id"],
            expected_member_id=state["member_id"],
            confirmation_state=state.get("confirmation_state", "NONE"),
            human_confirmation_present=state.get(
                "human_confirmation_granted", False
            ),
        )
        self._record_safety_decision(state, decision)
        request = state.get("confirmation_request")
        action_type = (
            str(request.get("action_type"))
            if isinstance(request, dict) and request.get("action_type")
            else None
        )
        if action_type is not None:
            action_flag = {
                "refill_request": "doctor_confirmation_required",
                "pharmacy_option": "purchase_confirmation_required",
                "reminder_create": "reminder_confirmation_required",
                "health_record": "doctor_confirmation_required",
                "consultation_request": "doctor_confirmation_required",
            }.get(action_type)
            if action_flag is not None:
                state["safety_flags"] = list(
                    dict.fromkeys(
                        [
                            flag
                            for flag in state.get("safety_flags", [])
                            if flag != "human_confirmation_required"
                        ]
                        + [action_flag]
                    )
                )
        if decision.blocked:
            state["confirmation_state"] = "BLOCKED"
            state["status"] = "blocked"
            state["need_human_confirmation"] = decision.requires_human_confirmation
            state["final_answer"] = decision.message
            return state
        if request:
            if not state.get("human_confirmation_granted"):
                state["confirmation_state"] = "DRAFT"
                state["need_human_confirmation"] = True
                state["status"] = "needs_confirmation"
                return state

            scope = self._scope_from_state(state)
            if scope is None:
                state["confirmation_state"] = "BLOCKED"
                state["status"] = "blocked"
                state["need_human_confirmation"] = False
                state["final_answer"] = "待确认草稿作用域无效，暂不执行任何动作。"
                state.setdefault("errors", []).append("confirmation_scope_invalid")
                return state
            transition = self.confirmation_machine.transition(
                ConfirmationTransitionRequest(
                    current_state=state.get("confirmation_state", "DRAFT"),
                    action="confirm",
                    scope=scope,
                    current_scope=scope,
                    actor_user_id=state["user_id"],
                    actor_member_id=state["member_id"],
                    human_confirmation_present=True,
                    safety_decision=decision,
                )
            )
            if not transition.allowed:
                state["confirmation_state"] = transition.state
                state["status"] = "blocked"
                state["need_human_confirmation"] = False
                state["final_answer"] = (
                    transition.failure_reason
                    or "待确认草稿未通过状态检查，暂不执行任何动作。"
                )
                state.setdefault("errors", []).append(
                    transition.failure_code or "confirmation_transition_blocked"
                )
                return state
            state["confirmation_state"] = transition.state
            state["need_human_confirmation"] = True
            state["status"] = "needs_confirmation"
        else:
            state["confirmation_state"] = "NONE"
            state["status"] = "completed"
        return state

    def _route_after_review(self, state: ProductWorkflowState) -> str:
        if state.get("status") == "blocked":
            return "blocked"
        if (
            state.get("confirmation_request")
            and state.get("human_confirmation_granted")
            and state.get("confirmation_state") == "CONFIRMED"
        ):
            return "confirm"
        return "finalize"

    def _confirm(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "confirm")
        request = state.get("confirmation_request")
        if not request:
            state["status"] = "failed"
            state["final_answer"] = "没有找到待确认草稿，暂未执行任何动作。"
            return state
        if not state.get("human_confirmation_granted"):
            state["status"] = "needs_confirmation"
            state["need_human_confirmation"] = True
            return state
        scope = self._scope_from_state(state)
        if scope is None or state.get("confirmation_state") != "CONFIRMED":
            state["confirmation_state"] = "BLOCKED"
            state["status"] = "blocked"
            state["need_human_confirmation"] = False
            state["final_answer"] = "确认草稿的版本或状态无效，暂不执行任何动作。"
            state.setdefault("errors", []).append("confirmation_state_invalid")
            return state

        action_decision = self.safety_guard.action(
            message=" ".join(
                [state.get("user_input", ""), str(request.get("summary", ""))]
            ),
            user_id=state["user_id"],
            member_id=state["member_id"],
            expected_user_id=scope.user_id,
            expected_member_id=scope.member_id,
            confirmation_state="CONFIRMED",
            human_confirmation_present=True,
        )
        self._record_safety_decision(state, action_decision)
        execution_transition = self.confirmation_machine.transition(
            ConfirmationTransitionRequest(
                current_state="CONFIRMED",
                action="execute",
                scope=scope,
                current_scope=scope,
                actor_user_id=state["user_id"],
                actor_member_id=state["member_id"],
                human_confirmation_present=True,
                safety_decision=action_decision,
            )
        )
        if not execution_transition.allowed:
            state["confirmation_state"] = execution_transition.state
            state["status"] = "blocked"
            state["need_human_confirmation"] = False
            state["final_answer"] = (
                execution_transition.failure_reason
                or "执行动作未通过安全检查，暂不继续。"
            )
            state.setdefault("errors", []).append(
                execution_transition.failure_code or "confirmation_execution_blocked"
            )
            return state

        request_payload = dict(request["payload"])
        if request["tool_name"] == "create_confirmation_draft":
            request_payload = {
                "user_id": state["user_id"],
                "member_id": state["member_id"],
                "idempotency_key": state["idempotency_key"],
                "action_type": request["action_type"],
                "summary": request["summary"],
                "payload": request_payload,
            }
        result = self._call(
            state,
            tool_name=request["tool_name"],
            agent_role=request["agent_role"],
            payload=request_payload,
        )
        if self._abort_on_failure(state, result):
            state["confirmation_state"] = "FAILED"
            return state
        state["confirmation_result"] = self._data(result)
        state["confirmation_state"] = execution_transition.state
        state["status"] = "completed"
        state["need_human_confirmation"] = False
        return state

    def _generate_final_answer(self, state: ProductWorkflowState) -> None:
        """Generate only the user-facing answer after execution is bounded.

        Routing, safety, tool permissions, and confirmation decisions are
        already fixed in state. The gateway receives a compact summary rather
        than raw conversation or complete tool output.
        """

        waiting = state.get("status") == "needs_confirmation"
        confirmed = bool(
            state.get("human_confirmation_granted")
            or state.get("confirmation_result")
        )
        claim_candidates = build_workflow_claims(
            run_id=state["run_id"],
            member_id=state["member_id"],
            status=str(state.get("status") or "unknown"),
            confirmation_state=str(state.get("confirmation_state") or "NONE"),
            source_ids=(
                str(source.get("source_id"))
                for source in state.get("source_refs", [])
                if isinstance(source, dict) and source.get("source_id")
            ),
        )
        payload = {
            "business_domain": state.get("business_domain"),
            "status": state.get("status"),
            "template": state.get("final_answer", ""),
            "waiting_for_user_confirmation": waiting,
            "human_confirmation_present": confirmed,
            "contains_factual_claims": bool(state.get("source_refs")),
            "source_count": len(state.get("source_refs", [])),
            "safety_flags": list(state.get("safety_flags", [])),
            "claims": [claim.model_dump(mode="json") for claim in claim_candidates],
        }
        result = self.model_gateway.invoke(
            ModelCallRequest(
                run_id=state["run_id"],
                task_id=state["task_id"],
                member_id=state["member_id"],
                purpose=f"business_{state['business_domain']}_final_answer",
                messages=(
                    ModelMessage(
                        role="system",
                        content=(
                            "Return only valid JSON for WorkflowFinalAnswerDraft. "
                            "Required keys are: content (string), "
                            "contains_factual_claims (boolean), claims (array), "
                            "waiting_for_user_confirmation (boolean), "
                            "human_confirmation_present (boolean), and "
                            "action_status (one of none, draft, "
                            "awaiting_confirmation, executed). "
                            "Copy the prepared claims array exactly; do not add, "
                            "remove, or rewrite claims. Keep the booleans and "
                            "action_status consistent with the supplied workflow "
                            "state. Do not invent medical facts, bypass "
                            "confirmation, or claim external actions were completed."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False),
                    ),
                ),
            ),
            WorkflowFinalAnswerDraft,
        )
        state["model_call_trace"] = result.trace.model_dump(mode="json")
        if result.trace.fallback_used:
            state["degraded"] = True
            state.setdefault("errors", []).append(
                f"model_gateway_fallback:{result.trace.fallback_reason}"
            )
        if result.output is None:
            state["degraded"] = True
            state.setdefault("errors", []).append("model_gateway_failed")
            return

        answer = result.output
        if not self._answer_matches_workflow_state(
            answer,
            waiting=waiting,
            confirmed=confirmed,
            has_sources=bool(state.get("source_refs")),
            member_id=state["member_id"],
            source_ids={
                str(source.get("source_id"))
                for source in state.get("source_refs", [])
                if isinstance(source, dict) and source.get("source_id")
            },
        ):
            state["degraded"] = True
            state.setdefault("errors", []).append("model_output_contract_mismatch")
            return
        decision, audit = self.safety_guard.final_output(
            output=answer,
            member_id=state["member_id"],
        )
        self._record_safety_decision(state, decision)
        state["final_output_safety"] = audit.model_dump(mode="json")
        if decision.blocked:
            state["confirmation_state"] = "BLOCKED"
            state["status"] = "blocked"
            state["need_human_confirmation"] = False
            state["final_answer"] = (
                decision.message
                or "候选回答未通过安全检查，请转人工复核。"
            )
            state.setdefault("errors", []).append("final_output_safety_blocked")
            return
        state["final_claims"] = [
            claim.model_dump(mode="json") for claim in answer.claims
        ]
        state["final_answer"] = answer.content

    def _check_existing_final_answer(self, state: ProductWorkflowState) -> None:
        """Run the output gate for fixed blocked/error messages too."""

        decision, audit = self.safety_guard.final_output(
            output=state.get("final_answer", ""),
            member_id=state["member_id"],
        )
        self._record_safety_decision(state, decision)
        state["final_output_safety"] = audit.model_dump(mode="json")
        if decision.blocked:
            state["confirmation_state"] = "BLOCKED"
            state["need_human_confirmation"] = False
            state["final_answer"] = (
                decision.message
                or "当前回答未通过安全检查，请转人工复核。"
            )
            state.setdefault("errors", []).append("final_output_safety_blocked")

    @staticmethod
    def _answer_matches_workflow_state(
        answer: WorkflowFinalAnswerDraft,
        *,
        waiting: bool,
        confirmed: bool,
        has_sources: bool,
        member_id: str,
        source_ids: set[str],
    ) -> bool:
        if answer.waiting_for_user_confirmation != waiting:
            return False
        if answer.human_confirmation_present != confirmed:
            return False
        if answer.contains_factual_claims and not has_sources:
            return False
        if answer.contains_factual_claims and not answer.claims:
            return False
        if any(
            claim.subject_id != member_id
            or not set(claim.source_ids).issubset(source_ids)
            for claim in answer.claims
        ):
            return False
        if waiting and answer.action_status != "awaiting_confirmation":
            return False
        return True

    def _finalize(self, state: ProductWorkflowState) -> ProductWorkflowState:
        self._visit(state, "finalize")
        if state.get("status") == "needs_confirmation":
            state["need_human_confirmation"] = True
            if not state.get("final_answer"):
                state["final_answer"] = "已生成待确认草稿，确认后才会保存或提交。"
            self._generate_final_answer(state)
            return state
        if state.get("status") in {"blocked", "failed", "needs_clarification"}:
            self._check_existing_final_answer(state)
            return state
        if state.get("confirmation_result"):
            state["final_answer"] = (
                f"{state.get('final_answer', '草稿已处理')} 已记录为本地草稿，未向外部医院、药店或通知服务提交动作。"
            )
        state["status"] = "completed"
        state["need_human_confirmation"] = False
        self._generate_final_answer(state)
        return state

    def invoke(
        self,
        *,
        run_id: str,
        task_id: str,
        user_id: str,
        member_id: str,
        business_domain: BusinessDomain,
        user_input: str,
        input_payload: dict[str, Any] | None = None,
        provider_mode: ProviderMode = "mock",
        human_confirmation_granted: bool = False,
        idempotency_key: str | None = None,
    ) -> ProductWorkflowState:
        state: ProductWorkflowState = {
            "run_id": run_id,
            "task_id": task_id,
            "user_id": user_id,
            "member_id": member_id,
            "business_domain": business_domain,
            "intent": business_domain,
            "user_goal": user_input,
            "user_input": user_input,
            "input_payload": dict(input_payload or {}),
            "provider_mode": provider_mode,
            "human_confirmation_granted": human_confirmation_granted,
            "idempotency_key": idempotency_key or str(uuid4()),
            "status": "created",
            "final_answer": "",
            "final_claims": [],
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "model_call_trace": {},
            "degraded": False,
            "errors": [],
            "confirmation_request": {},
            "confirmation_result": {},
            "confirmation_state": "NONE",
            "confirmation_scope": {},
            "confirmation_draft": {},
            "safety_decisions": [],
            "final_output_safety": {},
            "visited_nodes": [],
        }
        return cast(ProductWorkflowState, self.graph.invoke(state))

    def resume_confirmation(
        self,
        state: ProductWorkflowState,
        *,
        run_id: str,
        human_confirmation_granted: bool = True,
    ) -> ProductWorkflowState:
        resumed: ProductWorkflowState = cast(ProductWorkflowState, dict(state))
        resumed["run_id"] = run_id
        resumed["human_confirmation_granted"] = human_confirmation_granted
        resumed["status"] = "running"
        resumed["final_answer"] = ""
        resumed["final_claims"] = []
        resumed["errors"] = []
        resumed["tool_calls"] = []
        resumed["provider_calls"] = []
        resumed["model_call_trace"] = {}
        resumed["visited_nodes"] = []
        resumed["confirmation_result"] = {}
        if not resumed.get("confirmation_state") and resumed.get(
            "confirmation_request"
        ):
            # Compatibility for states written before task seven introduced the
            # explicit state-machine field.
            resumed["confirmation_state"] = "DRAFT"
        if resumed.get("confirmation_state") != "DRAFT":
            resumed["confirmation_state"] = "BLOCKED"
            resumed["status"] = "blocked"
            resumed["need_human_confirmation"] = False
            resumed["final_answer"] = "当前任务不处于可确认的草稿状态。"
            return self._finalize(resumed)
        scope = self._scope_from_state(resumed)
        if scope is None or any(
            (
                scope.task_id != resumed["task_id"],
                scope.user_id != resumed["user_id"],
                scope.member_id != resumed["member_id"],
                scope.idempotency_key != resumed["idempotency_key"],
            )
        ):
            resumed["confirmation_state"] = "BLOCKED"
            resumed["status"] = "blocked"
            resumed["need_human_confirmation"] = False
            resumed["final_answer"] = "待确认草稿作用域校验失败，暂不执行任何动作。"
            resumed.setdefault("errors", []).append("confirmation_scope_conflict")
            return self._finalize(resumed)
        reviewed = self._safety_review(resumed)
        if reviewed.get("status") not in {"blocked", "failed", "needs_clarification"}:
            self._confirm(reviewed)
        return self._finalize(reviewed)

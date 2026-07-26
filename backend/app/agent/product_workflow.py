from __future__ import annotations

import json
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agent.safety import evaluate_safety
from app.providers import build_mock_provider_registry
from app.rag.retriever import create_knowledge_retriever
from app.schemas.business import BusinessDomain, ProviderMode
from app.tools.business_tools import register_business_tools
from app.tools.db_tools import create_db_tool_registry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult


ConfirmationAction = Literal[
    "refill_request",
    "consultation_request",
    "pharmacy_option",
    "reminder_create",
    "health_record",
]


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
    need_human_confirmation: bool
    safety_flags: list[str]
    source_refs: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    provider_calls: list[dict[str, Any]]
    degraded: bool
    errors: list[str]
    confirmation_request: dict[str, Any]
    confirmation_result: dict[str, Any]


class FamilyHealthProductWorkflow:
    """Bounded workflow for the three 4B business branches.

    The graph prepares evidence and local confirmation drafts. It never submits
    a consultation, purchase, reminder, or medical record to an external system.
    """

    def __init__(self, db: Session):
        self.db = db
        self.retriever = create_knowledge_retriever(db)
        self.registry = create_db_tool_registry(db, include_confirmation_tools=True)
        register_business_tools(
            self.registry,
            self.db,
            provider_registry=build_mock_provider_registry(),
            knowledge_retriever=self.retriever,
        )
        self.graph = self._build_graph()

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
        state["confirmation_request"] = {
            "tool_name": tool_name,
            "agent_role": agent_role,
            "action_type": action_type,
            "summary": summary,
            "payload": payload,
        }
        state["need_human_confirmation"] = True
        state["status"] = "needs_confirmation"

    def _safety_entry(self, state: ProductWorkflowState) -> ProductWorkflowState:
        decision = evaluate_safety(state.get("user_input", ""))
        state["safety_flags"] = list(decision.flags)
        state["need_human_confirmation"] = decision.requires_human_confirmation
        if decision.blocked:
            state["status"] = "blocked"
            state["final_answer"] = decision.message
        else:
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
        state["confirmation_request"] = {
            "tool_name": "create_health_record_draft",
            "agent_role": "ProfileAgent",
            "action_type": "health_record",
            "summary": "已整理报告内容，生成待确认的健康记录草稿。",
            "payload": {
                "user_id": state["user_id"],
                "member_id": state["member_id"],
                "idempotency_key": state["idempotency_key"],
                "summary": "报告解读结果草稿",
                "event_type": event_type,
                "payload": record_payload,
                "source_document_id": payload.get("source_document_id"),
                "source_refs": list(state.get("source_refs", [])),
            },
        }
        state["need_human_confirmation"] = True
        state["status"] = "needs_confirmation"
        state["final_answer"] = "已完成报告内容整理和来源检索，生成健康记录草稿；保存前需要你的确认。"
        return state

    def _safety_review(self, state: ProductWorkflowState) -> ProductWorkflowState:
        if state.get("status") in {"failed", "needs_clarification", "blocked"}:
            return state
        decision = evaluate_safety(
            " ".join(
                [
                    state.get("user_input", ""),
                    state.get("confirmation_request", {}).get("summary", ""),
                ]
            )
        )
        flags = list(dict.fromkeys(state.get("safety_flags", []) + decision.flags))
        state["safety_flags"] = flags
        if decision.blocked:
            state["status"] = "blocked"
            state["need_human_confirmation"] = decision.requires_human_confirmation
            state["final_answer"] = decision.message
            return state
        request = state.get("confirmation_request")
        if request:
            state["need_human_confirmation"] = True
            state["status"] = "needs_confirmation"
        else:
            state["status"] = "completed"
        return state

    def _route_after_review(self, state: ProductWorkflowState) -> str:
        if state.get("status") == "blocked":
            return "blocked"
        if state.get("confirmation_request") and state.get("human_confirmation_granted"):
            return "confirm"
        return "finalize"

    def _confirm(self, state: ProductWorkflowState) -> ProductWorkflowState:
        request = state.get("confirmation_request")
        if not request:
            state["status"] = "failed"
            state["final_answer"] = "没有找到待确认草稿，暂未执行任何动作。"
            return state
        if not state.get("human_confirmation_granted"):
            state["status"] = "needs_confirmation"
            state["need_human_confirmation"] = True
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
            return state
        state["confirmation_result"] = self._data(result)
        state["status"] = "completed"
        state["need_human_confirmation"] = False
        return state

    def _finalize(self, state: ProductWorkflowState) -> ProductWorkflowState:
        if state.get("status") == "needs_confirmation":
            state["need_human_confirmation"] = True
            if not state.get("final_answer"):
                state["final_answer"] = "已生成待确认草稿，确认后才会保存或提交。"
            return state
        if state.get("status") in {"blocked", "failed", "needs_clarification"}:
            return state
        if state.get("confirmation_result"):
            state["final_answer"] = (
                f"{state.get('final_answer', '草稿已处理')} 已记录为本地草稿，未向外部医院、药店或通知服务提交动作。"
            )
        state["status"] = "completed"
        state["need_human_confirmation"] = False
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
            "need_human_confirmation": False,
            "safety_flags": [],
            "source_refs": [],
            "tool_calls": [],
            "provider_calls": [],
            "degraded": False,
            "errors": [],
            "confirmation_request": {},
            "confirmation_result": {},
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
        resumed["errors"] = []
        resumed["tool_calls"] = []
        resumed["provider_calls"] = []
        resumed["confirmation_result"] = {}
        reviewed = self._safety_review(resumed)
        if reviewed.get("status") not in {"blocked", "failed", "needs_clarification"}:
            self._confirm(reviewed)
        return self._finalize(reviewed)

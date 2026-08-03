"""Tool-backed domain Agents used by the patient-facing Supervisor.

The original ``domain_agents`` module intentionally contains side-effect-free
deterministic Agents for harness tests.  This module is the runtime boundary:
the same three roles are now executed by the Supervisor with a per-run context
that owns a Tool Registry.  Agents never receive a database session and never
call a provider directly; they request a named tool and return structured
evidence to the Supervisor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.agent.context_schemas import ToolEvidenceRef
from app.agent.domain_agents import DomainAgent, DomainAgentInput
from app.agent.orchestration_schemas import AgentTaskResult, DomainAgentRole
from app.tools.tool_schemas import ToolResult


class RuntimeAgentContext(Protocol):
    """Small capability interface visible to a runtime domain Agent."""

    run_id: str
    task_id: str
    user_id: str
    member_id: str
    business_domain: str
    input_payload: dict[str, Any]
    human_confirmation_granted: bool
    is_confirmation_run: bool

    def trace_cursor(self) -> int: ...

    def call_tool(
        self,
        *,
        agent_role: DomainAgentRole,
        tool_name: str,
        payload: dict[str, Any],
        step_id: str,
        allowed_tools: tuple[str, ...],
    ) -> ToolResult: ...

    def tool_names_since(self, cursor: int) -> tuple[str, ...]: ...

    def evidence_refs_since(self, cursor: int) -> tuple[ToolEvidenceRef, ...]: ...

    def output_since(self, cursor: int) -> dict[str, Any]: ...

    def should_prepare_confirmation(self, agent_role: DomainAgentRole) -> bool: ...

    def prepare_confirmation(
        self,
        *,
        agent_role: DomainAgentRole,
        action_type: str,
        tool_name: str,
        summary: str,
        payload: dict[str, Any],
    ) -> None: ...

    def execute_confirmed_action(self, agent_role: DomainAgentRole) -> bool: ...

    def is_confirmation_target(self, agent_role: DomainAgentRole) -> bool: ...

    def set_final_answer(self, text: str) -> None: ...


class RuntimeDomainAgent(DomainAgent):
    """Base class that adds real tool evidence to ``AgentTaskResult``."""

    def __init__(self, runtime: RuntimeAgentContext) -> None:
        self.runtime = runtime
        self._trace_start = 0

    def execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        self._trace_start = self.runtime.trace_cursor()
        return super().execute(agent_input)

    def _result(
        self,
        agent_input: DomainAgentInput,
        *,
        facts: Mapping[str, Any],
        status: str = "completed",
        missing_information: tuple[str, ...] = (),
        requested_confirmation: bool = False,
        failure_reason: str | None = None,
        retryable: bool = False,
    ) -> AgentTaskResult:
        output = dict(facts)
        output.update(self.runtime.output_since(self._trace_start))
        return AgentTaskResult(
            task_id=agent_input.route.task_id,
            member_id=agent_input.route.member_id,
            agent_role=self.role,
            step_id=agent_input.step.step_id,
            status=status,
            facts=output,
            source_refs=self.runtime.evidence_refs_since(self._trace_start),
            tool_calls=self.runtime.tool_names_since(self._trace_start),
            missing_information=missing_information,
            requested_confirmation=requested_confirmation,
            failure_reason=failure_reason,
            retryable=retryable,
        )

    def _failure(
        self,
        agent_input: DomainAgentInput,
        result: ToolResult,
    ) -> AgentTaskResult:
        return self._result(
            agent_input,
            status="failed",
            facts={"workflow_action": "stop_after_tool_failure"},
            failure_reason=result.error_type or "tool_execution_failed",
        )

    def _call(
        self,
        agent_input: DomainAgentInput,
        *,
        tool_name: str,
        payload: dict[str, Any],
    ) -> ToolResult | AgentTaskResult:
        result = self.runtime.call_tool(
            agent_role=self.role,
            tool_name=tool_name,
            payload=payload,
            step_id=agent_input.step.step_id,
            allowed_tools=agent_input.allowed_tools,
        )
        if not result.success:
            return self._failure(agent_input, result)
        return result

    @staticmethod
    def _data(result: ToolResult) -> dict[str, Any]:
        return dict(result.output or {})


class RuntimeTriageAgent(RuntimeDomainAgent):
    """Handle pre-consultation preparation and safety-oriented triage."""

    role = "TriageAgent"
    allowed_tools = (
        "query_health_profile",
        "search_safety_knowledge",
        "hospital_list_departments",
        "hospital_list_slots",
        "consultation_prepare_draft",
        "search_business_knowledge",
        "create_confirmation_draft",
    )

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        if self.runtime.is_confirmation_run:
            if not self.runtime.is_confirmation_target(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "no_confirmation_action_for_role"},
                )
            if self.runtime.execute_confirmed_action(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "execute_confirmed_consultation"},
                )
            return self._result(
                agent_input,
                status="failed",
                facts={"workflow_action": "confirmation_failed"},
                failure_reason="confirmation_execution_failed",
            )

        profile = self._call(
            agent_input,
            tool_name="query_health_profile",
            payload={"user_id": self.runtime.user_id, "member_id": self.runtime.member_id},
        )
        if isinstance(profile, AgentTaskResult):
            return profile

        knowledge = self._call(
            agent_input,
            tool_name="search_safety_knowledge",
            payload={"query": "预问诊材料整理、红旗症状和人工确认边界"},
        )
        if isinstance(knowledge, AgentTaskResult):
            return knowledge

        if agent_input.route.intent == "safety_check":
            self.runtime.set_final_answer(
                "已完成症状和安全规则整理；当前不做疾病诊断，请根据安全提示及时联系医生或急救服务。"
            )
            return self._result(
                agent_input,
                facts={
                    "workflow_action": "prepare_safety_review",
                    "medical_claims_generated": False,
                },
            )

        payload = self.runtime.input_payload
        departments = self._call(
            agent_input,
            tool_name="hospital_list_departments",
            payload={
                "operation": "list_departments",
                "business_domain": "preconsultation",
                "user_id": self.runtime.user_id,
                "member_id": self.runtime.member_id,
                "payload": {"keyword": payload.get("department_keyword", "")},
            },
        )
        if isinstance(departments, AgentTaskResult):
            return departments
        department_data = self._data(departments).get("data", {})

        slots = self._call(
            agent_input,
            tool_name="hospital_list_slots",
            payload={
                "operation": "list_slots",
                "business_domain": "preconsultation",
                "user_id": self.runtime.user_id,
                "member_id": self.runtime.member_id,
                "payload": {
                    "department_candidates": department_data.get("candidates", []),
                    "preferred_date": payload.get("preferred_date"),
                },
            },
        )
        if isinstance(slots, AgentTaskResult):
            return slots

        draft = self._call(
            agent_input,
            tool_name="consultation_prepare_draft",
            payload={
                "operation": "prepare_draft",
                "business_domain": "preconsultation",
                "user_id": self.runtime.user_id,
                "member_id": self.runtime.member_id,
                "payload": {
                    "chief_complaint": payload.get("chief_complaint", payload.get("symptoms", "")),
                    "symptoms": payload.get("symptoms", ""),
                    "medication_changes": payload.get("medication_changes", ""),
                    "materials": payload.get("materials", []),
                },
            },
        )
        if isinstance(draft, AgentTaskResult):
            return draft

        if self.runtime.should_prepare_confirmation(self.role):
            self.runtime.prepare_confirmation(
                agent_role=self.role,
                action_type="consultation_request",
                tool_name="create_confirmation_draft",
                summary="已整理复诊材料、科室和可选时间，生成待确认的复诊申请草稿。",
                payload={
                    "draft_content": self._data(draft).get("data", {}),
                    "profile": self._data(profile),
                    "knowledge": self._data(knowledge),
                    "department_candidates": department_data.get("candidates", []),
                    "slot_candidates": self._data(slots).get("data", {}).get("slots", []),
                },
            )
        return self._result(
            agent_input,
            facts={
                "workflow_action": "prepare_preconsultation",
                "medical_claims_generated": False,
            },
            requested_confirmation=self.runtime.should_prepare_confirmation(self.role),
        )


class RuntimeMedicationAgent(RuntimeDomainAgent):
    """Read medication facts and prepare refill, pharmacy or reminder drafts."""

    role = "MedicationAgent"
    allowed_tools = (
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
        "search_business_knowledge",
        "consultation_prepare_draft",
        "pharmacy_search_inventory",
        "notification_prepare_reminder",
        "create_confirmation_draft",
    )

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        if self.runtime.is_confirmation_run:
            if not self.runtime.is_confirmation_target(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "no_confirmation_action_for_role"},
                )
            if self.runtime.execute_confirmed_action(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "execute_confirmed_medication_action"},
                )
            return self._result(
                agent_input,
                status="failed",
                facts={"workflow_action": "confirmation_failed"},
                failure_reason="confirmation_execution_failed",
            )

        payload = self.runtime.input_payload
        action_type = str(payload.get("action_type", "refill_request"))
        medicine_name = str(payload.get("medicine_name", "")).strip()
        if not medicine_name:
            return self._result(
                agent_input,
                status="needs_clarification",
                facts={"workflow_action": "request_medicine_name"},
                missing_information=("medicine_name",),
            )
        if action_type == "reminder_create" and not payload.get("schedule"):
            return self._result(
                agent_input,
                status="needs_clarification",
                facts={"workflow_action": "request_reminder_schedule"},
                missing_information=("schedule",),
            )
        if action_type not in {"refill_request", "pharmacy_option", "reminder_create"}:
            return self._result(
                agent_input,
                status="needs_clarification",
                facts={"workflow_action": "request_supported_medication_action"},
                missing_information=("action_type",),
            )

        profile = self._call(
            agent_input,
            tool_name="query_health_profile",
            payload={"user_id": self.runtime.user_id, "member_id": self.runtime.member_id},
        )
        if isinstance(profile, AgentTaskResult):
            return profile
        box = self._call(
            agent_input,
            tool_name="query_medicine_box",
            payload={"member_id": self.runtime.member_id},
        )
        if isinstance(box, AgentTaskResult):
            return box
        prescriptions = self._call(
            agent_input,
            tool_name="query_prescriptions",
            payload={"member_id": self.runtime.member_id},
        )
        if isinstance(prescriptions, AgentTaskResult):
            return prescriptions
        knowledge = self._call(
            agent_input,
            tool_name="search_safety_knowledge",
            payload={"query": f"{medicine_name} 用药流程、续方和人工确认边界"},
        )
        if isinstance(knowledge, AgentTaskResult):
            return knowledge

        action_result: ToolResult | AgentTaskResult | None = None
        if action_type == "pharmacy_option":
            action_result = self._call(
                agent_input,
                tool_name="pharmacy_search_inventory",
                payload={
                    "operation": "search_inventory",
                    "business_domain": "chronic_care",
                    "user_id": self.runtime.user_id,
                    "member_id": self.runtime.member_id,
                    "payload": {
                        "medicine_name": medicine_name,
                        "city": payload.get("city", ""),
                    },
                },
            )
        elif action_type == "refill_request":
            action_result = self._call(
                agent_input,
                tool_name="consultation_prepare_draft",
                payload={
                    "operation": "prepare_draft",
                    "business_domain": "chronic_care",
                    "user_id": self.runtime.user_id,
                    "member_id": self.runtime.member_id,
                    "payload": {
                        "medicine_name": medicine_name,
                        "materials": ["prescription", "medicine_box"],
                    },
                },
            )
        else:
            action_result = self._call(
                agent_input,
                tool_name="notification_prepare_reminder",
                payload={
                    "operation": "prepare_reminder",
                    "business_domain": "chronic_care",
                    "user_id": self.runtime.user_id,
                    "member_id": self.runtime.member_id,
                    "payload": {
                        "medicine_name": medicine_name,
                        "schedule": payload["schedule"],
                    },
                },
            )
        if isinstance(action_result, AgentTaskResult):
            return action_result

        if self.runtime.should_prepare_confirmation(self.role):
            summaries = {
                "refill_request": "已整理续方材料，生成待确认的续方申请草稿。",
                "pharmacy_option": "已查询购药候选方案，生成待确认的购药草稿。",
                "reminder_create": "已整理用药信息，生成待确认的提醒草稿。",
            }
            self.runtime.prepare_confirmation(
                agent_role=self.role,
                action_type=action_type,
                tool_name="create_confirmation_draft",
                summary=summaries[action_type],
                payload={
                    "medicine_name": medicine_name,
                    "profile": self._data(profile),
                    "medicine_box": self._data(box),
                    "prescriptions": self._data(prescriptions),
                    "knowledge": self._data(knowledge),
                    "action_result": self._data(action_result),
                    "schedule": payload.get("schedule"),
                },
            )
        return self._result(
            agent_input,
            facts={
                "workflow_action": "prepare_medication_workflow",
                "action_type": action_type,
                "medical_claims_generated": False,
            },
            requested_confirmation=self.runtime.should_prepare_confirmation(self.role),
        )


class RuntimeReportAgent(RuntimeDomainAgent):
    """Parse report material and create a source-backed health-record draft."""

    role = "ReportAgent"
    allowed_tools = (
        "parse_medical_document",
        "inspect_medical_image",
        "search_business_knowledge",
        "query_health_profile",
        "create_health_record_draft",
    )

    def _execute(self, agent_input: DomainAgentInput) -> AgentTaskResult:
        if self.runtime.is_confirmation_run:
            if not self.runtime.is_confirmation_target(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "no_confirmation_action_for_role"},
                )
            if self.runtime.execute_confirmed_action(self.role):
                return self._result(
                    agent_input,
                    facts={"workflow_action": "execute_confirmed_report_action"},
                )
            return self._result(
                agent_input,
                status="failed",
                facts={"workflow_action": "confirmation_failed"},
                failure_reason="confirmation_execution_failed",
            )

        payload = self.runtime.input_payload
        text = str(payload.get("text", payload.get("source_text", "")))
        if not text and not payload.get("image_uri"):
            return self._result(
                agent_input,
                status="needs_clarification",
                facts={"workflow_action": "request_report_material"},
                missing_information=("report_text_or_image",),
            )

        parsed = self._call(
            agent_input,
            tool_name="parse_medical_document",
            payload={
                "operation": "parse",
                "business_domain": "health_record",
                "user_id": self.runtime.user_id,
                "member_id": self.runtime.member_id,
                "payload": {
                    "text": text,
                    "document_type": payload.get("document_type", "medical_report"),
                },
            },
        )
        if isinstance(parsed, AgentTaskResult):
            return parsed

        image_quality: ToolResult | None = None
        if payload.get("image_uri"):
            image_quality = self._call(
                agent_input,
                tool_name="inspect_medical_image",
                payload={
                    "operation": "inspect_quality",
                    "business_domain": "health_record",
                    "user_id": self.runtime.user_id,
                    "member_id": self.runtime.member_id,
                    "payload": {"image_uri": payload["image_uri"]},
                },
            )
            if isinstance(image_quality, AgentTaskResult):
                return image_quality

        knowledge = self._call(
            agent_input,
            tool_name="search_business_knowledge",
            payload={
                "query": payload.get("knowledge_query", "检查报告说明边界和来源解释"),
                "purpose": "health_record",
                "mode": "hybrid",
                "limit": 5,
            },
        )
        if isinstance(knowledge, AgentTaskResult):
            return knowledge

        if self.runtime.should_prepare_confirmation(self.role):
            self.runtime.prepare_confirmation(
                agent_role=self.role,
                action_type="health_record",
                tool_name="create_health_record_draft",
                summary="已整理报告内容，生成待确认的健康记录草稿。",
                payload={
                    "user_id": self.runtime.user_id,
                    "member_id": self.runtime.member_id,
                    "idempotency_key": self.runtime.input_payload.get(
                        "idempotency_key", self.runtime.run_id
                    ),
                    "summary": "报告解读结果草稿",
                    "event_type": payload.get("event_type", "medical_report_explanation"),
                    "payload": {
                        "document_type": payload.get("document_type", "medical_report"),
                        "parsed_content": self._data(parsed),
                        "image_quality": self._data(image_quality) if image_quality else None,
                        "knowledge_evidence": self._data(knowledge),
                        "explanation_boundary": "仅做信息整理和来源解释，不替代医生诊断或调整处方。",
                    },
                    "source_document_id": payload.get("source_document_id"),
                },
            )
        return self._result(
            agent_input,
            facts={
                "workflow_action": "prepare_report_explanation",
                "medical_claims_generated": False,
            },
            requested_confirmation=self.runtime.should_prepare_confirmation(self.role),
        )


def build_runtime_domain_agent_registry(
    runtime: RuntimeAgentContext,
) -> dict[DomainAgentRole, DomainAgent]:
    """Create fresh runtime Agents for one run; no state is shared across runs."""

    return {
        "TriageAgent": RuntimeTriageAgent(runtime),
        "MedicationAgent": RuntimeMedicationAgent(runtime),
        "ReportAgent": RuntimeReportAgent(runtime),
    }


__all__ = [
    "RuntimeAgentContext",
    "RuntimeDomainAgent",
    "RuntimeMedicationAgent",
    "RuntimeReportAgent",
    "RuntimeTriageAgent",
    "build_runtime_domain_agent_registry",
]

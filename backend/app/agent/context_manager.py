from collections.abc import Iterable
from typing import Any

from app.agent.context_schemas import (
    ConfirmedFact,
    ContextEnvelope,
    ConversationSummary,
    ExecutionAgentRole,
    MemoryRef,
    RAGSourceRef,
    RoleSpecificContextView,
    RunSummary,
    TaskState,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult
from app.agent.run_trace_schemas import FinalAnswerTrace, RunTrace


class ResetContextState(dict[str, Any]):
    """A small serializable reset result used by tests and future adapters."""


class ContextManager:
    """Pure in-memory context builder/projector.

    This class does not call LLMs, tools, APIs, LangGraph, or a database. It only
    transforms already-frozen context artifacts into stricter Pydantic contracts.
    """

    ROLE_ALLOWED_TOOLS: dict[str, set[str]] = {
        "Planner": set(),
        "ProfileAgent": {"query_health_profile"},
        "RefillAgent": {
            "get_medicine_box",
            "query_health_profile",
            "query_medicine_box",
            "query_prescriptions",
            "query_purchase_records",
        },
        "PharmacyAgent": {
            "check_pharmacy_inventory",
            "create_confirmation_draft",
        },
        "ReminderAgent": {
            "create_confirmation_draft",
            "query_medicine_box",
        },
        "SafetyAgent": {
            "search_safety_knowledge",
        },
    }

    ROLE_TOOL_EVIDENCE: dict[str, set[str]] = {
        "Planner": set(),
        "ProfileAgent": {"query_health_profile"},
        "RefillAgent": {
            "get_medicine_box",
            "query_medicine_box",
            "query_prescriptions",
            "query_purchase_records",
        },
        "PharmacyAgent": {"check_pharmacy_inventory"},
        "ReminderAgent": {"create_confirmation_draft", "query_medicine_box"},
        "SafetyAgent": set(),
    }

    ROLE_SLOT_KEYWORDS: dict[str, tuple[str, ...]] = {
        "Planner": (),
        "ProfileAgent": ("member", "profile", "allergy", "chronic", "safety"),
        "RefillAgent": (
            "dosage",
            "frequency",
            "medicine",
            "prescription",
            "purchase",
            "remaining",
        ),
        "PharmacyAgent": ("delivery", "inventory", "pharmacy", "pickup", "stock"),
        "ReminderAgent": ("medicine", "reminder", "schedule"),
        "SafetyAgent": (),
    }

    def build_envelope(
        self,
        *,
        user_input: str,
        run_id: str,
        task_id: str,
        user_id: str,
        member_id: str,
        intent: str,
        action_type: str,
        missing_slots: list[str] | None = None,
        confirmed_slots: dict[str, Any] | None = None,
        pending_confirmations: list[str] | None = None,
        candidate_inferences: dict[str, Any] | None = None,
        tool_evidence_refs: list[ToolEvidenceRef] | None = None,
        rag_source_refs: list[RAGSourceRef] | None = None,
        safety_flags: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        memory_refs: list[MemoryRef] | None = None,
    ) -> ContextEnvelope:
        summary = self._summarize_user_input(user_input)
        task_state = TaskState(
            missing_slots=missing_slots or [],
            confirmed_slots=confirmed_slots or {},
            pending_confirmations=pending_confirmations or [],
            candidate_inferences=candidate_inferences or {},
        )
        return ContextEnvelope(
            run_id=run_id,
            task_id=task_id,
            user_id=user_id,
            member_id=member_id,
            intent=intent,
            action_type=action_type,
            task_state=task_state,
            conversation_summary=ConversationSummary(
                summary=summary,
                source_ids=[f"user_input:{run_id}"],
            ),
            tool_evidence_refs=tool_evidence_refs or [],
            rag_source_refs=rag_source_refs or [],
            safety_flags=safety_flags or [],
            allowed_tools=allowed_tools or [],
            memory_refs=memory_refs or [],
        )

    def build_role_view(
        self,
        envelope: ContextEnvelope,
        agent_role: str,
        *,
        extra_allowed_tools: list[str] | None = None,
    ) -> RoleSpecificContextView:
        if agent_role == "EvaluatorAgent":
            raise ValueError("EvaluatorAgent reads frozen run artifacts, not business context views")

        allowed_tools = self._visible_tools(
            envelope.allowed_tools,
            agent_role,
            extra_allowed_tools or [],
        )
        return RoleSpecificContextView(
            run_id=envelope.run_id,
            task_id=envelope.task_id,
            agent_role=agent_role,
            member_id=envelope.member_id,
            intent=envelope.intent,
            allowed_tools=allowed_tools,
            visible_task_state=self._visible_task_state(envelope, agent_role),
            visible_tool_evidence_refs=self._visible_tool_evidence(envelope, agent_role),
            visible_rag_source_refs=self._visible_rag_sources(envelope, agent_role),
            safety_flags=self._visible_safety_flags(envelope, agent_role),
        )

    def compact(self, envelopes: list[ContextEnvelope]) -> ContextEnvelope:
        if not envelopes:
            raise ValueError("compact requires at least one ContextEnvelope")

        task_ids = {envelope.task_id for envelope in envelopes}
        member_ids = {envelope.member_id for envelope in envelopes}
        if len(task_ids) != 1:
            raise ValueError("compact only supports contexts from the same task_id")
        if len(member_ids) != 1:
            raise ValueError("compact only supports contexts from the same member_id")

        latest = envelopes[-1]
        task_state = TaskState(
            missing_slots=self._unique(
                slot for envelope in envelopes for slot in envelope.task_state.missing_slots
            ),
            confirmed_slots=self._merge_confirmed_slots(envelopes),
            pending_confirmations=self._unique(
                item
                for envelope in envelopes
                for item in envelope.task_state.pending_confirmations
            ),
            candidate_inferences=self._merge_candidate_inferences(envelopes),
        )
        return ContextEnvelope(
            run_id=latest.run_id,
            task_id=latest.task_id,
            user_id=latest.user_id,
            member_id=latest.member_id,
            intent=latest.intent,
            action_type=latest.action_type,
            task_state=task_state,
            conversation_summary=ConversationSummary(
                summary=" | ".join(
                    envelope.conversation_summary.summary for envelope in envelopes
                    if envelope.conversation_summary.summary
                ),
                source_ids=self._unique(
                    source_id
                    for envelope in envelopes
                    for source_id in envelope.conversation_summary.source_ids
                ),
            ),
            tool_evidence_refs=self._unique_tool_refs(
                ref for envelope in envelopes for ref in envelope.tool_evidence_refs
            ),
            rag_source_refs=self._unique_rag_refs(
                ref for envelope in envelopes for ref in envelope.rag_source_refs
            ),
            safety_flags=self._unique(
                flag for envelope in envelopes for flag in envelope.safety_flags
            ),
            allowed_tools=self._unique(
                tool for envelope in envelopes for tool in envelope.allowed_tools
            ),
            memory_refs=self._unique_memory_refs(
                ref for envelope in envelopes for ref in envelope.memory_refs
            ),
        )

    def create_run_summary(
        self,
        *,
        envelope: ContextEnvelope,
        run_trace: RunTrace,
        final_answer: FinalAnswerTrace,
        evaluation_result: EvaluationResult | None = None,
        confirmed_facts: list[ConfirmedFact] | None = None,
    ) -> RunSummary:
        if run_trace.run_id != envelope.run_id:
            raise ValueError("run_trace run_id must match envelope run_id")
        if final_answer.answer_id != run_trace.final_answer.answer_id:
            raise ValueError("final_answer must match run_trace final_answer")
        if evaluation_result is not None and evaluation_result.run_id != envelope.run_id:
            raise ValueError("evaluation_result run_id must match envelope run_id")

        return RunSummary(
            run_id=envelope.run_id,
            task_id=envelope.task_id,
            member_id=envelope.member_id,
            intent=envelope.intent,
            final_status=self._final_status(envelope, run_trace, evaluation_result),
            confirmed_facts=confirmed_facts or [],
            pending_confirmations=envelope.task_state.pending_confirmations,
            safety_flags=self._unique([*envelope.safety_flags, *run_trace.safety_trace.flags]),
            tool_evidence_refs=envelope.tool_evidence_refs,
            rag_source_refs=envelope.rag_source_refs,
            final_answer_ref=final_answer.answer_id,
            evaluation_ref=(
                f"evaluation:{evaluation_result.case_id}:{evaluation_result.run_id}"
                if evaluation_result is not None
                else None
            ),
        )

    def reset_after_run(
        self,
        *,
        envelope: ContextEnvelope,
        run_trace: RunTrace,
        final_answer: FinalAnswerTrace,
        evaluation_result: EvaluationResult | None = None,
        confirmed_facts: list[ConfirmedFact] | None = None,
    ) -> ResetContextState:
        summary = self.create_run_summary(
            envelope=envelope,
            run_trace=run_trace,
            final_answer=final_answer,
            evaluation_result=evaluation_result,
            confirmed_facts=confirmed_facts,
        )
        return ResetContextState(
            run_summary=summary,
            retained_tool_evidence_refs=list(summary.tool_evidence_refs),
            retained_rag_source_refs=list(summary.rag_source_refs),
            run_trace_ref=f"run_trace:{run_trace.run_id}",
            final_answer_ref=summary.final_answer_ref,
            evaluation_ref=summary.evaluation_ref,
            memory_refs=list(envelope.memory_refs),
            working_context_cleared=True,
            cleared_fields=[
                "candidate_inferences",
                "raw_conversation",
                "scratchpad",
                "temporary_tool_outputs",
            ],
        )

    @staticmethod
    def _summarize_user_input(user_input: str) -> str:
        normalized = " ".join(user_input.split())
        if len(normalized) <= 160:
            return normalized
        return f"{normalized[:157]}..."

    def _visible_tools(
        self,
        envelope_tools: list[str],
        agent_role: str,
        extra_allowed_tools: list[str],
    ) -> list[str]:
        if agent_role == "Planner":
            return list(envelope_tools)
        allowed_by_role = self.ROLE_ALLOWED_TOOLS.get(agent_role, set())
        explicit = set(extra_allowed_tools)
        return [
            tool for tool in envelope_tools
            if tool in allowed_by_role or tool in explicit
        ]

    def _visible_task_state(
        self,
        envelope: ContextEnvelope,
        agent_role: str,
    ) -> TaskState:
        if agent_role in {"Planner", "SafetyAgent"}:
            confirmed_slots = dict(envelope.task_state.confirmed_slots)
            if agent_role == "Planner":
                confirmed_slots["conversation_summary"] = envelope.conversation_summary.summary
            return TaskState(
                missing_slots=list(envelope.task_state.missing_slots),
                confirmed_slots=confirmed_slots,
                pending_confirmations=list(envelope.task_state.pending_confirmations),
                candidate_inferences={},
            )

        keywords = self.ROLE_SLOT_KEYWORDS.get(agent_role, ())
        return TaskState(
            missing_slots=[
                slot for slot in envelope.task_state.missing_slots
                if self._matches_keywords(slot, keywords)
            ],
            confirmed_slots={
                key: value for key, value in envelope.task_state.confirmed_slots.items()
                if self._matches_keywords(key, keywords)
            },
            pending_confirmations=[
                item for item in envelope.task_state.pending_confirmations
                if self._matches_keywords(item, keywords)
                or item == "create_confirmation_draft"
            ],
            candidate_inferences={},
        )

    def _visible_tool_evidence(
        self,
        envelope: ContextEnvelope,
        agent_role: str,
    ) -> list[ToolEvidenceRef]:
        if agent_role == "SafetyAgent":
            return list(envelope.tool_evidence_refs)
        allowed_tools = self.ROLE_TOOL_EVIDENCE.get(agent_role, set())
        return [
            ref for ref in envelope.tool_evidence_refs
            if ref.tool_name in allowed_tools
        ]

    @staticmethod
    def _visible_rag_sources(
        envelope: ContextEnvelope,
        agent_role: str,
    ) -> list[RAGSourceRef]:
        if agent_role == "SafetyAgent":
            return [
                ref for ref in envelope.rag_source_refs
                if ContextManager._matches_keywords(
                    f"{ref.purpose} {ref.document_id} {ref.chunk_id}",
                    ("safety", "rule", "sop", "risk", "medical"),
                )
            ]
        if agent_role == "Planner":
            return []
        return [
            ref for ref in envelope.rag_source_refs
            if ContextManager._matches_keywords(ref.purpose, (agent_role.removesuffix("Agent").lower(),))
        ]

    @staticmethod
    def _visible_safety_flags(
        envelope: ContextEnvelope,
        agent_role: str,
    ) -> list[str]:
        if agent_role in {"Planner", "SafetyAgent"}:
            return list(envelope.safety_flags)
        return [
            flag for flag in envelope.safety_flags
            if flag.endswith("_confirmation_required")
            or ContextManager._matches_keywords(flag, (agent_role.removesuffix("Agent").lower(),))
        ]

    @staticmethod
    def _final_status(
        envelope: ContextEnvelope,
        run_trace: RunTrace,
        evaluation_result: EvaluationResult | None,
    ) -> str:
        if run_trace.safety_trace.blocked:
            return "blocked"
        if evaluation_result is not None and not evaluation_result.task_success:
            return "failed"
        if (
            envelope.task_state.pending_confirmations
            or run_trace.final_answer.waiting_for_user_confirmation
            or run_trace.final_answer.action_status == "awaiting_confirmation"
        ):
            return "needs_confirmation"
        return "completed"

    @staticmethod
    def _matches_keywords(value: str, keywords: tuple[str, ...]) -> bool:
        if not keywords:
            return True
        lower_value = value.lower()
        return any(keyword in lower_value for keyword in keywords)

    @staticmethod
    def _merge_confirmed_slots(envelopes: list[ContextEnvelope]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for envelope in envelopes:
            merged.update(envelope.task_state.confirmed_slots)
        return merged

    @staticmethod
    def _merge_candidate_inferences(envelopes: list[ContextEnvelope]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for envelope in envelopes:
            merged.update(envelope.task_state.candidate_inferences)
        return merged

    @staticmethod
    def _unique(items: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(items))

    @staticmethod
    def _unique_tool_refs(items: Iterable[ToolEvidenceRef]) -> list[ToolEvidenceRef]:
        indexed: dict[tuple[str, str | None], ToolEvidenceRef] = {}
        for item in items:
            indexed[(item.source_id, item.tool_call_id)] = item
        return list(indexed.values())

    @staticmethod
    def _unique_rag_refs(items: Iterable[RAGSourceRef]) -> list[RAGSourceRef]:
        indexed: dict[str, RAGSourceRef] = {}
        for item in items:
            indexed[item.source_id] = item
        return list(indexed.values())

    @staticmethod
    def _unique_memory_refs(items: Iterable[MemoryRef]) -> list[MemoryRef]:
        indexed: dict[str, MemoryRef] = {}
        for item in items:
            indexed[item.memory_id] = item
        return list(indexed.values())

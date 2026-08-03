from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]

Intent = Literal[
    "refill",
    "reminder",
    "pharmacy",
    "safety_check",
    "preconsultation",
    "chronic_care",
    "health_record",
]
ContextMode = Literal["all_history", "dependency_only"]
ActionType = Literal["draft", "query", "safety_review"]
ExecutionAgentRole = Literal[
    "Planner",
    "TriageAgent",
    "MedicationAgent",
    "ReportAgent",
    "ProfileAgent",
    "RefillAgent",
    "PharmacyAgent",
    "ReminderAgent",
    "SafetyAgent",
]
FinalStatus = Literal["completed", "needs_confirmation", "blocked", "failed"]
MemorySourceType = Literal[
    "user_confirmation",
    "tool_evidence",
    "rag_source",
    "model_inference",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        protected_namespaces=(),
    )


class TaskState(ContractModel):
    missing_slots: list[NonEmptyStr] = Field(default_factory=list)
    confirmed_slots: dict[str, Any] = Field(default_factory=dict)
    pending_confirmations: list[NonEmptyStr] = Field(default_factory=list)
    candidate_inferences: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(ContractModel):
    summary: str = ""
    source_ids: list[NonEmptyStr] = Field(default_factory=list)


class ToolEvidenceRef(ContractModel):
    source_id: NonEmptyStr
    run_id: NonEmptyStr
    member_id: NonEmptyStr
    tool_name: NonEmptyStr
    tool_call_id: NonEmptyStr | None = None
    success: bool
    schema_valid: bool


class RAGSourceRef(ContractModel):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    chunk_id: NonEmptyStr
    member_id: NonEmptyStr | None = None
    version: NonEmptyStr | None = None
    purpose: NonEmptyStr


class MemoryRef(ContractModel):
    memory_id: NonEmptyStr
    member_id: NonEmptyStr
    memory_type: NonEmptyStr
    source_id: NonEmptyStr
    source_type: MemorySourceType
    confirmed_by_user: bool

    @model_validator(mode="after")
    def reject_unconfirmed_memory(self) -> "MemoryRef":
        if not self.confirmed_by_user:
            raise ValueError("memory_refs only accept user-confirmed content")
        return self


class ConfirmedFact(ContractModel):
    fact_key: NonEmptyStr
    value: Any
    source_ids: list[NonEmptyStr] = Field(min_length=1)
    confirmed_by_user: bool = True

    @model_validator(mode="after")
    def require_user_confirmation(self) -> "ConfirmedFact":
        if not self.confirmed_by_user:
            raise ValueError("confirmed_facts must be confirmed by the user")
        return self


class ContextEnvelope(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    intent: Intent
    action_type: ActionType
    task_state: TaskState
    conversation_summary: ConversationSummary
    tool_evidence_refs: list[ToolEvidenceRef] = Field(default_factory=list)
    rag_source_refs: list[RAGSourceRef] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    memory_refs: list[MemoryRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_run_and_member_isolation(self) -> "ContextEnvelope":
        for evidence in self.tool_evidence_refs:
            if evidence.run_id != self.run_id:
                raise ValueError("tool evidence run_id must match the context run_id")
            if evidence.member_id != self.member_id:
                raise ValueError("tool evidence member_id must match the context member_id")

        for source in self.rag_source_refs:
            if source.member_id is not None and source.member_id != self.member_id:
                raise ValueError("RAG source member_id must match the context member_id")

        for memory in self.memory_refs:
            if memory.member_id != self.member_id:
                raise ValueError("memory member_id must match the context member_id")

        return self


class RoleSpecificContextView(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    agent_role: ExecutionAgentRole
    member_id: NonEmptyStr
    intent: Intent
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    visible_task_state: TaskState
    visible_tool_evidence_refs: list[ToolEvidenceRef] = Field(default_factory=list)
    visible_rag_source_refs: list[RAGSourceRef] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_visible_reference_isolation(self) -> "RoleSpecificContextView":
        for evidence in self.visible_tool_evidence_refs:
            if evidence.run_id != self.run_id:
                raise ValueError("visible tool evidence must belong to the current run")
            if evidence.member_id != self.member_id:
                raise ValueError("visible tool evidence must belong to the current member")

        for source in self.visible_rag_source_refs:
            if source.member_id is not None and source.member_id != self.member_id:
                raise ValueError("visible RAG source must belong to the current member")

        return self


class RunSummary(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    intent: Intent
    final_status: FinalStatus
    confirmed_facts: list[ConfirmedFact] = Field(default_factory=list)
    pending_confirmations: list[NonEmptyStr] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    tool_evidence_refs: list[ToolEvidenceRef] = Field(default_factory=list)
    rag_source_refs: list[RAGSourceRef] = Field(default_factory=list)
    final_answer_ref: NonEmptyStr
    evaluation_ref: NonEmptyStr | None

    @model_validator(mode="after")
    def enforce_summary_reference_isolation(self) -> "RunSummary":
        for evidence in self.tool_evidence_refs:
            if evidence.run_id != self.run_id:
                raise ValueError("summary tool evidence must belong to the current run")
            if evidence.member_id != self.member_id:
                raise ValueError("summary tool evidence must belong to the current member")

        for source in self.rag_source_refs:
            if source.member_id is not None and source.member_id != self.member_id:
                raise ValueError("summary RAG source must belong to the current member")

        return self

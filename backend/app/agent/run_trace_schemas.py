from typing import Literal
from uuid import UUID, uuid5

from pydantic import ConfigDict, Field

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr


ActionTraceStatus = Literal["none", "draft", "awaiting_confirmation", "executed"]
_TOOL_CALL_NAMESPACE = UUID("70f6b387-f71d-4221-bc4a-6c7b7a16c389")


class FrozenTraceModel(ContractModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class ToolCallTrace(FrozenTraceModel):
    tool_name: NonEmptyStr
    member_id: NonEmptyStr
    source_id: NonEmptyStr | None = None
    source_name: NonEmptyStr | None = None
    success: bool
    schema_valid: bool
    evidence_present: bool = False


class RAGTrace(FrozenTraceModel):
    source_id: NonEmptyStr
    source_name: NonEmptyStr
    member_id: NonEmptyStr | None = None
    retrieved: bool = True
    schema_valid: bool = True


class SafetyTrace(FrozenTraceModel):
    member_id: NonEmptyStr
    flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    blocked: bool = False
    requires_human_confirmation: bool = False


class FinalAnswerTrace(FrozenTraceModel):
    answer_id: NonEmptyStr
    content: str
    contains_factual_claims: bool
    waiting_for_user_confirmation: bool = False
    human_confirmation_present: bool = False
    action_status: ActionTraceStatus = "none"


class RunTrace(FrozenTraceModel):
    case_id: NonEmptyStr
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    intent: Intent
    tool_calls: tuple[ToolCallTrace, ...] = Field(default_factory=tuple)
    rag_traces: tuple[RAGTrace, ...] = Field(default_factory=tuple)
    safety_trace: SafetyTrace
    final_answer: FinalAnswerTrace
    latency_ms: int = Field(ge=0)
    schema_valid: bool = True


def build_tool_call_id(run_id: str, index: int, tool_name: str) -> str:
    """Return the stable database ID used by a run's ordered tool call."""
    return str(uuid5(_TOOL_CALL_NAMESPACE, f"{run_id}:{index}:{tool_name}"))

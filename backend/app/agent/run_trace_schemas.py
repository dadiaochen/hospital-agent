from typing import Literal
from uuid import UUID, uuid5

from pydantic import ConfigDict, Field, model_validator

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr
from app.agent.final_claim_schemas import AnswerEnvelope
from app.agent.orchestration_schemas import (
    AgentTaskResult,
    ComplexityRoute,
    ContextMode,
    ExecutionMode,
    SupervisorDecision,
    TaskPlan,
)


ActionTraceStatus = Literal["none", "draft", "awaiting_confirmation", "executed"]
TraceSchemaVersion = Literal["4d-b2.2", "4d-b2.3"]
ObservationEventType = Literal[
    "request",
    "node",
    "tool",
    "provider",
    "source",
    "model",
    "final",
]
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
    answer_envelope: AnswerEnvelope | None = None


class ObservationTrace(FrozenTraceModel):
    """Allow-listed operational event that never stores business payload text."""

    observation_id: NonEmptyStr
    request_id: NonEmptyStr
    task_id: NonEmptyStr
    run_id: NonEmptyStr
    member_id: NonEmptyStr
    event_type: ObservationEventType
    node_name: NonEmptyStr
    sequence_no: int = Field(ge=1)
    agent_role: NonEmptyStr | None = None
    tool_name: NonEmptyStr | None = None
    provider_name: NonEmptyStr | None = None
    model_name: NonEmptyStr | None = None
    success: bool | None = None
    latency_ms: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_reason: NonEmptyStr | None = None
    source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    token_usage_available: bool = False
    redaction_applied: bool = False
    redacted_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_observation(self) -> "ObservationTrace":
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.token_usage_available != all(value is not None for value in counts):
            raise ValueError("token_usage_available must match complete token counts")
        if any(value is not None for value in counts) and not self.token_usage_available:
            raise ValueError("partial token usage is not allowed")
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        if self.redaction_applied != bool(self.redacted_fields):
            raise ValueError("redaction_applied must match redacted_fields")
        return self


class OrchestrationTrace(FrozenTraceModel):
    """Frozen Router/Planner/Supervisor/domain-agent projection.

    The projection intentionally omits the raw user input from the nested
    routing request. The run already stores its identity; this artifact keeps
    only validated decisions needed for audit and later evaluation.
    """

    route: ComplexityRoute
    plan: TaskPlan | None = None
    supervisor_decisions: tuple[SupervisorDecision, ...] = Field(
        default_factory=tuple
    )
    domain_agent_results: tuple[AgentTaskResult, ...] = Field(
        default_factory=tuple
    )
    completed: bool
    termination_reason: NonEmptyStr
    steps_executed: int = Field(ge=0, le=3)
    used_planner: bool = False
    used_supervisor: bool = False
    execution_mode: ExecutionMode = "serial"
    context_mode: ContextMode = "dependency_only"
    parallel_batches: tuple[tuple[NonEmptyStr, ...], ...] = Field(
        default_factory=tuple
    )


class RunTrace(FrozenTraceModel):
    trace_schema_version: TraceSchemaVersion = "4d-b2.2"
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
    observations: tuple[ObservationTrace, ...] = Field(default_factory=tuple)
    orchestration: OrchestrationTrace | None = None
    context_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    dependency_result_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    token_usage_available: bool = False
    latency_ms: int = Field(ge=0)
    schema_valid: bool = True

    @model_validator(mode="after")
    def validate_orchestration_scope(self) -> "RunTrace":
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.token_usage_available != all(value is not None for value in counts):
            raise ValueError("token_usage_available must match complete token counts")
        if any(value is not None for value in counts) and not self.token_usage_available:
            raise ValueError("partial token usage is not allowed")
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens + output_tokens")

        envelope = self.final_answer.answer_envelope
        if self.trace_schema_version == "4d-b2.3" and envelope is None:
            raise ValueError("4d-b2.3 RunTrace requires an AnswerEnvelope")
        if envelope is not None:
            if any(
                (
                    envelope.answer_id != self.final_answer.answer_id,
                    envelope.run_id != self.run_id,
                    envelope.task_id != self.task_id,
                    envelope.member_id != self.member_id,
                    envelope.display_text != self.final_answer.content,
                    envelope.waiting_for_user_confirmation
                    != self.final_answer.waiting_for_user_confirmation,
                    envelope.human_confirmation_present
                    != self.final_answer.human_confirmation_present,
                    envelope.action_status != self.final_answer.action_status,
                )
            ):
                raise ValueError("AnswerEnvelope must match FinalAnswerTrace")
            if set(envelope.context_source_ids) != set(self.context_source_ids):
                raise ValueError(
                    "AnswerEnvelope context_source_ids must match RunTrace"
                )
            if set(envelope.dependency_result_ids) != set(self.dependency_result_ids):
                raise ValueError(
                    "AnswerEnvelope dependency_result_ids must match RunTrace"
                )

        if self.orchestration is None:
            return self
        route = self.orchestration.route
        if any(
            (
                route.task_id != self.task_id,
                route.user_id != self.user_id,
                route.member_id != self.member_id,
            )
        ):
            raise ValueError("orchestration scope must match the run trace")
        if self.orchestration.plan is not None and any(
            (
                self.orchestration.plan.task_id != self.task_id,
                self.orchestration.plan.user_id != self.user_id,
                self.orchestration.plan.member_id != self.member_id,
            )
        ):
            raise ValueError("orchestration plan scope must match the run trace")
        for result in self.orchestration.domain_agent_results:
            if any(
                (
                    result.task_id != self.task_id,
                    result.member_id != self.member_id,
                )
            ):
                raise ValueError(
                    "orchestration domain-agent result scope must match the run trace"
                )
        return self


def build_tool_call_id(run_id: str, index: int, tool_name: str) -> str:
    """Return the stable database ID used by a run's ordered tool call."""
    return str(uuid5(_TOOL_CALL_NAMESPACE, f"{run_id}:{index}:{tool_name}"))

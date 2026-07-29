"""Frozen contracts for the 4B task-eleven orchestration ablation harness."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr
from app.agent.eval_schemas import EvaluationResult
from app.agent.orchestration_schemas import DomainAgentRole
from app.agent.run_trace_schemas import RunTrace


AblationStrategy = Literal[
    "single_agent",
    "fixed_router",
    "bounded_supervisor",
]
BusinessHarnessCategory = Literal[
    "normal_single_domain",
    "complex_cross_domain",
    "missing_information",
    "high_risk_medical",
    "rag_and_source",
    "provider_or_tool_failure",
    "member_isolation_attack",
    "confirmation_idempotency",
]
TaskComplexity = Literal["simple", "complex"]
ExpectedBehavior = Literal[
    "completed",
    "needs_clarification",
    "blocked",
    "needs_confirmation",
    "degraded",
]
GovernanceStage = Literal["request", "action", "final_output", "evaluator"]


class FrozenAblationModel(ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        protected_namespaces=(),
        frozen=True,
    )


class FairnessConfig(FrozenAblationModel):
    """Conditions that must be identical across all three strategies."""

    config_id: NonEmptyStr
    model_provider: NonEmptyStr
    model_name: NonEmptyStr
    tool_catalog_version: NonEmptyStr
    rag_index_version: NonEmptyStr
    safety_policy_version: NonEmptyStr
    confirmation_policy_version: NonEmptyStr
    context_token_limit: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_token_limits(self) -> "FairnessConfig":
        if self.max_output_tokens > self.context_token_limit:
            raise ValueError("max_output_tokens cannot exceed context_token_limit")
        return self


class ExpectedToolInvocation(FrozenAblationModel):
    tool_name: NonEmptyStr
    owner_role: DomainAgentRole
    parameters: dict[NonEmptyStr, Any] = Field(default_factory=dict)
    success: bool = True
    schema_valid: bool = True
    evidence_present: bool = False
    source_id: NonEmptyStr | None = None
    source_name: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> "ExpectedToolInvocation":
        if self.evidence_present and (self.source_id is None or self.source_name is None):
            raise ValueError("evidence-bearing tool calls require source_id and source_name")
        if not self.success and self.evidence_present:
            raise ValueError("failed tool calls cannot claim evidence")
        return self


class BusinessHarnessCase(FrozenAblationModel):
    case_id: NonEmptyStr
    category: BusinessHarnessCategory
    complexity: TaskComplexity
    user_input: NonEmptyStr
    intent: Intent
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    primary_role: DomainAgentRole
    expected_role_order: tuple[DomainAgentRole, ...] = Field(min_length=1, max_length=3)
    expected_tool_calls: tuple[ExpectedToolInvocation, ...] = Field(default_factory=tuple)
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_behavior: ExpectedBehavior
    expected_human_confirmation_required: bool = False
    forbidden_phrases: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    relevant_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    ranked_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    cited_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    contains_factual_claims: bool = False

    @model_validator(mode="after")
    def validate_case(self) -> "BusinessHarnessCase":
        if self.expected_role_order[0] != self.primary_role:
            raise ValueError("primary_role must be the first expected role")
        if self.complexity == "simple" and len(self.expected_role_order) != 1:
            raise ValueError("simple cases must have exactly one expected role")
        if self.complexity == "complex" and len(self.expected_role_order) < 2:
            raise ValueError("complex cases must have at least two expected roles")
        if self.category == "complex_cross_domain" and self.complexity != "complex":
            raise ValueError("complex_cross_domain cases must use complexity=complex")
        if self.category == "high_risk_medical" and not self.expected_safety_flags:
            raise ValueError("high-risk cases require expected safety flags")
        if self.category == "rag_and_source" and not self.relevant_rag_source_ids:
            raise ValueError("RAG cases require relevant source ids")
        if set(self.cited_source_ids) - set(self.ranked_rag_source_ids):
            raise ValueError("citations must come from the shared ranked RAG result")
        for invocation in self.expected_tool_calls:
            if invocation.owner_role not in self.expected_role_order:
                raise ValueError("tool owner must be present in expected_role_order")
            parameter_member = invocation.parameters.get("member_id")
            if parameter_member is not None and parameter_member != self.member_id:
                raise ValueError("expected tool parameters cannot cross member scope")
        return self


class AblationToolCallTrace(FrozenAblationModel):
    tool_name: NonEmptyStr
    agent_role: NonEmptyStr
    parameters: dict[NonEmptyStr, Any] = Field(default_factory=dict)
    success: bool
    schema_valid: bool
    evidence_present: bool = False
    source_id: NonEmptyStr | None = None
    source_name: NonEmptyStr | None = None


class AblationRunTrace(FrozenAblationModel):
    """A frozen business RunTrace plus orchestration-only audit fields."""

    strategy: AblationStrategy
    fairness_config_id: NonEmptyStr
    run_trace: RunTrace
    role_sequence: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    tool_calls: tuple[AblationToolCallTrace, ...] = Field(default_factory=tuple)
    governance_stages: tuple[GovernanceStage, ...]
    ranked_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    cited_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    token_usage_available: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    billed_cost_usd: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_trace_alignment(self) -> "AblationRunTrace":
        run_tools = tuple(item.tool_name for item in self.run_trace.tool_calls)
        audit_tools = tuple(item.tool_name for item in self.tool_calls)
        if run_tools != audit_tools:
            raise ValueError("RunTrace and ablation tool-call order must match")
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.token_usage_available != all(value is not None for value in counts):
            raise ValueError("token usage availability must match complete counts")
        if not self.token_usage_available and any(value is not None for value in counts):
            raise ValueError("synthetic or partial token counts are not allowed")
        if self.token_usage_available and self.total_tokens != self.input_tokens + self.output_tokens:  # type: ignore[operator]
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        if not self.token_usage_available and self.billed_cost_usd is not None:
            raise ValueError("cost cannot be claimed when token usage is unavailable")
        return self


class AblationCaseResult(FrozenAblationModel):
    case_id: NonEmptyStr
    category: BusinessHarnessCategory
    complexity: TaskComplexity
    strategy: AblationStrategy
    evaluation: EvaluationResult
    trace: AblationRunTrace
    task_completed: bool
    tool_set_exact_match: bool
    tool_parameter_exact_match: bool
    role_order_exact_match: bool | None
    required_role_coverage: float = Field(ge=0.0, le=1.0)
    unnecessary_handoffs: int = Field(ge=0)
    duplicate_tool_calls: int = Field(ge=0)
    safety_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    governance_coverage: float = Field(ge=0.0, le=1.0)
    rag_recall_at_3: float | None = Field(default=None, ge=0.0, le=1.0)
    rag_recall_at_5: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_correctness: float | None = Field(default=None, ge=0.0, le=1.0)


class SliceMetrics(FrozenAblationModel):
    case_count: int = Field(ge=0)
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    tool_set_exact_match_rate: float = Field(ge=0.0, le=1.0)
    tool_parameter_exact_match_rate: float = Field(ge=0.0, le=1.0)


class StrategyMetrics(FrozenAblationModel):
    strategy: AblationStrategy
    case_count: int = Field(ge=0)
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    tool_set_exact_match_rate: float = Field(ge=0.0, le=1.0)
    tool_parameter_exact_match_rate: float = Field(ge=0.0, le=1.0)
    route_order_exact_match_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    required_role_coverage_avg: float = Field(ge=0.0, le=1.0)
    unnecessary_handoffs_avg: float = Field(ge=0.0)
    duplicate_tool_calls_avg: float = Field(ge=0.0)
    safety_recall_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    safety_precision_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    context_isolation_pass_rate: float = Field(ge=0.0, le=1.0)
    governance_coverage_rate: float = Field(ge=0.0, le=1.0)
    rag_recall_at_3: float | None = Field(default=None, ge=0.0, le=1.0)
    rag_recall_at_5: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_correctness_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    p50_latency_ms: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    token_usage_available_rate: float = Field(ge=0.0, le=1.0)
    avg_total_tokens: float | None = Field(default=None, ge=0.0)
    total_billed_cost_usd: float | None = Field(default=None, ge=0.0)
    simple: SliceMetrics
    complex: SliceMetrics


class AblationHarnessOutput(FrozenAblationModel):
    fairness_config: FairnessConfig
    results: tuple[AblationCaseResult, ...]
    metrics: tuple[StrategyMetrics, ...]


__all__ = [
    "AblationCaseResult",
    "AblationHarnessOutput",
    "AblationRunTrace",
    "AblationStrategy",
    "AblationToolCallTrace",
    "BusinessHarnessCase",
    "BusinessHarnessCategory",
    "ExpectedToolInvocation",
    "FairnessConfig",
    "GovernanceStage",
    "SliceMetrics",
    "StrategyMetrics",
    "TaskComplexity",
]

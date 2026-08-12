"""Contracts for the 4D-B2.5 materializer, graders and eval runner.

These models describe an evaluation run, not a production business request.
They make the boundary explicit between:

* a frozen ``RunTrace`` produced by an executor;
* the observations needed by deterministic graders; and
* the aggregated, review-aware report written by the runner.

The default B2.5 executor is an in-memory deterministic projection of Gold.
It is useful for proving the evaluation pipeline and its failure taxonomy,
but it is intentionally not presented as a PostgreSQL or real-provider
quality result.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr
from app.agent.run_trace_schemas import RunTrace, ToolCallTrace
from app.agent.v2_benchmark_schemas import (
    DatasetSplit,
    EvalDependencyEdge,
    ExpectedRoute,
)


LayerName = Literal[
    "route",
    "plan",
    "tool",
    "claim",
    "rag",
    "safety",
    "context",
    "reliability",
    "database_state",
]
ReportStatus = Literal["preview", "completed", "blocked"]
RunnerMode = Literal["synthetic_projection", "integration"]
ConfirmationDraftStatus = Literal["DRAFT", "CONFIRMED", "REJECTED"]


class ConfirmationDraftSnapshot(ContractModel):
    """Safe, read-only evidence and preview for a local confirmation draft.

    The B3 review queue must prove that a draft existed without copying the
    full medical payload into an evaluation report.  ``preview`` contains
    only user-facing action fields; the full payload remains in the normal
    business checkpoint/API response and is never an external action by
    itself.
    """

    draft_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    action_type: NonEmptyStr
    status: ConfirmationDraftStatus
    draft_version: int = Field(ge=1)
    need_human_confirmation: bool
    local_only: bool
    external_action_status: Literal["not_submitted"]
    summary: NonEmptyStr | None = None
    preview: dict[str, object] = Field(default_factory=dict)


class LayerGrade(ContractModel):
    """One deterministic grader result for one query run."""

    grader: LayerName
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    failure_reasons: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    details: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_score_and_reasons(self) -> "LayerGrade":
        if self.passed and self.failure_reasons:
            raise ValueError("a passed grader cannot contain failure_reasons")
        if not self.passed and not self.failure_reasons:
            raise ValueError("a failed grader requires failure_reasons")
        return self


class MaterializationReceipt(ContractModel):
    """The isolated namespace created for one WorldState/query pair."""

    world_state_id: NonEmptyStr
    query_id: NonEmptyStr
    namespace: NonEmptyStr
    member_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    materialized_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    stale_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    gold_hash: str = Field(min_length=64, max_length=64)
    backend: Literal[
        "in_memory_projection",
        "postgresql_shadow_transaction",
    ] = "in_memory_projection"
    cleanup_succeeded: bool = False


class V2RunArtifacts(ContractModel):
    """Frozen run trace plus normalized observations consumed by graders.

    An integration executor can fill this model from the real graph.  The
    synthetic executor fills the same fields from the WorldState Gold so the
    runner and graders are tested without calling a database, API or LLM.
    """

    run_trace: RunTrace
    route_mode: ExpectedRoute
    observed_intent: Intent
    observed_agent_roles: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_domain_steps: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_domain_dependency_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    observed_governance_steps: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_governance_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    observed_tool_names: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_blocked: bool
    observed_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    observed_database_changes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    confirmation_draft: ConfirmationDraftSnapshot | None = None
    provider_attempts: int = Field(default=1, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_action: NonEmptyStr = "none"
    external_action_status: NonEmptyStr = "none"
    checkpoint_restored: bool = False
    foreign_member_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    cleanup_succeeded: bool = False

    @model_validator(mode="after")
    def validate_trace_scope(self) -> "V2RunArtifacts":
        domain_steps = set(self.observed_domain_steps)
        governance_steps = set(self.observed_governance_steps)
        if domain_steps & governance_steps:
            raise ValueError("observed domain and governance steps must be disjoint")
        if any(
            edge.upstream_step_id not in domain_steps
            or edge.downstream_step_id not in domain_steps
            for edge in self.observed_domain_dependency_edges
        ):
            raise ValueError(
                "observed domain dependency edges must reference domain steps"
            )
        known_steps = domain_steps | governance_steps
        if any(
            edge.upstream_step_id not in known_steps
            or edge.downstream_step_id not in known_steps
            for edge in self.observed_governance_edges
        ):
            raise ValueError(
                "observed governance edges must reference known steps"
            )
        trace = self.run_trace
        observed_sources = set(self.observed_source_ids)
        trace_sources = {
            *(call.source_id for call in trace.tool_calls if call.source_id),
            *(rag.source_id for rag in trace.rag_traces),
            *trace.context_source_ids,
        }
        if not trace_sources.issubset(observed_sources):
            raise ValueError(
                "observed_source_ids must include every source in RunTrace"
            )
        if self.observed_rag_source_ids and not set(self.observed_rag_source_ids).issubset(
            observed_sources
        ):
            raise ValueError("observed_rag_source_ids must be observed sources")
        return self


class V2CaseEvaluation(ContractModel):
    """All layer grades and aggregate outcome for one query variant."""

    query_id: NonEmptyStr
    world_state_id: NonEmptyStr
    dataset_split: DatasetSplit
    run_id: NonEmptyStr
    task_success: bool
    intent_correct: bool
    route_correct: bool
    tool_call_correct: bool
    tool_parameter_correct: bool
    matched_parameter_call_count: int = Field(ge=0)
    correct_parameter_call_count: int = Field(ge=0)
    final_answer_correct: bool
    expected_blocked: bool
    observed_blocked: bool
    tool_calls: tuple[ToolCallTrace, ...] = Field(default_factory=tuple)
    layer_grades: tuple[LayerGrade, ...] = Field(min_length=9, max_length=9)
    failure_reasons: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    latency_ms: int = Field(ge=0)
    materialization_backend: Literal[
        "in_memory_projection",
        "postgresql_shadow_transaction",
    ] = (
        "in_memory_projection"
    )
    cleanup_succeeded: bool
    # The unified synthetic dataset is frozen from deterministic business
    # state. It is automatically Gold-scored and never waits for a person to
    # review every generated row. Legacy fixture flows can still use the
    # historical pending/human states.
    review_status: Literal["automatic_gold", "pending_review", "human_reviewed"] = (
        "automatic_gold"
    )

    @model_validator(mode="after")
    def validate_grade_set(self) -> "V2CaseEvaluation":
        graders = [grade.grader for grade in self.layer_grades]
        expected = {
            "route",
            "plan",
            "tool",
            "claim",
            "rag",
            "safety",
            "context",
            "reliability",
            "database_state",
        }
        if set(graders) != expected or len(graders) != len(set(graders)):
            raise ValueError("one unique grade is required for every B2.5 grader")
        if self.task_success and self.failure_reasons:
            raise ValueError("successful case cannot contain failure_reasons")
        if not self.task_success and not self.failure_reasons:
            raise ValueError("failed case requires failure_reasons")
        return self


class V2Metric(ContractModel):
    name: NonEmptyStr
    value: float = Field(ge=0.0)
    sample_count: int = Field(ge=0)
    status: ReportStatus
    note: NonEmptyStr


class V2EvalReport(ContractModel):
    """Review-aware JSON report produced by the unified runner."""

    report_id: NonEmptyStr
    dataset_version: NonEmptyStr
    runner_mode: RunnerMode
    status: ReportStatus
    dataset_split: Literal["all", "development", "validation", "holdout"]
    generated_at: datetime
    sample_count: int = Field(ge=0)
    case_results: tuple[V2CaseEvaluation, ...] = Field(default_factory=tuple)
    metrics: tuple[V2Metric, ...] = Field(default_factory=tuple)
    failure_counts: dict[str, int] = Field(default_factory=dict)
    world_states_sha256: str = Field(min_length=64, max_length=64)
    queries_sha256: str = Field(min_length=64, max_length=64)
    notes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class V2RunnerOptions(ContractModel):
    """Server-owned options for a deterministic local evaluation preview."""

    dataset_split: Literal["all", "development", "validation", "holdout"] = "all"
    max_cases: int | None = Field(default=None, ge=1)
    query_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    runner_mode: RunnerMode = "synthetic_projection"
    allow_pending_review: bool = False
    repeat: int = Field(default=1, ge=1, le=3)
    concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description=(
            "Bounded number of independent evaluation Query groups to run in "
            "parallel. Repeats of the same Query remain serial."
        ),
    )

    @model_validator(mode="after")
    def validate_mode(self) -> "V2RunnerOptions":
        return self


__all__ = [
    "ConfirmationDraftSnapshot",
    "LayerGrade",
    "MaterializationReceipt",
    "ReportStatus",
    "RunnerMode",
    "V2CaseEvaluation",
    "V2EvalReport",
    "V2Metric",
    "V2RunArtifacts",
    "V2RunnerOptions",
]

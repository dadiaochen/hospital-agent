"""Frozen observation contracts for the local 4D-B benchmark.

These models describe evidence produced by the local test harness.  They are
separate from the reviewed gold labels so a generated observation cannot be
mistaken for a human-verified expected answer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import NonEmptyStr
from app.agent.eval_schemas import EvaluationResult
from app.agent.model_gateway_schemas import ModelCallTrace
from app.agent.run_trace_schemas import FrozenTraceModel, RunTrace
from app.providers.schemas import ProviderAttemptTrace


LocalObservationMode = Literal["local_integration"]
LocalRAGMode = Literal["keyword", "vector", "hybrid"]


class LocalRAGCase(FrozenTraceModel):
    """A small synthetic RAG gold case whose source mapping is unambiguous."""

    case_id: NonEmptyStr
    query: NonEmptyStr
    purpose: NonEmptyStr
    category: NonEmptyStr
    mode: LocalRAGMode = "keyword"
    top_k: int = Field(default=3, ge=1, le=10)
    expected_source_id: NonEmptyStr
    expected_source: NonEmptyStr


class LocalAgentObservation(FrozenTraceModel):
    """One bounded-Supervisor run plus its measured local execution evidence."""

    case_id: NonEmptyStr
    category: NonEmptyStr
    strategy: Literal["bounded_supervisor"]
    run_trace: RunTrace
    evaluation: EvaluationResult
    relevant_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    ranked_rag_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    cited_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    fixture_latency_ms: int = Field(ge=0)
    execution_latency_ms: float = Field(gt=0.0)
    model_call_trace: ModelCallTrace | None = None
    environment: dict[NonEmptyStr, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trace_alignment(self) -> "LocalAgentObservation":
        if self.case_id != self.run_trace.case_id:
            raise ValueError("agent observation case_id must match RunTrace")
        if self.case_id != self.evaluation.case_id:
            raise ValueError("agent observation case_id must match EvaluationResult")
        if self.run_trace.run_id != self.evaluation.run_id:
            raise ValueError("agent observation run_id must match EvaluationResult")
        if self.run_trace.latency_ms != max(1, round(self.execution_latency_ms)):
            raise ValueError("RunTrace latency must round from measured local latency")
        if set(self.cited_source_ids) - set(self.ranked_rag_source_ids):
            raise ValueError("citations must come from the recorded RAG ranking")
        return self


class LocalRAGObservation(FrozenTraceModel):
    """One retrieval executed against the synthetic local knowledge database."""

    case_id: NonEmptyStr
    query: NonEmptyStr
    category: NonEmptyStr
    requested_mode: LocalRAGMode
    effective_mode: LocalRAGMode
    expected_source_id: NonEmptyStr
    expected_source: NonEmptyStr
    ranked_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    cited_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    fallback_used: bool = False
    fallback_reason: NonEmptyStr | None = None
    latency_ms: int = Field(ge=1)
    embedding_model: NonEmptyStr | None = None
    embedding_schema_version: NonEmptyStr | None = None
    environment: dict[NonEmptyStr, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rag_evidence(self) -> "LocalRAGObservation":
        if set(self.cited_source_ids) - set(self.ranked_source_ids):
            raise ValueError("RAG citations must come from the recorded ranking")
        return self


class LocalMemoryObservation(FrozenTraceModel):
    """Observed ContextManager retention and member-isolation checks."""

    case_id: NonEmptyStr
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    expected_retained_fact_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    retained_fact_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_memory_write_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    actual_memory_write_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    unconfirmed_memory_write_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_dropped_fact_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    member_scope_leakage: bool = False
    source_pointers_preserved: bool
    checkpoint_source: NonEmptyStr
    checkpoint_recovery_observed: bool | None = None
    latency_ms: int = Field(ge=1)


class LocalProviderObservation(FrozenTraceModel):
    """Provider retry/fallback evidence from an injected local fault."""

    case_id: NonEmptyStr
    provider_name: NonEmptyStr
    operation: NonEmptyStr
    read_only: bool
    injected_fault: NonEmptyStr
    expected_retryable: bool
    expected_max_attempts: int = Field(ge=1, le=5)
    attempts: tuple[ProviderAttemptTrace, ...] = Field(default_factory=tuple)
    success: bool
    provider_recovered: bool
    safe_degraded: bool
    write_retry_count: int = Field(ge=0)
    latency_ms: int = Field(ge=1)
    environment: dict[NonEmptyStr, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_attempts(self) -> "LocalProviderObservation":
        if self.attempts and tuple(
            attempt.attempt_no for attempt in self.attempts
        ) != tuple(range(1, len(self.attempts) + 1)):
            raise ValueError("provider attempts must be consecutively numbered")
        if self.provider_recovered != self.success:
            raise ValueError("provider_recovered must match successful recovery")
        if self.write_retry_count != max(0, len(self.attempts) - 1) and not self.read_only:
            raise ValueError("write retry count must match provider attempts")
        return self


class LocalObservationBundle(FrozenTraceModel):
    """The complete local evidence set consumed by the observed runner."""

    bundle_version: NonEmptyStr
    mode: LocalObservationMode
    generated_at: datetime
    fixture_sha256: str = Field(min_length=64, max_length=64)
    environment: dict[NonEmptyStr, str] = Field(default_factory=dict)
    agent_runs: tuple[LocalAgentObservation, ...] = Field(default_factory=tuple)
    rag_queries: tuple[LocalRAGObservation, ...] = Field(default_factory=tuple)
    memory_cases: tuple[LocalMemoryObservation, ...] = Field(default_factory=tuple)
    provider_cases: tuple[LocalProviderObservation, ...] = Field(default_factory=tuple)


__all__ = [
    "LocalAgentObservation",
    "LocalMemoryObservation",
    "LocalObservationBundle",
    "LocalObservationMode",
    "LocalProviderObservation",
    "LocalRAGCase",
    "LocalRAGObservation",
]

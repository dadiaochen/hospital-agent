"""Pydantic contracts for the versioned 4D benchmark data and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import Field

from app.agent.context_schemas import ContractModel, NonEmptyStr


BenchmarkMode = Literal[
    "deterministic",
    "local_integration",
    "real_model",
    "docker_integration",
]
BenchmarkRunStatus = Literal["completed", "not_available"]
MetricStatus = Literal["measured", "not_available"]
MetricType = Literal["dataset_contract", "runtime_observation"]
ReviewStatus = Literal["approved"]


class BenchmarkCaseMetadata(ContractModel):
    case_id: NonEmptyStr
    category: NonEmptyStr
    generated_by_ai: bool
    human_reviewed: Literal[True]
    review_status: ReviewStatus
    review_notes: str = ""
    reviewer_id: NonEmptyStr
    reviewed_at: datetime


class AnswerQualityCase(BenchmarkCaseMetadata):
    user_input: NonEmptyStr
    member_id: NonEmptyStr
    expected_behavior: NonEmptyStr
    expected_human_confirmation_required: bool
    expected_safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    expected_source_keys: list[NonEmptyStr] = Field(default_factory=list)
    must_include: list[NonEmptyStr] = Field(default_factory=list)
    forbidden_phrases: list[NonEmptyStr] = Field(default_factory=list)
    contains_factual_claims: bool


class RAGGoldCase(BenchmarkCaseMetadata):
    query: NonEmptyStr
    purpose: NonEmptyStr
    requested_mode: Literal["keyword", "vector", "hybrid"]
    top_k: int = Field(ge=1, le=50)
    expected_source_keys: list[NonEmptyStr] = Field(min_length=1)
    expected_source: NonEmptyStr
    expected_citation_required: bool
    expected_member_id: str | None = None
    stale_source_must_be_rejected: bool


class SafetyGoldCase(BenchmarkCaseMetadata):
    user_input: NonEmptyStr
    member_id: NonEmptyStr
    expected_decision: NonEmptyStr
    expected_safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    expected_human_confirmation_required: bool
    must_include: list[NonEmptyStr] = Field(default_factory=list)
    forbidden_phrases: list[NonEmptyStr] = Field(default_factory=list)


class MemoryTurn(ContractModel):
    turn_id: NonEmptyStr
    text: NonEmptyStr
    confirmed: bool
    fact_id: str | None = None
    member_id: NonEmptyStr | None = None


class MemoryContextCase(BenchmarkCaseMetadata):
    task_id: NonEmptyStr
    member_id: NonEmptyStr
    previous_member_id: NonEmptyStr | None = None
    turns: list[MemoryTurn] = Field(min_length=1)
    expected_retained_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    expected_dropped_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    expected_source_keys: list[NonEmptyStr] = Field(default_factory=list)
    expected_memory_write_ids: list[NonEmptyStr] = Field(default_factory=list)
    expected_checkpoint_source: NonEmptyStr
    fault: str | None = None


class ProviderFaultCase(BenchmarkCaseMetadata):
    provider_name: NonEmptyStr
    operation: NonEmptyStr
    member_id: NonEmptyStr
    read_only: bool
    injected_fault: NonEmptyStr
    expected_retryable: bool
    expected_max_attempts: int = Field(ge=1, le=5)
    expected_output_state: NonEmptyStr
    expected_source_present: bool
    expected_external_action_status: NonEmptyStr
    expected_write_retry_count: int = Field(ge=0)


CaseT = TypeVar("CaseT")


class BenchmarkDataset(ContractModel, Generic[CaseT]):
    dataset_id: NonEmptyStr
    dataset_version: NonEmptyStr
    status: Literal["gold"]
    human_reviewed: Literal[True]
    source_of_truth: NonEmptyStr
    cases: list[CaseT] = Field(min_length=1)
    reviewed_at: datetime
    frozen_at: datetime


class ManifestDatasetEntry(ContractModel):
    dataset_id: NonEmptyStr
    case_count: int = Field(ge=1)
    human_reviewed: Literal[True]
    sha256: str = Field(min_length=64, max_length=64)


class BenchmarkManifest(ContractModel):
    manifest_id: NonEmptyStr
    dataset_version: NonEmptyStr
    status: Literal["frozen"]
    human_reviewed: Literal[True]
    generated_by_ai: bool
    hashes_frozen: Literal[True]
    knowledge_version: NonEmptyStr
    model_config_name: str | None = None
    pricing_version: str | None = None
    datasets: dict[NonEmptyStr, ManifestDatasetEntry]
    review_action: NonEmptyStr
    frozen_at: datetime


class BenchmarkMetric(ContractModel):
    name: NonEmptyStr
    value: float | None = Field(default=None, ge=0.0)
    status: MetricStatus
    metric_type: MetricType
    sample_count: int = Field(ge=0)
    unit: NonEmptyStr
    notes: NonEmptyStr


class BenchmarkDatasetReport(ContractModel):
    dataset_id: NonEmptyStr
    case_count: int = Field(ge=0)
    contract_valid: bool
    category_counts: dict[NonEmptyStr, int]
    bad_case_ids: list[NonEmptyStr] = Field(default_factory=list)


class BenchmarkReport(ContractModel):
    report_version: NonEmptyStr
    manifest_id: NonEmptyStr
    manifest_sha256: str = Field(min_length=64, max_length=64)
    run_id: NonEmptyStr
    generated_at: datetime
    mode: BenchmarkMode
    status: BenchmarkRunStatus
    datasets: list[BenchmarkDatasetReport]
    metrics: list[BenchmarkMetric]
    bad_cases: list[NonEmptyStr] = Field(default_factory=list)
    environment: dict[NonEmptyStr, str] = Field(default_factory=dict)
    notes: list[NonEmptyStr] = Field(default_factory=list)


__all__ = [
    "AnswerQualityCase",
    "BenchmarkCaseMetadata",
    "BenchmarkDataset",
    "BenchmarkDatasetReport",
    "BenchmarkManifest",
    "BenchmarkMetric",
    "BenchmarkMode",
    "BenchmarkReport",
    "MemoryContextCase",
    "MemoryTurn",
    "ProviderFaultCase",
    "RAGGoldCase",
    "SafetyGoldCase",
]

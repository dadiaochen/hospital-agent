"""Preparation contracts for the final v2 evaluation gate.

The v2 benchmark is synthetic, but its labels still need a human review
before real integration metrics can be called final.  This module creates
two local-only artifacts:

* a review queue containing the frozen WorldState/Query expectations; and
* a case-scoped identity/source map template for the disposable demo data.

It does not call a model, database, Provider or RAG service.  The generated
files belong under ``var/`` and must never be committed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_benchmark_schemas import (
    DatasetSplit,
    EvalDependencyEdge,
    EvalWorldState,
)


ReviewDecision = Literal["pending", "pass", "fail"]
FinalGateReviewStatus = Literal["pending_review", "human_reviewed"]

WORLD_REVIEW_FIELDS = frozenset(
    {
        "world_members",
        "world_sources",
        "gold_domain_plan",
        "gold_governance_plan",
        "gold_safety",
        "gold_confirmation",
        "gold_claims",
    }
)
QUERY_REVIEW_FIELDS = frozenset(
    {
        "user_input",
        "member_scope",
        "intent_and_route",
        "domain_plan",
        "governance_plan",
        "tools_and_sources",
        "safety_and_confirmation",
        "claims_and_forbidden_phrases",
    }
)


class WorldReviewItem(ContractModel):
    """Reviewable WorldState expectations without runtime output."""

    world_state_id: NonEmptyStr
    base_case_id: NonEmptyStr
    dataset_split: DatasetSplit
    category: NonEmptyStr
    member_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_member_id: NonEmptyStr
    expected_intent: NonEmptyStr
    expected_route: NonEmptyStr
    expected_domain_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)
    expected_domain_dependency_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_governance_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)
    expected_governance_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_required_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_supporting_source_ids: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple
    )
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_confirmation_required: bool
    expected_final_status: NonEmptyStr
    required_claim_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    decision: ReviewDecision = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    checked_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    notes: str = ""

    @model_validator(mode="after")
    def validate_review_metadata(self) -> "WorldReviewItem":
        if self.expected_member_id not in self.member_ids:
            raise ValueError("WorldState review member must belong to the world")
        if not set(self.expected_supporting_source_ids).issubset(self.source_ids):
            raise ValueError("WorldState review sources must belong to the world")
        if self.decision == "pass":
            missing = WORLD_REVIEW_FIELDS - set(self.checked_fields)
            if missing:
                raise ValueError(
                    "passed WorldState review is missing fields: "
                    + ", ".join(sorted(missing))
                )
            if not self.reviewer or self.reviewed_at is None:
                raise ValueError("passed WorldState review needs reviewer and timestamp")
        if self.decision == "fail" and not self.notes.strip():
            raise ValueError("failed WorldState review needs notes")
        return self


class QueryReviewItem(ContractModel):
    """Reviewable Query variant expectations and safety labels."""

    query_id: NonEmptyStr
    world_state_id: NonEmptyStr
    base_case_id: NonEmptyStr
    dataset_split: DatasetSplit
    variant_index: int = Field(ge=1, le=4)
    variant_type: NonEmptyStr
    user_input: NonEmptyStr
    expected_member_id: NonEmptyStr
    expected_intent: NonEmptyStr
    expected_route: NonEmptyStr
    expected_agent_roles: tuple[NonEmptyStr, ...] = Field(min_length=1)
    expected_domain_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)
    expected_domain_dependency_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_governance_steps: tuple[NonEmptyStr, ...] = Field(min_length=1)
    expected_governance_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_required_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_sources: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_human_confirmation_required: bool
    expected_blocked: bool
    expected_final_status: NonEmptyStr
    required_claim_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    forbidden_phrases: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    decision: ReviewDecision = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    checked_fields: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    notes: str = ""

    @model_validator(mode="after")
    def validate_review_metadata(self) -> "QueryReviewItem":
        if self.decision == "pass":
            missing = QUERY_REVIEW_FIELDS - set(self.checked_fields)
            if missing:
                raise ValueError(
                    "passed Query review is missing fields: "
                    + ", ".join(sorted(missing))
                )
            if not self.reviewer or self.reviewed_at is None:
                raise ValueError("passed Query review needs reviewer and timestamp")
        if self.decision == "fail" and not self.notes.strip():
            raise ValueError("failed Query review needs notes")
        return self


class FinalGateReviewQueue(ContractModel):
    """The human-review input for the complete 300/1200 benchmark."""

    schema_version: Literal["4d-final-review-v1"] = "4d-final-review-v1"
    dataset_version: Literal["4d-b5.5"] = "4d-b5.5"
    generated_at: datetime
    world_states_sha256: str = Field(min_length=64, max_length=64)
    queries_sha256: str = Field(min_length=64, max_length=64)
    world_reviews: list[WorldReviewItem] = Field(min_length=300, max_length=300)
    query_reviews: list[QueryReviewItem] = Field(min_length=1200, max_length=1200)
    review_status: FinalGateReviewStatus = "pending_review"

    @model_validator(mode="after")
    def validate_join_and_status(self) -> "FinalGateReviewQueue":
        world_ids = {item.world_state_id for item in self.world_reviews}
        if len(world_ids) != 300:
            raise ValueError("review queue must contain 300 unique WorldStates")
        query_ids = {item.query_id for item in self.query_reviews}
        if len(query_ids) != 1200:
            raise ValueError("review queue must contain 1200 unique Queries")
        if any(item.world_state_id not in world_ids for item in self.query_reviews):
            raise ValueError("every Query review must reference a known WorldState")
        if self.review_status == "human_reviewed" and any(
            item.decision == "pending"
            for item in (*self.world_reviews, *self.query_reviews)
        ):
            raise ValueError("human_reviewed queue cannot contain pending items")
        return self


class SourceIdentityTemplate(ContractModel):
    """A benchmark source slot used by the local identity-map worksheet.

    Provider and RAG sources are created inside the case-scoped shadow run.
    They remain visible in the worksheet for review, but they do not need a
    fabricated database ID.  Database-backed sources still require an
    explicit local mapping before integration can run.
    """

    benchmark_source_id: NonEmptyStr
    source_kind: Literal["database", "provider", "rag"] = "database"
    requires_actual_mapping: bool = True
    actual_source_id: str = ""


class CaseIdentityTemplate(ContractModel):
    """Identity inputs for one synthetic WorldState namespace."""

    benchmark_user_id: NonEmptyStr
    actual_user_id: str = ""
    member_ids: dict[NonEmptyStr, str] = Field(min_length=1)
    source_mappings: list[SourceIdentityTemplate] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_source_templates(self) -> "CaseIdentityTemplate":
        source_ids = [item.benchmark_source_id for item in self.source_mappings]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source identity templates must be unique")
        return self


class IdentityMapTemplate(ContractModel):
    """Local-only, case-scoped map template; empty values are intentional."""

    schema_version: Literal["4d-final-identity-map-v1"] = (
        "4d-final-identity-map-v1"
    )
    benchmark_dataset_version: Literal["4d-b5.5"] = "4d-b5.5"
    generated_at: datetime
    cases: dict[NonEmptyStr, CaseIdentityTemplate] = Field(
        min_length=300, max_length=300
    )

    @model_validator(mode="after")
    def validate_case_keys_and_empty_actuals(self) -> "IdentityMapTemplate":
        if len(self.cases) != 300:
            raise ValueError("identity template must contain 300 WorldStates")
        for world_state_id, case in self.cases.items():
            if case.actual_user_id:
                raise ValueError(
                    f"identity template must not contain actual user ID: {world_state_id}"
                )
            if any(case.member_ids.values()):
                raise ValueError(
                    f"identity template must not contain actual member IDs: {world_state_id}"
                )
            if any(item.actual_source_id for item in case.source_mappings):
                raise ValueError(
                    f"identity template must not contain actual source IDs: {world_state_id}"
                )
        return self


def _world_source_ids(world: EvalWorldState) -> tuple[str, ...]:
    values = [
        *(member.profile_source_id for member in world.members),
        *(item.source_id for item in world.prescriptions),
        *(item.source_id for item in world.medicine_box),
        *(item.source_id for item in world.health_records),
        *world.provider_state.source_ids,
        *world.knowledge_state.current_source_ids,
        *world.knowledge_state.stale_source_ids,
    ]
    return tuple(dict.fromkeys(values))


def _source_template(source_id: str) -> SourceIdentityTemplate:
    """Describe how a source is resolved during a real integration run."""

    if ":source:provider" in source_id:
        return SourceIdentityTemplate(
            benchmark_source_id=source_id,
            source_kind="provider",
            requires_actual_mapping=False,
        )
    if ":source:rag:" in source_id:
        return SourceIdentityTemplate(
            benchmark_source_id=source_id,
            source_kind="rag",
            requires_actual_mapping=False,
        )
    return SourceIdentityTemplate(
        benchmark_source_id=source_id,
        source_kind="database",
        requires_actual_mapping=True,
    )


def build_review_queue(
    *,
    worlds,
    queries,
    manifest,
    generated_at: datetime | None = None,
) -> FinalGateReviewQueue:
    """Project the frozen benchmark into human-editable review records."""

    world_by_id = {world.world_state_id: world for world in worlds.world_states}
    timestamp = generated_at or datetime.now(timezone.utc)
    world_reviews: list[WorldReviewItem] = []
    for world in worlds.world_states:
        gold = world.gold
        world_reviews.append(
            WorldReviewItem(
                world_state_id=world.world_state_id,
                base_case_id=world.base_case_id,
                dataset_split=world.dataset_split,
                category=world.category,
                member_ids=tuple(member.member_id for member in world.members),
                source_ids=_world_source_ids(world),
                expected_member_id=gold.expected_member_id,
                expected_intent=gold.expected_intent,
                expected_route=gold.expected_route,
                expected_domain_steps=gold.expected_domain_steps,
                expected_domain_dependency_edges=gold.expected_domain_dependency_edges,
                expected_governance_steps=gold.expected_governance_steps,
                expected_governance_edges=gold.expected_governance_edges,
                expected_required_tools=gold.expected_tool_calls,
                expected_supporting_source_ids=gold.supporting_source_ids,
                expected_safety_flags=gold.expected_safety_flags,
                expected_confirmation_required=gold.expected_confirmation_required,
                expected_final_status=gold.expected_final_status,
                required_claim_ids=tuple(
                    claim.claim_id for claim in gold.required_claims
                ),
            )
        )

    query_reviews: list[QueryReviewItem] = []
    for query in queries.queries:
        if query.world_state_id not in world_by_id:
            raise ValueError(f"query references unknown world: {query.query_id}")
        query_reviews.append(
            QueryReviewItem(
                query_id=query.query_id,
                world_state_id=query.world_state_id,
                base_case_id=query.base_case_id,
                dataset_split=query.dataset_split,
                variant_index=query.variant_index,
                variant_type=query.variant_type,
                user_input=query.user_input,
                expected_member_id=query.expected_member_id,
                expected_intent=query.expected_intent,
                expected_route=query.expected_route,
                expected_agent_roles=query.expected_agent_roles,
                expected_domain_steps=query.expected_domain_steps,
                expected_domain_dependency_edges=query.expected_domain_dependency_edges,
                expected_governance_steps=query.expected_governance_steps,
                expected_governance_edges=query.expected_governance_edges,
                expected_required_tools=query.expected_required_tools,
                expected_safety_flags=query.expected_safety_flags,
                expected_sources=query.expected_sources,
                expected_human_confirmation_required=(
                    query.expected_human_confirmation_required
                ),
                expected_blocked=query.expected_blocked,
                expected_final_status=query.expected_final_status,
                required_claim_ids=query.required_claim_ids,
                forbidden_phrases=query.forbidden_phrases,
            )
        )

    return FinalGateReviewQueue(
        generated_at=timestamp,
        world_states_sha256=manifest.world_states_sha256,
        queries_sha256=manifest.queries_sha256,
        world_reviews=world_reviews,
        query_reviews=query_reviews,
    )


def build_identity_map_template(
    *, worlds, generated_at: datetime | None = None
) -> IdentityMapTemplate:
    """Create empty case-scoped slots without inventing local IDs."""

    cases: dict[str, CaseIdentityTemplate] = {}
    for world in worlds.world_states:
        cases[world.world_state_id] = CaseIdentityTemplate(
            benchmark_user_id=world.user.user_id,
            member_ids={member.member_id: "" for member in world.members},
            source_mappings=[
                _source_template(source_id)
                for source_id in _world_source_ids(world)
            ],
        )
    return IdentityMapTemplate(
        generated_at=generated_at or datetime.now(timezone.utc),
        cases=cases,
    )


def prepare_final_gate_artifacts(
    *, project_root: Path | None = None, output_dir: Path | None = None
) -> tuple[Path, Path]:
    """Load frozen v2 files and write ignored local review templates."""

    root = project_root or Path(__file__).resolve().parents[3]
    target = output_dir or root / "var" / "demo"
    target.mkdir(parents=True, exist_ok=True)
    worlds, queries, manifest = load_v2_benchmark(project_root=root)
    timestamp = datetime.now(timezone.utc)
    review_queue = build_review_queue(
        worlds=worlds,
        queries=queries,
        manifest=manifest,
        generated_at=timestamp,
    )
    identity_template = build_identity_map_template(
        worlds=worlds,
        generated_at=timestamp,
    )
    review_path = target / "v2_review_queue.local.json"
    identity_path = target / "v2_identity_map.template.local.json"
    review_path.write_text(
        json.dumps(review_queue.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    identity_path.write_text(
        json.dumps(
            identity_template.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return review_path, identity_path


__all__ = [
    "CaseIdentityTemplate",
    "FinalGateReviewQueue",
    "IdentityMapTemplate",
    "QueryReviewItem",
    "SourceIdentityTemplate",
    "WorldReviewItem",
    "build_identity_map_template",
    "build_review_queue",
    "prepare_final_gate_artifacts",
]

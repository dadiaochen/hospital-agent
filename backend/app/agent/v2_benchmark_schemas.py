"""Contracts for the 4D-B2.4 WorldState and Query benchmark.

The v2 benchmark is deliberately separate from the frozen 4D-A gold files.
It describes synthetic, reproducible evaluation worlds.  It is suitable for
runner development and leakage checks, but it is not a clinical gold set
until the generated safety, source and routing labels are reviewed by a
human.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr
from app.agent.final_claim_schemas import FinalClaim


DatasetSplit = Literal["development", "validation", "holdout"]
WorldCategory = Literal[
    "triage",
    "medication",
    "report",
    "cross_domain",
    "resilience",
]
QueryVariant = Literal["direct", "colloquial", "omitted", "adversarial"]
WorldStatus = Literal["generated"]
ReviewStatus = Literal["pending_review"]
FaultType = Literal[
    "none",
    "timeout",
    "stale_source",
    "cross_member",
    "confirmation_race",
    "no_source",
]
ExpectedRoute = Literal["simple_single_domain", "complex_cross_domain"]
ExpectedFinalStatus = Literal["completed", "needs_confirmation", "blocked", "failed"]


class EvalUserState(ContractModel):
    """Synthetic user identity used only to join a benchmark world."""

    user_id: NonEmptyStr
    household_id: NonEmptyStr
    locale: NonEmptyStr = "zh-CN"


class EvalMemberState(ContractModel):
    """Synthetic member facts; no real patient identifiers are stored."""

    member_id: NonEmptyStr
    relationship: NonEmptyStr
    age_band: NonEmptyStr
    condition_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    profile_source_id: NonEmptyStr


class EvalPrescriptionState(ContractModel):
    prescription_id: NonEmptyStr
    member_id: NonEmptyStr
    medication_code: NonEmptyStr
    valid: bool
    doctor_confirmed: bool
    source_id: NonEmptyStr


class EvalMedicineBoxState(ContractModel):
    item_id: NonEmptyStr
    member_id: NonEmptyStr
    medication_code: NonEmptyStr
    remaining_days: int = Field(ge=0, le=3650)
    source_id: NonEmptyStr


class EvalHealthRecordState(ContractModel):
    record_id: NonEmptyStr
    member_id: NonEmptyStr
    record_type: NonEmptyStr
    available: bool
    source_id: NonEmptyStr


class EvalProviderState(ContractModel):
    """Mock Provider state consumed later by the WorldState materializer."""

    mode: Literal["mock", "sandbox"] = "mock"
    hospital_available: bool = True
    pharmacy_available: bool = True
    notification_available: bool = True
    source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class EvalKnowledgeState(ContractModel):
    namespace: NonEmptyStr = "medical-knowledge-v2"
    version: NonEmptyStr
    current_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    stale_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class EvalFaultInjection(ContractModel):
    enabled: bool
    fault_type: FaultType
    target: NonEmptyStr
    retryable: bool
    expected_fallback: NonEmptyStr

    @model_validator(mode="after")
    def validate_disabled_fault(self) -> "EvalFaultInjection":
        if not self.enabled and self.fault_type != "none":
            raise ValueError("disabled fault injections must use fault_type=none")
        if self.enabled and self.fault_type == "none":
            raise ValueError("enabled fault injections need a concrete fault_type")
        return self


class EvalDependencyEdge(ContractModel):
    upstream_step_id: NonEmptyStr
    downstream_step_id: NonEmptyStr

    @model_validator(mode="after")
    def reject_self_edge(self) -> "EvalDependencyEdge":
        if self.upstream_step_id == self.downstream_step_id:
            raise ValueError("WorldState dependency edges cannot point to themselves")
        return self


class EvalGoldExpectation(ContractModel):
    """Expected behavior derived from the synthetic world, not from an LLM."""

    expected_member_id: NonEmptyStr
    expected_intent: Intent
    expected_route: ExpectedRoute
    expected_agent_roles: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    # Business execution is the only graph that the Planner/Supervisor owns.
    expected_domain_steps: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    expected_domain_dependency_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    # Governance is projected separately because Safety/Confirmation/FinalAnswer
    # and Evaluator are fixed graph edges, not Supervisor candidates.
    expected_governance_steps: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=4
    )
    expected_governance_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_tool_calls: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    required_claims: tuple[FinalClaim, ...] = Field(default_factory=tuple)
    forbidden_claims: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    supporting_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_blocked: bool
    expected_confirmation_required: bool
    expected_final_status: ExpectedFinalStatus
    expected_database_changes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_status_rules(self) -> "EvalGoldExpectation":
        domain_steps = set(self.expected_domain_steps)
        governance_steps = set(self.expected_governance_steps)
        if domain_steps & governance_steps:
            raise ValueError("domain and governance steps must be disjoint")

        domain_edges = {
            (edge.upstream_step_id, edge.downstream_step_id)
            for edge in self.expected_domain_dependency_edges
        }
        if len(domain_edges) != len(self.expected_domain_dependency_edges):
            raise ValueError("domain dependency edges must be unique")
        if any(
            edge.upstream_step_id not in domain_steps
            or edge.downstream_step_id not in domain_steps
            for edge in self.expected_domain_dependency_edges
        ):
            raise ValueError("domain dependency edges must reference domain steps")

        governance_edges = {
            (edge.upstream_step_id, edge.downstream_step_id)
            for edge in self.expected_governance_edges
        }
        if len(governance_edges) != len(self.expected_governance_edges):
            raise ValueError("governance edges must be unique")
        if any(
            edge.upstream_step_id not in domain_steps | governance_steps
            or edge.downstream_step_id not in domain_steps | governance_steps
            for edge in self.expected_governance_edges
        ):
            raise ValueError("governance edges must reference known steps")

        if self.expected_blocked and self.expected_final_status != "blocked":
            raise ValueError("blocked gold must use final_status=blocked")
        if self.expected_confirmation_required and not (
            self.expected_final_status in {"needs_confirmation", "blocked"}
        ):
            raise ValueError(
                "confirmation-required gold must wait for confirmation or be blocked"
            )
        if self.expected_route == "simple_single_domain" and len(self.expected_agent_roles) != 1:
            raise ValueError("simple gold must contain one agent role")
        if self.expected_route == "complex_cross_domain" and len(self.expected_agent_roles) < 2:
            raise ValueError("complex gold must contain multiple agent roles")
        return self


class EvalWorldState(ContractModel):
    world_state_id: NonEmptyStr
    base_case_id: NonEmptyStr
    dataset_split: DatasetSplit
    category: WorldCategory
    tags: tuple[NonEmptyStr, ...] = Field(min_length=1)
    frozen_now: datetime
    seed: int = Field(ge=0)
    user: EvalUserState
    members: tuple[EvalMemberState, ...] = Field(min_length=1, max_length=3)
    prescriptions: tuple[EvalPrescriptionState, ...] = Field(default_factory=tuple)
    medicine_box: tuple[EvalMedicineBoxState, ...] = Field(default_factory=tuple)
    health_records: tuple[EvalHealthRecordState, ...] = Field(default_factory=tuple)
    provider_state: EvalProviderState
    knowledge_state: EvalKnowledgeState
    fault_injection: EvalFaultInjection
    gold: EvalGoldExpectation

    @model_validator(mode="after")
    def validate_member_and_source_scope(self) -> "EvalWorldState":
        member_ids = [member.member_id for member in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("WorldState member_id values must be unique")
        member_set = set(member_ids)
        scoped_member_ids = [
            *(item.member_id for item in self.prescriptions),
            *(item.member_id for item in self.medicine_box),
            *(item.member_id for item in self.health_records),
        ]
        if any(member_id not in member_set for member_id in scoped_member_ids):
            raise ValueError("all WorldState records must reference a world member")
        if self.gold.expected_member_id not in member_set:
            raise ValueError("gold expected_member_id must reference a world member")

        source_ids = {
            *(member.profile_source_id for member in self.members),
            *(item.source_id for item in self.prescriptions),
            *(item.source_id for item in self.medicine_box),
            *(item.source_id for item in self.health_records),
            *self.provider_state.source_ids,
            *self.knowledge_state.current_source_ids,
            *self.knowledge_state.stale_source_ids,
        }
        if not set(self.gold.supporting_source_ids).issubset(source_ids):
            raise ValueError("gold supporting_source_ids must exist in the WorldState")
        source_owners = {
            member.profile_source_id: member.member_id for member in self.members
        }
        source_owners.update(
            {
                item.source_id: item.member_id
                for item in (
                    *self.prescriptions,
                    *self.medicine_box,
                    *self.health_records,
                )
            }
        )
        for source_id in self.gold.supporting_source_ids:
            owner = source_owners.get(source_id)
            if owner is not None and owner != self.gold.expected_member_id:
                raise ValueError(
                    "gold supporting sources must stay within expected member scope"
                )
        for claim in self.gold.required_claims:
            if claim.subject_id != self.gold.expected_member_id:
                raise ValueError("required Claim must use the expected member")
            if not set(claim.source_ids).issubset(source_ids):
                raise ValueError("required Claim source_ids must exist in the WorldState")
            if any(
                source_owners.get(source_id) not in {None, self.gold.expected_member_id}
                for source_id in claim.source_ids
            ):
                raise ValueError("required Claim sources must stay within member scope")
        return self


class EvalQueryVariant(ContractModel):
    query_id: NonEmptyStr
    world_state_id: NonEmptyStr
    base_case_id: NonEmptyStr
    dataset_split: DatasetSplit
    category: WorldCategory
    variant_index: int = Field(ge=1, le=4)
    variant_type: QueryVariant
    user_input: NonEmptyStr
    expected_member_id: NonEmptyStr
    expected_intent: Intent
    expected_route: ExpectedRoute
    expected_agent_roles: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    expected_domain_steps: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=3)
    expected_domain_dependency_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_governance_steps: tuple[NonEmptyStr, ...] = Field(
        min_length=1, max_length=4
    )
    expected_governance_edges: tuple[EvalDependencyEdge, ...] = Field(
        default_factory=tuple
    )
    expected_required_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_sources: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_human_confirmation_required: bool
    expected_blocked: bool
    expected_final_status: ExpectedFinalStatus
    required_claim_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    forbidden_phrases: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class V2WorldStateDataset(ContractModel):
    dataset_id: Literal["world_states_v2"] = "world_states_v2"
    dataset_version: Literal["4d-b5.5"] = "4d-b5.5"
    status: WorldStatus = "generated"
    generated_by: Literal["deterministic_rule_generator"] = (
        "deterministic_rule_generator"
    )
    human_reviewed: Literal[False] = False
    review_status: ReviewStatus = "pending_review"
    generator_seed: int = Field(ge=0)
    frozen_now: datetime
    world_states: list[EvalWorldState] = Field(min_length=300, max_length=300)

    @model_validator(mode="after")
    def validate_distribution(self) -> "V2WorldStateDataset":
        split_counts = {
            split: sum(world.dataset_split == split for world in self.world_states)
            for split in ("development", "validation", "holdout")
        }
        if split_counts != {"development": 180, "validation": 60, "holdout": 60}:
            raise ValueError(f"invalid WorldState split counts: {split_counts}")
        category_counts = {
            category: sum(world.category == category for world in self.world_states)
            for category in ("triage", "medication", "report", "cross_domain", "resilience")
        }
        expected = {
            "triage": 70,
            "medication": 85,
            "report": 55,
            "cross_domain": 50,
            "resilience": 40,
        }
        if category_counts != expected:
            raise ValueError(f"invalid WorldState category counts: {category_counts}")
        return self


class V2QueryDataset(ContractModel):
    dataset_id: Literal["query_variants_v2"] = "query_variants_v2"
    dataset_version: Literal["4d-b5.5"] = "4d-b5.5"
    status: WorldStatus = "generated"
    generated_by: Literal["deterministic_rule_generator"] = (
        "deterministic_rule_generator"
    )
    human_reviewed: Literal[False] = False
    review_status: ReviewStatus = "pending_review"
    generator_seed: int = Field(ge=0)
    frozen_now: datetime
    queries: list[EvalQueryVariant] = Field(min_length=1200, max_length=1200)

    @model_validator(mode="after")
    def validate_distribution(self) -> "V2QueryDataset":
        split_counts = {
            split: sum(query.dataset_split == split for query in self.queries)
            for split in ("development", "validation", "holdout")
        }
        if split_counts != {"development": 720, "validation": 240, "holdout": 240}:
            raise ValueError(f"invalid Query split counts: {split_counts}")
        by_world: dict[str, list[EvalQueryVariant]] = {}
        for query in self.queries:
            by_world.setdefault(query.world_state_id, []).append(query)
        if len(by_world) != 300 or any(len(items) != 4 for items in by_world.values()):
            raise ValueError("each of 300 WorldStates must have exactly four queries")
        if any(
            {item.variant_index for item in items} != {1, 2, 3, 4}
            for items in by_world.values()
        ):
            raise ValueError("each WorldState must have variant indexes 1 through 4")
        return self


class V2BenchmarkManifest(ContractModel):
    manifest_id: Literal["agent-harness-v2"] = "agent-harness-v2"
    dataset_version: Literal["4d-b5.5"] = "4d-b5.5"
    status: WorldStatus = "generated"
    generated_by: Literal["deterministic_rule_generator"] = (
        "deterministic_rule_generator"
    )
    human_reviewed: Literal[False] = False
    review_status: ReviewStatus = "pending_review"
    generator_seed: int = Field(ge=0)
    frozen_now: datetime
    world_state_count: Literal[300] = 300
    query_count: Literal[1200] = 1200
    world_states_sha256: str = Field(min_length=64, max_length=64)
    queries_sha256: str = Field(min_length=64, max_length=64)


__all__ = [
    "DatasetSplit",
    "EvalDependencyEdge",
    "EvalFaultInjection",
    "EvalGoldExpectation",
    "EvalHealthRecordState",
    "EvalKnowledgeState",
    "EvalMedicineBoxState",
    "EvalMemberState",
    "EvalPrescriptionState",
    "EvalProviderState",
    "EvalQueryVariant",
    "EvalUserState",
    "EvalWorldState",
    "ExpectedFinalStatus",
    "FaultType",
    "QueryVariant",
    "V2BenchmarkManifest",
    "V2QueryDataset",
    "V2WorldStateDataset",
    "WorldCategory",
]

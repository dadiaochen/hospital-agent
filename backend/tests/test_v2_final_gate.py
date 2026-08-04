from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_final_gate import (
    FinalGateReviewQueue,
    build_identity_map_template,
    build_review_queue,
)
from app.agent.v2_integration import IntegrationExecutionError, IntegrationIdentityMap


ROOT = Path(__file__).resolve().parents[2]
FIXED_REVIEW_TIME = datetime(2026, 8, 3, tzinfo=timezone.utc)


def test_final_gate_queue_projects_all_worlds_and_queries() -> None:
    worlds, queries, manifest = load_v2_benchmark(project_root=ROOT)

    queue = build_review_queue(
        worlds=worlds,
        queries=queries,
        manifest=manifest,
        generated_at=FIXED_REVIEW_TIME,
    )

    assert isinstance(queue, FinalGateReviewQueue)
    assert len(queue.world_reviews) == 300
    assert len(queue.query_reviews) == 1200
    assert queue.review_status == "pending_review"
    assert all(item.decision == "pending" for item in queue.query_reviews)
    assert all(item.world_state_id in {
        world.world_state_id for world in worlds.world_states
    } for item in queue.query_reviews)


def test_identity_template_covers_every_world_member_and_source_without_actual_ids() -> None:
    worlds, _queries, _manifest = load_v2_benchmark(project_root=ROOT)

    template = build_identity_map_template(
        worlds=worlds,
        generated_at=FIXED_REVIEW_TIME,
    )

    assert len(template.cases) == 300
    for world in worlds.world_states:
        case = template.cases[world.world_state_id]
        assert set(case.member_ids) == {member.member_id for member in world.members}
        assert all(value == "" for value in case.member_ids.values())
        expected_sources = {
            *(member.profile_source_id for member in world.members),
            *(item.source_id for item in world.prescriptions),
            *(item.source_id for item in world.medicine_box),
            *(item.source_id for item in world.health_records),
            *world.provider_state.source_ids,
            *world.knowledge_state.current_source_ids,
            *world.knowledge_state.stale_source_ids,
        }
        assert {
            item.benchmark_source_id for item in case.source_mappings
        } == expected_sources
        assert all(item.actual_source_id == "" for item in case.source_mappings)


def test_identity_template_marks_provider_and_rag_as_runtime_owned_sources() -> None:
    worlds, _queries, _manifest = load_v2_benchmark(project_root=ROOT)

    template = build_identity_map_template(
        worlds=worlds,
        generated_at=FIXED_REVIEW_TIME,
    )
    case = template.cases["world-v2-0001"]
    by_source = {item.benchmark_source_id: item for item in case.source_mappings}

    assert by_source["world-v2-0001:source:provider"].requires_actual_mapping is False
    assert by_source["world-v2-0001:source:provider"].source_kind == "provider"
    assert by_source["world-v2-0001:source:rag:current"].requires_actual_mapping is False
    assert by_source["world-v2-0001:source:rag:current"].source_kind == "rag"
    assert by_source["world-v2-0001:source:profile-primary"].requires_actual_mapping


def test_identity_loader_accepts_empty_runtime_owned_source_slots() -> None:
    identity = IntegrationIdentityMap.from_payload(
        {
            "cases": {
                "world-1": {
                    "benchmark_user_id": "benchmark-user-1",
                    "actual_user_id": "actual-user-1",
                    "member_ids": {"member-1": "actual-member-1"},
                    "source_mappings": [
                        {
                            "benchmark_source_id": "source:provider",
                            "source_kind": "provider",
                            "requires_actual_mapping": False,
                            "actual_source_id": "",
                        },
                        {
                            "benchmark_source_id": "source:profile",
                            "source_kind": "database",
                            "requires_actual_mapping": True,
                            "actual_source_id": "health_profile:1",
                        },
                    ],
                }
            }
        }
    )

    assert identity.map_source("health_profile:1", world_state_id="world-1") == (
        "source:profile"
    )


def test_case_scoped_identity_map_isolated_and_fail_closed() -> None:
    identity = IntegrationIdentityMap.from_payload(
        {
            "schema_version": "4d-final-identity-map-v1",
            "cases": {
                "world-1": {
                    "benchmark_user_id": "benchmark-user-1",
                    "actual_user_id": "actual-user-1",
                    "member_ids": {"member-1": "actual-member-1"},
                    "source_ids": {"actual-source-1": "source-1"},
                },
                "world-2": {
                    "benchmark_user_id": "benchmark-user-2",
                    "actual_user_id": "actual-user-2",
                    "member_ids": {"member-1": "actual-member-2"},
                    "source_ids": {"actual-source-2": "source-2"},
                },
            },
        }
    )

    assert identity.resolve_user_id("world-1") == "actual-user-1"
    assert identity.resolve_member("member-1", world_state_id="world-1") == (
        "actual-member-1"
    )
    assert identity.resolve_member("member-1", world_state_id="world-2") == (
        "actual-member-2"
    )
    assert identity.map_source("actual-source-2", world_state_id="world-2") == (
        "source-2"
    )
    with pytest.raises(IntegrationExecutionError, match="missing identity map case"):
        identity.resolve_member("member-1", world_state_id="world-3")
    with pytest.raises(IntegrationExecutionError, match="missing benchmark source mapping"):
        identity.map_source("actual-source-1", world_state_id="world-2")


def test_identity_loader_rejects_unfilled_template() -> None:
    with pytest.raises(ValueError, match="missing actual user mapping"):
        IntegrationIdentityMap.from_payload(
            {
                "cases": {
                    "world-1": {
                        "benchmark_user_id": "benchmark-user-1",
                        "actual_user_id": "",
                        "member_ids": {"member-1": ""},
                    }
                }
            }
        )

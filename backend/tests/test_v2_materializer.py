from pathlib import Path

import pytest

from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_materializer import (
    InMemoryProjectionBackend,
    MaterializationError,
    WorldStateMaterializer,
)


ROOT = Path(__file__).resolve().parents[2]


def _first_case():
    worlds, queries, _ = load_v2_benchmark(project_root=ROOT)
    world = worlds.world_states[0]
    query = next(item for item in queries.queries if item.world_state_id == world.world_state_id)
    return world, query


def test_materializer_creates_isolated_projection_and_cleans_it() -> None:
    backend = InMemoryProjectionBackend()
    materializer = WorldStateMaterializer(backend)
    world, query = _first_case()

    materialized = materializer.materialize(world, query)

    assert materialized.receipt.namespace in backend.active_namespaces
    assert materialized.receipt.member_ids == tuple(member.member_id for member in world.members)
    assert materialized.receipt.materialized_source_ids
    assert materialized.database_projection["members"]
    assert materialized.rag_projection["namespace"] == (world.knowledge_state.namespace,)

    receipt = materializer.cleanup(materialized)
    assert receipt.cleanup_succeeded is True
    assert backend.active_namespaces == ()
    assert materializer.cleanup(materialized).cleanup_succeeded is True


def test_materializer_rejects_query_from_another_world() -> None:
    world, query = _first_case()
    worlds, queries, _ = load_v2_benchmark(project_root=ROOT)
    other_query = next(
        item for item in queries.queries if item.world_state_id != world.world_state_id
    )

    with pytest.raises(MaterializationError, match="IDs do not match"):
        WorldStateMaterializer().materialize(world, other_query)


def test_no_source_fault_materializes_no_available_sources() -> None:
    worlds, queries, _ = load_v2_benchmark(project_root=ROOT)
    world = next(
        item for item in worlds.world_states if item.fault_injection.fault_type == "no_source"
    )
    query = next(item for item in queries.queries if item.world_state_id == world.world_state_id)

    materialized = WorldStateMaterializer().materialize(world, query)

    assert materialized.receipt.materialized_source_ids == ()

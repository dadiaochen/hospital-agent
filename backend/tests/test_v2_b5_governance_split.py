"""Minimum B5.5 tests for the domain DAG/governance graph split.

These tests intentionally reuse the checked-in v2 benchmark and the existing
synthetic runner.  They verify the contract boundary without changing the
benchmark data or production code.
"""

from pathlib import Path

import pytest

from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_benchmark_schemas import EvalGoldExpectation
from app.agent.v2_eval_runner import V2EvalRunner
from app.agent.v2_eval_schemas import V2RunnerOptions, V2RunArtifacts


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_fixture_data():
    worlds, queries, manifest = load_v2_benchmark(project_root=PROJECT_ROOT)
    world_by_id = {world.world_state_id: world for world in worlds.world_states}
    return worlds, queries, manifest, world_by_id


def test_v2_fixture_projection_matches_gold_for_all_cases() -> None:
    worlds, queries, manifest, world_by_id = _load_fixture_data()

    assert len(worlds.world_states) == manifest.world_state_count == 300
    assert len(queries.queries) == manifest.query_count == 1200

    for query in queries.queries:
        world = world_by_id[query.world_state_id]
        gold = world.gold

        assert query.expected_domain_steps == gold.expected_domain_steps
        assert (
            query.expected_domain_dependency_edges
            == gold.expected_domain_dependency_edges
        )
        assert query.expected_governance_steps == gold.expected_governance_steps
        assert (
            query.expected_governance_edges
            == gold.expected_governance_edges
        )


def test_safety_review_is_governance_only_and_edges_are_separate() -> None:
    worlds, queries, _, world_by_id = _load_fixture_data()

    assert any(
        world.gold.expected_governance_edges for world in worlds.world_states
    )
    for query in queries.queries:
        world = world_by_id[query.world_state_id]
        assert "safety-review" not in query.expected_domain_steps
        assert "safety-review" in query.expected_governance_steps
        assert all(
            edge.upstream_step_id != "safety-review"
            and edge.downstream_step_id != "safety-review"
            for edge in query.expected_domain_dependency_edges
        )


def test_synthetic_runner_plan_grade_and_dependency_result_scope() -> None:
    runner = V2EvalRunner(project_root=PROJECT_ROOT)
    report = runner.run(
        V2RunnerOptions(max_cases=1, allow_pending_review=True)
    )

    assert report.case_results[0].layer_grades[1].grader == "plan"
    assert report.case_results[0].layer_grades[1].passed is True

    _, queries, _, world_by_id = _load_fixture_data()
    query = queries.queries[0]
    world = world_by_id[query.world_state_id]
    materialized = runner.materializer.materialize(world, query)
    try:
        artifacts = runner.executor.execute(materialized, repeat_index=0)
    finally:
        runner.materializer.cleanup(materialized)

    expected_domain_steps = set(world.gold.expected_domain_steps)
    trace = artifacts.run_trace
    envelope = trace.final_answer.answer_envelope

    assert set(trace.dependency_result_ids) <= expected_domain_steps
    assert "safety-review" not in trace.dependency_result_ids
    assert envelope is not None
    assert set(envelope.dependency_result_ids) <= expected_domain_steps
    assert set(envelope.dependency_result_ids) == set(trace.dependency_result_ids)


def test_gold_rejects_governance_edge_in_domain_edges() -> None:
    worlds, _, _, _ = _load_fixture_data()
    world = next(
        item for item in worlds.world_states if item.gold.expected_governance_edges
    )
    payload = world.gold.model_dump(mode="python")
    payload["expected_domain_dependency_edges"] = list(
        world.gold.expected_domain_dependency_edges
    ) + [world.gold.expected_governance_edges[0].model_dump(mode="python")]

    with pytest.raises(
        ValueError, match="domain dependency edges must reference domain steps"
    ):
        EvalGoldExpectation.model_validate(payload)


def test_run_artifacts_reject_governance_edge_in_domain_edges() -> None:
    runner = V2EvalRunner(project_root=PROJECT_ROOT)
    worlds, queries, _, world_by_id = _load_fixture_data()
    world = next(
        item for item in worlds.world_states if item.gold.expected_governance_edges
    )
    query = next(
        item for item in queries.queries if item.world_state_id == world.world_state_id
    )
    materialized = runner.materializer.materialize(world, query)
    try:
        artifacts = runner.executor.execute(materialized, repeat_index=0)
    finally:
        runner.materializer.cleanup(materialized)

    payload = artifacts.model_dump(mode="python")
    payload["observed_domain_dependency_edges"] = [
        world.gold.expected_governance_edges[0].model_dump(mode="python")
    ]

    with pytest.raises(
        ValueError, match="observed domain dependency edges must reference domain steps"
    ):
        V2RunArtifacts.model_validate(payload)

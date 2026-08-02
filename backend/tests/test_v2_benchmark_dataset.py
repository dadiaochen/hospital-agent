import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from app.agent.v2_benchmark_generator import (
    V2BenchmarkDataError,
    V2BenchmarkGenerator,
    load_v2_benchmark,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_v2_fixture_has_exact_world_query_and_split_counts() -> None:
    worlds, queries, manifest = load_v2_benchmark(project_root=PROJECT_ROOT)

    assert len(worlds.world_states) == manifest.world_state_count == 300
    assert len(queries.queries) == manifest.query_count == 1200
    assert Counter(world.dataset_split for world in worlds.world_states) == {
        "development": 180,
        "validation": 60,
        "holdout": 60,
    }
    assert Counter(query.dataset_split for query in queries.queries) == {
        "development": 720,
        "validation": 240,
        "holdout": 240,
    }
    assert Counter(world.category for world in worlds.world_states) == {
        "triage": 70,
        "medication": 85,
        "report": 55,
        "cross_domain": 50,
        "resilience": 40,
    }


def test_each_world_has_four_same_split_variants_and_scoped_claims() -> None:
    worlds, queries, _ = load_v2_benchmark(project_root=PROJECT_ROOT)
    world_by_id = {world.world_state_id: world for world in worlds.world_states}
    queries_by_world: dict[str, list] = {}
    for query in queries.queries:
        queries_by_world.setdefault(query.world_state_id, []).append(query)

    assert set(queries_by_world) == set(world_by_id)
    for world_id, variants in queries_by_world.items():
        world = world_by_id[world_id]
        assert len(variants) == 4
        assert {variant.variant_index for variant in variants} == {1, 2, 3, 4}
        assert {variant.variant_type for variant in variants} == {
            "direct",
            "colloquial",
            "omitted",
            "adversarial",
        }
        assert {variant.dataset_split for variant in variants} == {
            world.dataset_split
        }
        assert {variant.base_case_id for variant in variants} == {world.base_case_id}
        assert all(
            variant.expected_member_id in {member.member_id for member in world.members}
            for variant in variants
        )
        assert all(
            claim.subject_id == world.gold.expected_member_id
            for claim in world.gold.required_claims
        )


def test_v2_generation_is_reproducible_and_pending_review() -> None:
    first_worlds, first_queries = V2BenchmarkGenerator(seed=20260801).generate()
    second_worlds, second_queries = V2BenchmarkGenerator(seed=20260801).generate()

    assert first_worlds.model_dump(mode="json") == second_worlds.model_dump(mode="json")
    assert first_queries.model_dump(mode="json") == second_queries.model_dump(mode="json")
    assert first_worlds.human_reviewed is False
    assert first_queries.human_reviewed is False
    assert first_worlds.review_status == "pending_review"
    assert first_queries.review_status == "pending_review"


def test_tampered_v2_dataset_hash_is_rejected(tmp_path: Path) -> None:
    source_dir = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "benchmarks" / "v2"
    target_dir = tmp_path / "backend" / "tests" / "fixtures" / "benchmarks" / "v2"
    target_dir.mkdir(parents=True)
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    manifest_path = target_dir / "benchmark_manifest.v2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["world_states_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(V2BenchmarkDataError, match="WorldState dataset hash mismatch"):
        load_v2_benchmark(project_root=tmp_path)

"""Load the single frozen Agent evaluation view from the unified dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.agent.v2_benchmark_generator import (
    V2BenchmarkDataError,
)
from app.agent.v2_benchmark_schemas import (
    EvalQueryVariant,
    EvalWorldState,
    V2BenchmarkManifest,
    V2QueryDataset,
    V2WorldStateDataset,
)


DATASET_VERSION = "internet-hospital-agent-eval-v1"
ACTIVE_AGENT_PROFILE = "fast-400"
ACTIVE_AGENT_WORLD_COUNT = 100
ACTIVE_AGENT_QUERY_COUNT = 400
ACTIVE_AGENT_SPLIT_COUNTS = {
    "development": (60, 240),
    "validation": (20, 80),
    "holdout": (20, 80),
}
DEFAULT_DATASET_ROOT = (
    Path(__file__).resolve().parents[3]
    / "output/benchmarks/evaluation_dataset"
    / DATASET_VERSION
)


def load_unified_agent_benchmark(
    *, project_root: Path | None = None,
) -> tuple[V2WorldStateDataset, V2QueryDataset, V2BenchmarkManifest]:
    """Validate hashes and adapt unified JSONL rows to existing runner contracts."""

    root = (
        project_root
        / "output/benchmarks/evaluation_dataset"
        / DATASET_VERSION
        if project_root is not None
        else DEFAULT_DATASET_ROOT
    )
    manifest_path = root / "manifest.json"
    world_path = root / "agent/world_states.jsonl"
    query_path = root / "agent/queries.jsonl"
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        world_rows = _read_jsonl(world_path)
        query_rows = _read_jsonl(query_path)
    except FileNotFoundError as exc:
        raise V2BenchmarkDataError(
            f"missing unified evaluation dataset file: {exc.filename}"
        ) from exc

    if manifest_payload.get("dataset_version") != DATASET_VERSION:
        raise V2BenchmarkDataError("unexpected unified evaluation dataset version")
    expected_hashes = manifest_payload.get("file_sha256", {})
    for relative_path, path in (
        ("agent/world_states.jsonl", world_path),
        ("agent/queries.jsonl", query_path),
    ):
        if expected_hashes.get(relative_path) != _sha256(path):
            raise V2BenchmarkDataError(
                f"unified evaluation dataset hash mismatch: {relative_path}"
            )
    agent_manifest = manifest_payload.get("agent", {})
    if manifest_payload.get("active_agent_profile") != ACTIVE_AGENT_PROFILE:
        raise V2BenchmarkDataError("unified dataset is not using the active fast-400 profile")
    if (
        agent_manifest.get("world_state_count") != ACTIVE_AGENT_WORLD_COUNT
        or agent_manifest.get("query_count") != ACTIVE_AGENT_QUERY_COUNT
    ):
        raise V2BenchmarkDataError("unified Agent view must contain the active 100/400 rows")
    if len(world_rows) != ACTIVE_AGENT_WORLD_COUNT or len(query_rows) != ACTIVE_AGENT_QUERY_COUNT:
        raise V2BenchmarkDataError("unified Agent view row count does not match fast-400")

    worlds = [
        EvalWorldState.model_validate(_known_fields(row, EvalWorldState))
        for row in world_rows
    ]
    queries = [
        EvalQueryVariant.model_validate(_known_fields(row, EvalQueryVariant))
        for row in query_rows
    ]
    _validate_active_profile(worlds, queries)
    frozen_now = worlds[0].frozen_now
    generator_seed = worlds[0].seed
    # These containers retain the runner's historical interface. Their v2
    # validators describe the shelved 300/1200 fixture, so the active subset
    # is validated above and then adapted without re-running that validator.
    world_dataset = V2WorldStateDataset.model_construct(
        dataset_version=DATASET_VERSION,
        generator_seed=generator_seed,
        frozen_now=frozen_now,
        world_states=worlds,
        review_status="automatic_gold",
    )
    query_dataset = V2QueryDataset.model_construct(
        dataset_version=DATASET_VERSION,
        generator_seed=generator_seed,
        frozen_now=frozen_now,
        queries=queries,
        review_status="automatic_gold",
    )
    manifest = V2BenchmarkManifest.model_construct(
        manifest_id="internet-hospital-agent-evaluation-dataset",
        dataset_version=DATASET_VERSION,
        generator_seed=generator_seed,
        frozen_now=frozen_now,
        world_state_count=ACTIVE_AGENT_WORLD_COUNT,
        query_count=ACTIVE_AGENT_QUERY_COUNT,
        world_states_sha256=expected_hashes["agent/world_states.jsonl"],
        queries_sha256=expected_hashes["agent/queries.jsonl"],
        review_status="automatic_gold",
    )
    return world_dataset, query_dataset, manifest


def _known_fields(row: dict[str, Any], model: type[Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key in model.model_fields}


def _validate_active_profile(
    worlds: list[EvalWorldState], queries: list[EvalQueryVariant]
) -> None:
    world_by_id = {world.world_state_id: world for world in worlds}
    if len(world_by_id) != ACTIVE_AGENT_WORLD_COUNT:
        raise V2BenchmarkDataError("active fast-400 profile contains duplicate WorldStates")
    world_split_counts = {
        split: sum(world.dataset_split == split for world in worlds)
        for split in ACTIVE_AGENT_SPLIT_COUNTS
    }
    query_split_counts = {
        split: sum(query.dataset_split == split for query in queries)
        for split in ACTIVE_AGENT_SPLIT_COUNTS
    }
    expected_world_counts = {
        split: counts[0] for split, counts in ACTIVE_AGENT_SPLIT_COUNTS.items()
    }
    expected_query_counts = {
        split: counts[1] for split, counts in ACTIVE_AGENT_SPLIT_COUNTS.items()
    }
    if world_split_counts != expected_world_counts:
        raise V2BenchmarkDataError(
            f"invalid active WorldState split counts: {world_split_counts}"
        )
    if query_split_counts != expected_query_counts:
        raise V2BenchmarkDataError(
            f"invalid active Query split counts: {query_split_counts}"
        )
    by_world: dict[str, list[EvalQueryVariant]] = {}
    for query in queries:
        world = world_by_id.get(query.world_state_id)
        if world is None:
            raise V2BenchmarkDataError(
                f"active Query references unknown WorldState: {query.query_id}"
            )
        if query.dataset_split != world.dataset_split:
            raise V2BenchmarkDataError(
                f"active Query split mismatch: {query.query_id}"
            )
        by_world.setdefault(query.world_state_id, []).append(query)
    if set(by_world) != set(world_by_id) or any(
        len(items) != 4 or {item.variant_index for item in items} != {1, 2, 3, 4}
        for items in by_world.values()
    ):
        raise V2BenchmarkDataError(
            "each active WorldState must have variants 1 through 4 exactly once"
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["DATASET_VERSION", "DEFAULT_DATASET_ROOT", "load_unified_agent_benchmark"]

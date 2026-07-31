from pathlib import Path

import pytest

from app.agent.benchmark_schemas import BenchmarkReport
from app.agent.local_benchmark_runner import LocalObservedBenchmarkRunner
from app.agent.local_observation_schemas import LocalObservationBundle


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_runner() -> LocalObservedBenchmarkRunner:
    return LocalObservedBenchmarkRunner.from_project_root(PROJECT_ROOT)


@pytest.fixture(scope="module")
def local_run() -> tuple[LocalObservationBundle, BenchmarkReport]:
    return make_runner().run()


def test_local_runner_executes_all_observation_groups(
    local_run: tuple[LocalObservationBundle, BenchmarkReport],
) -> None:
    bundle, report = local_run

    assert report.status == "completed"
    assert report.mode == "local_integration"
    assert len(bundle.agent_runs) == 32
    assert len(bundle.rag_queries) == 12
    assert len(bundle.memory_cases) == 40
    assert len(bundle.provider_cases) == 30


def test_local_rag_records_actual_source_pointers_and_versions(
    local_run: tuple[LocalObservationBundle, BenchmarkReport],
) -> None:
    bundle, _ = local_run

    assert all(
        item.expected_source_id in item.ranked_source_ids[:3]
        for item in bundle.rag_queries
    )
    assert all(item.ranked_source_names for item in bundle.rag_queries)
    assert all(item.source_versions for item in bundle.rag_queries)
    assert all(
        set(item.cited_source_ids) <= set(item.ranked_source_ids)
        for item in bundle.rag_queries
    )


def test_local_memory_and_provider_observations_use_real_components(
    local_run: tuple[LocalObservationBundle, BenchmarkReport],
) -> None:
    bundle, _ = local_run

    assert all(not item.member_scope_leakage for item in bundle.memory_cases)
    assert all(not item.unconfirmed_memory_write_ids for item in bundle.memory_cases)
    assert all(item.source_pointers_preserved for item in bundle.memory_cases)

    retryable = [item for item in bundle.provider_cases if item.expected_retryable]
    writes = [item for item in bundle.provider_cases if not item.read_only]
    assert retryable
    assert all(item.provider_recovered for item in retryable)
    assert all(len(item.attempts) == item.expected_max_attempts for item in retryable)
    assert all(item.write_retry_count == 0 for item in writes)


def test_local_report_keeps_real_model_metrics_unavailable(
    local_run: tuple[LocalObservationBundle, BenchmarkReport],
) -> None:
    _, report = local_run
    metrics = {metric.name: metric for metric in report.metrics}

    assert metrics["rag_recall_at_3"].status == "measured"
    assert metrics["safety_recall"].status == "measured"
    assert metrics["memory_key_retention_rate"].status == "measured"
    assert metrics["provider_recovery_rate"].status == "measured"
    assert metrics["latency_p95_ms"].status == "measured"
    assert metrics["latency_p50_ms"].sample_count == len(local_run[0].agent_runs)
    assert metrics["latency_p95_ms"].sample_count == len(local_run[0].agent_runs)
    assert metrics["answer_quality_pass_rate"].value is None
    assert metrics["average_input_tokens"].value is None
    assert metrics["average_cost_usd"].value is None


def test_local_runner_writes_frozen_observations_and_report(tmp_path: Path) -> None:
    runner = LocalObservedBenchmarkRunner(
        project_root=PROJECT_ROOT,
        output_dir=tmp_path / "output",
    )
    bundle, report = runner.run()
    observation_path, json_path, markdown_path = runner.write_reports(
        bundle,
        report,
        markdown_path=tmp_path / "local_benchmark_report.4d.md",
    )

    assert observation_path.exists()
    assert json_path.exists()
    assert markdown_path.exists()
    assert "Local Integration Benchmark" in markdown_path.read_text(encoding="utf-8")
    assert "average_cost_usd" in markdown_path.read_text(encoding="utf-8")

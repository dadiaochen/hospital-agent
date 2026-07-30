from pathlib import Path

import pytest

from app.agent.benchmark_runner import BenchmarkDataError, BenchmarkRunner


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_runner() -> BenchmarkRunner:
    return BenchmarkRunner.from_project_root(PROJECT_ROOT)


def test_runner_loads_frozen_manifest_and_all_five_datasets() -> None:
    runner = make_runner()

    manifest, _, manifest_hash = runner.load_manifest()
    datasets = runner.load_datasets(manifest)

    assert manifest.status == "frozen"
    assert len(manifest_hash) == 64
    assert {name for name in datasets} == {
        "answer_quality",
        "rag_gold",
        "safety_gold",
        "memory_context",
        "provider_faults",
    }
    assert [len(dataset.cases) for dataset in datasets.values()] == [60, 30, 100, 40, 30]


def test_deterministic_runner_generates_contract_report() -> None:
    report = make_runner().run("deterministic")

    assert report.status == "completed"
    assert report.mode == "deterministic"
    assert report.bad_cases == []
    assert all(dataset.contract_valid for dataset in report.datasets)
    assert report.metrics[0].name == "answer_quality_contract_pass_rate"
    assert report.metrics[0].value == 1.0


def test_runtime_quality_and_cost_metrics_remain_unavailable() -> None:
    report = make_runner().run("deterministic")
    runtime_metrics = [metric for metric in report.metrics if metric.metric_type == "runtime_observation"]

    assert runtime_metrics
    assert all(metric.status == "not_available" for metric in runtime_metrics)
    assert all(metric.value is None for metric in runtime_metrics)


def test_non_deterministic_modes_are_explicitly_not_available() -> None:
    report = make_runner().run("real_model")

    assert report.status == "not_available"
    assert report.metrics == []
    assert "not enabled" in report.notes[0]


def test_tampered_dataset_hash_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = make_runner()
    original = runner._read_json

    def tampered(filename: str):
        payload = original(filename)
        if filename == "rag_gold.v1.json":
            payload["cases"][0]["expected_source"] = "tampered-source"
        return payload

    monkeypatch.setattr(runner, "_read_json", tampered)
    manifest, _, _ = runner.load_manifest()

    with pytest.raises(BenchmarkDataError, match="dataset hash mismatch"):
        runner.load_datasets(manifest)


def test_markdown_report_states_evidence_boundary() -> None:
    report = make_runner().run("deterministic")
    markdown = make_runner().render_markdown(report)

    assert "not a clinical or production performance claim" in markdown
    assert "N/A" in markdown
    assert "cross_member_leakage_rate" in markdown

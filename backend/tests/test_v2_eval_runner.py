from pathlib import Path

import pytest

from app.agent.v2_benchmark_generator import V2BenchmarkDataError
from app.agent.v2_eval_runner import V2EvalRunner
from app.agent.v2_eval_schemas import V2RunnerOptions


ROOT = Path(__file__).resolve().parents[2]


def test_runner_requires_explicit_pending_review_preview() -> None:
    with pytest.raises(V2BenchmarkDataError, match="pending human review"):
        V2EvalRunner(project_root=ROOT).run(V2RunnerOptions(max_cases=1))


def test_runner_aggregates_metrics_and_cleans_namespaces() -> None:
    runner = V2EvalRunner(project_root=ROOT)

    report = runner.run(
        V2RunnerOptions(
            dataset_split="development",
            max_cases=16,
            allow_pending_review=True,
        )
    )

    metric_names = {metric.name for metric in report.metrics}
    assert report.status == "preview"
    assert report.sample_count == 16
    assert "task_success_rate" in metric_names
    assert "p95_latency_ms" in metric_names
    assert "context_pass_rate" in metric_names
    assert all(result.cleanup_succeeded for result in report.case_results)
    assert runner.materializer.backend.active_namespaces == ()


def test_runner_writes_json_and_markdown_report(tmp_path: Path) -> None:
    runner = V2EvalRunner(project_root=ROOT)
    report = runner.run(
        V2RunnerOptions(max_cases=2, allow_pending_review=True)
    )

    json_path, markdown_path = runner.write_report(report, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "4D-B2.5 v2 Evaluation Report" in markdown
    assert "synthetic_projection" in markdown


def test_same_selection_has_stable_report_id() -> None:
    options = V2RunnerOptions(max_cases=3, allow_pending_review=True)
    first = V2EvalRunner(project_root=ROOT).run(options)
    second = V2EvalRunner(project_root=ROOT).run(options)

    assert first.report_id == second.report_id
    assert [item.run_id for item in first.case_results] == [
        item.run_id for item in second.case_results
    ]

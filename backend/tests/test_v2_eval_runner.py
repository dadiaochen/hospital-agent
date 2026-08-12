from pathlib import Path
from threading import Lock, get_ident
import time

import pytest

from app.agent.v2_benchmark_generator import V2BenchmarkDataError
from app.agent.v2_eval_runner import SyntheticProjectionExecutor, V2EvalRunner
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


def test_parallel_preview_keeps_repeat_order_and_cleans_namespaces() -> None:
    runner = V2EvalRunner(project_root=ROOT)

    report = runner.run(
        V2RunnerOptions(
            max_cases=4,
            repeat=2,
            concurrency=4,
            allow_pending_review=True,
        )
    )

    assert report.sample_count == 8
    assert [item.query_id for item in report.case_results] == [
        item.query_id
        for item in runner.run(
            V2RunnerOptions(
                max_cases=4,
                repeat=2,
                concurrency=1,
                allow_pending_review=True,
            )
        ).case_results
    ]
    assert all(item.cleanup_succeeded for item in report.case_results)
    assert runner.materializer.backend.active_namespaces == ()


def test_parallel_preview_executes_independent_queries_concurrently() -> None:
    class ProbeExecutor(SyntheticProjectionExecutor):
        def __init__(self) -> None:
            self.thread_ids: set[int] = set()
            self.active = 0
            self.maximum = 0
            self.lock = Lock()

        def execute(self, materialized, *, repeat_index: int):
            with self.lock:
                self.thread_ids.add(get_ident())
                self.active += 1
                self.maximum = max(self.maximum, self.active)
            time.sleep(0.02)
            try:
                return super().execute(materialized, repeat_index=repeat_index)
            finally:
                with self.lock:
                    self.active -= 1

    executor = ProbeExecutor()
    report = V2EvalRunner(project_root=ROOT, executor=executor).run(
        V2RunnerOptions(
            max_cases=6,
            concurrency=4,
            allow_pending_review=True,
        )
    )

    assert report.sample_count == 6
    assert executor.maximum > 1
    assert len(executor.thread_ids) > 1

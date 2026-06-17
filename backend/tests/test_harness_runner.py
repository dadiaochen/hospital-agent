from pathlib import Path

from app.agent.harness_runner import HarnessRunner


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_runner() -> HarnessRunner:
    return HarnessRunner(
        cases_path=FIXTURES_DIR / "agent_harness_cases.json",
        traces_path=FIXTURES_DIR / "mock_run_traces.json",
    )


def test_runner_loads_sixteen_cases_and_traces() -> None:
    runner = make_runner()

    assert len(runner.load_cases()) == 16
    assert len(runner.load_traces()) == 16


def test_runner_generates_results_and_aggregated_metrics() -> None:
    output = make_runner().run()

    assert len(output.results) == 16
    assert output.metrics.case_count == 16
    assert output.metrics.task_success_rate == 0.625
    assert output.metrics.tool_call_accuracy_avg == 0.9875
    assert output.metrics.groundedness_rate == 0.9375
    assert output.metrics.schema_valid_rate == 1.0
    assert output.metrics.hallucination_rate == 0.1875
    assert output.metrics.safety_recall_rate == 0.9375
    assert output.metrics.context_isolation_pass_rate == 0.9375
    assert output.metrics.p95_latency_ms == 260


def test_runner_generates_markdown_report() -> None:
    runner = make_runner()
    output = runner.run()

    report = runner.render_markdown(output)

    assert "# Agent Evaluation Report Example" in report
    assert "task_success_rate" in report
    assert "refill_father_low_stock" in report
    assert "deterministic mock fixtures" in report


def test_markdown_rendering_is_deterministic() -> None:
    runner = make_runner()
    output = runner.run()

    assert runner.render_markdown(output) == runner.render_markdown(output)


def test_example_report_matches_runner_output() -> None:
    runner = make_runner()
    output = runner.run()
    project_root = Path(__file__).resolve().parents[2]
    report_path = project_root / "docs" / "agent_eval_report.example.md"

    assert report_path.read_text(encoding="utf-8") == runner.render_markdown(output)

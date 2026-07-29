from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.ablation_harness import AblationHarnessRunner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "business_harness_cases.4b.json"
)


@pytest.fixture(scope="module")
def harness_output():
    return AblationHarnessRunner(FIXTURE_PATH).run()


def test_suite_matches_the_roadmap_32_case_inventory() -> None:
    _, cases = AblationHarnessRunner(FIXTURE_PATH).load_suite()

    assert len(cases) == 32
    assert Counter(case.category for case in cases) == {
        "normal_single_domain": 6,
        "complex_cross_domain": 6,
        "missing_information": 3,
        "high_risk_medical": 5,
        "rag_and_source": 4,
        "provider_or_tool_failure": 3,
        "member_isolation_attack": 3,
        "confirmation_idempotency": 2,
    }
    assert all(case.member_id for case in cases)
    assert all(
        invocation.parameters.get("member_id", case.member_id) == case.member_id
        for case in cases
        for invocation in case.expected_tool_calls
    )


def test_runner_creates_three_frozen_business_traces_per_case(harness_output) -> None:
    assert len(harness_output.results) == 96
    assert Counter(result.strategy for result in harness_output.results) == {
        "single_agent": 32,
        "fixed_router": 32,
        "bounded_supervisor": 32,
    }
    assert all(
        result.trace.fairness_config_id == harness_output.fairness_config.config_id
        for result in harness_output.results
    )
    assert all(result.trace.run_trace.case_id == result.case_id for result in harness_output.results)
    assert all(
        result.trace.run_trace.member_id
        == result.trace.run_trace.safety_trace.member_id
        for result in harness_output.results
    )
    with pytest.raises(ValidationError):
        harness_output.results[0].trace.run_trace.final_answer.content = "mutated"


def test_ablation_separates_simple_and_complex_orchestration_value(
    harness_output,
) -> None:
    metrics = {metric.strategy: metric for metric in harness_output.metrics}

    assert metrics["fixed_router"].simple.task_completion_rate == 1.0
    assert metrics["fixed_router"].complex.task_completion_rate == 0.0
    assert metrics["bounded_supervisor"].simple.task_completion_rate == 1.0
    assert metrics["bounded_supervisor"].complex.task_completion_rate == 1.0
    assert metrics["bounded_supervisor"].route_order_exact_match_rate == 1.0
    assert metrics["single_agent"].route_order_exact_match_rate is None
    assert metrics["single_agent"].duplicate_tool_calls_avg > 0.0
    assert (
        metrics["single_agent"].tool_set_exact_match_rate
        < metrics["bounded_supervisor"].tool_set_exact_match_rate
    )
    assert metrics["fixed_router"].p50_latency_ms < metrics["bounded_supervisor"].p95_latency_ms


def test_safety_isolation_and_rag_controls_are_not_changed_by_strategy(
    harness_output,
) -> None:
    metrics = {metric.strategy: metric for metric in harness_output.metrics}
    shared_values = {
        (
            metric.safety_recall_rate,
            metric.safety_precision_rate,
            metric.context_isolation_pass_rate,
            metric.governance_coverage_rate,
            metric.rag_recall_at_3,
            metric.rag_recall_at_5,
            metric.citation_correctness_rate,
        )
        for metric in metrics.values()
    }

    assert shared_values == {(1.0, 1.0, 1.0, 1.0, 0.75, 1.0, 1.0)}
    attack_results = [
        result
        for result in harness_output.results
        if result.category == "member_isolation_attack"
    ]
    assert len(attack_results) == 9
    assert all(result.evaluation.context_isolation_passed for result in attack_results)
    assert all(
        result.trace.run_trace.safety_trace.blocked
        or result.case_id.endswith("cache_pollution")
        for result in attack_results
    )


def test_harness_does_not_invent_token_or_cost_metrics(harness_output) -> None:
    assert all(
        result.trace.token_usage_available is False
        and result.trace.input_tokens is None
        and result.trace.output_tokens is None
        and result.trace.total_tokens is None
        and result.trace.billed_cost_usd is None
        for result in harness_output.results
    )
    assert all(metric.token_usage_available_rate == 0.0 for metric in harness_output.metrics)
    assert all(metric.avg_total_tokens is None for metric in harness_output.metrics)
    assert all(metric.total_billed_cost_usd is None for metric in harness_output.metrics)


def test_report_is_repeatable_and_labels_fixture_metrics(
    harness_output,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "ablation.json"
    markdown_path = tmp_path / "ablation.md"

    AblationHarnessRunner.write_reports(
        harness_output,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    first_json = json_path.read_text(encoding="utf-8")
    first_markdown = markdown_path.read_text(encoding="utf-8")
    AblationHarnessRunner.write_reports(
        harness_output,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert json.loads(first_json)["fairness_config"]["config_id"] == "4b-task11-shared-v1"
    assert first_json == json_path.read_text(encoding="utf-8")
    assert first_markdown == markdown_path.read_text(encoding="utf-8")
    assert "frozen deterministic fixtures" in first_markdown
    assert "not a production" in first_markdown
    assert "Token and billed cost remain" in first_markdown
    assert "simple success" in first_markdown

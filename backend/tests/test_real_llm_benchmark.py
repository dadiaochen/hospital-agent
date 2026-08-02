from pathlib import Path
from datetime import datetime, timezone
import json

import pytest

from app.agent.real_llm_benchmark import (
    ModelPricing,
    RealLLMBenchmarkReport,
    RealLLMBenchmarkRunner,
    RealLLMCaseResult,
    RealLLMFinalizationError,
    RealLLMReviewItem,
)
from app.agent.v2_eval_schemas import ConfirmationDraftSnapshot, V2RunnerOptions
from app.agent.v2_integration import (
    IntegrationIdentityMap,
    UnifiedHealthGraphIntegrationExecutor,
)
from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_integration_executor_keeps_b3_model_configuration() -> None:
    configuration = Settings(
        model_provider="deterministic",
        model_name="deterministic-local",
    )
    identity = IntegrationIdentityMap(
        benchmark_user_id="benchmark-user",
        actual_user_id="actual-user",
        member_ids={"member-1": "actual-member-1"},
        source_ids={},
    )

    executor = UnifiedHealthGraphIntegrationExecutor(
        identity,
        model_configuration=configuration,
    )

    assert executor.model_configuration is configuration


def test_real_llm_runner_is_blocked_without_live_flag_and_sends_no_request() -> None:
    runner = RealLLMBenchmarkRunner(
        project_root=ROOT,
        configuration=Settings(
            model_provider="deterministic",
            model_name="deterministic-local",
        ),
    )

    report = runner.run(
        V2RunnerOptions(
            runner_mode="integration",
            max_cases=1,
            allow_pending_review=True,
        ),
        live=False,
    )

    assert report.status == "blocked"
    assert report.sample_count == 0
    assert report.metrics[0].status == "not_available"
    assert "no model request" in report.notes[0]


def test_real_llm_runner_does_not_call_network_when_provider_is_deterministic() -> None:
    runner = RealLLMBenchmarkRunner(
        project_root=ROOT,
        configuration=Settings(
            model_provider="deterministic",
            model_name="deterministic-local",
        ),
    )

    report = runner.run(
        V2RunnerOptions(
            runner_mode="integration",
            max_cases=1,
            allow_pending_review=True,
        ),
        live=True,
    )

    assert report.status == "blocked"
    assert "not openai_compatible" in report.notes[0]


def test_cost_requires_complete_usage_and_explicit_prices() -> None:
    pricing = ModelPricing(
        input_price_per_1m_usd=0.5,
        output_price_per_1m_usd=1.0,
    )

    assert (
        RealLLMBenchmarkRunner.calculate_cost(
            input_tokens=1_000,
            output_tokens=2_000,
            pricing=pricing,
        )
        == 0.0025
    )
    assert (
        RealLLMBenchmarkRunner.calculate_cost(
            input_tokens=None,
            output_tokens=2_000,
            pricing=pricing,
        )
        is None
    )
    assert (
        RealLLMBenchmarkRunner.calculate_cost(
            input_tokens=1_000,
            output_tokens=2_000,
            pricing=ModelPricing(),
        )
        is None
    )


def test_real_llm_metrics_keep_unavailable_quality_explicit() -> None:
    configuration = Settings(
        model_provider="openai_compatible",
        model_api_base="https://model.example/v1",
        model_api_key="local-test-key",
        model_name="test-model",
    )
    runner = RealLLMBenchmarkRunner(project_root=ROOT, configuration=configuration)
    cases = [
        RealLLMCaseResult(
            query_id="q-1",
            world_state_id="w-1",
            run_id="r-1",
            task_success=True,
            workflow_latency_ms=100,
            model_latency_ms=40,
            effective_provider="openai_compatible",
            model_name="test-model",
            token_usage_available=True,
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            cost_usd=0.001,
        )
    ]

    metrics = runner._metrics(cases)
    by_name = {metric.name: metric for metric in metrics}
    assert by_name["real_provider_effective_rate"].value == 1.0
    assert by_name["token_usage_available_rate"].value == 1.0
    assert by_name["average_cost_usd"].value == 0.001
    assert by_name["human_reviewed_answer_quality"].value is None
    assert by_name["human_reviewed_answer_quality"].status == "not_available"


def test_b3_review_queue_keeps_local_draft_evidence_visible() -> None:
    item = RealLLMReviewItem(
        query_id="q-1",
        world_state_id="w-1",
        run_id="r-1",
        user_input="prepare a reminder draft",
        final_answer="A local draft is ready and awaits confirmation.",
        expected_member_id="member-1",
        expected_intent="reminder",
        expected_human_confirmation_required=True,
        automatic_task_success=True,
        confirmation_draft=ConfirmationDraftSnapshot(
            draft_id="draft:r-1",
            task_id="q-1",
            member_id="member-1",
            action_type="reminder_create",
            status="DRAFT",
            draft_version=1,
            need_human_confirmation=True,
            local_only=True,
            external_action_status="not_submitted",
            summary="A local reminder draft is ready.",
            preview={"medicine_name": "demo-medication", "schedule": {"time": "08:00"}},
        ),
    )
    report = RealLLMBenchmarkReport(
        report_id="report-1",
        generated_at=datetime.now(timezone.utc),
        status="preview",
        provider_name="openai_compatible",
        model_name="test-model",
        dataset_split="development",
        sample_count=1,
        pricing=ModelPricing(),
        review_items=(item,),
        notes=("test report",),
    )

    markdown = RealLLMBenchmarkRunner.render_review_queue(report)

    assert "draft:r-1" in markdown
    assert "reminder_create" in markdown
    assert "not_submitted" in markdown
    assert "demo-medication" in markdown
    assert "08:00" in markdown


def _write_review_fixture(
    tmp_path: Path,
    *,
    review_status: str,
    final_answer: str = "A local draft is ready and awaits confirmation.",
    reviewer_notes: str | None = None,
) -> tuple[RealLLMBenchmarkRunner, Path, Path]:
    item = RealLLMReviewItem(
        query_id="q-1",
        world_state_id="w-1",
        run_id="r-1",
        user_input="prepare a reminder draft",
        final_answer="A local draft is ready and awaits confirmation.",
        expected_member_id="member-1",
        expected_intent="reminder",
        expected_human_confirmation_required=True,
        automatic_task_success=True,
    )
    report = RealLLMBenchmarkReport(
        report_id="report-1",
        generated_at=datetime.now(timezone.utc),
        status="preview",
        provider_name="openai_compatible",
        model_name="test-model",
        dataset_version="v2-test",
        dataset_split="development",
        sample_count=1,
        pricing=ModelPricing(),
        review_items=(item,),
        metrics=(
            RealLLMBenchmarkRunner._mean(
                "human_reviewed_answer_quality",
                [],
                "ratio",
                "pending human review",
            ),
        ),
        notes=("Review badcases before writing any quality claim.",),
    )
    report_path = tmp_path / "report.json"
    queue_path = tmp_path / "queue.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    reviewed_item = item.model_dump(mode="json")
    reviewed_item.update(
        {
            "review_status": review_status,
            "reviewer_notes": reviewer_notes,
            "final_answer": final_answer,
        }
    )
    queue_path.write_text(
        json.dumps(
            {"report_id": report.report_id, "review_items": [reviewed_item]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return RealLLMBenchmarkRunner(project_root=ROOT), report_path, queue_path


def test_b3_finalizer_accepts_pass_alias_and_freezes_manifest(tmp_path: Path) -> None:
    runner, report_path, queue_path = _write_review_fixture(
        tmp_path,
        review_status="pass",
    )

    report = runner.finalize_reviewed_report(
        report_path=report_path,
        review_queue_path=queue_path,
    )
    json_path, markdown_path, manifest_path = runner.write_finalized_report(
        report,
        output_dir=tmp_path / "final",
    )

    assert report.status == "completed"
    assert report.reviewed_sample_count == 1
    assert report.reviewed_pass_count == 1
    assert report.reviewed_fail_count == 0
    assert report.review_items[0].review_status == "reviewed_pass"
    assert report.review_queue_sha256 is not None
    quality = next(
        metric
        for metric in report.metrics
        if metric.name == "human_reviewed_answer_quality"
    )
    assert quality.value == 1.0
    assert quality.status == "measured"
    assert json_path.exists()
    assert "Human Review Freeze" in markdown_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["reviewed_pass_count"] == 1
    assert set(manifest["artifact_sha256"]) == {
        "agent_eval_report.4d-b3.real-llm.json",
        "agent_eval_report.4d-b3.real-llm.md",
        "badcase_review_queue.4d-b3.json",
        "badcase_review_queue.4d-b3.md",
    }


def test_b3_finalizer_rejects_pending_review(tmp_path: Path) -> None:
    runner, report_path, queue_path = _write_review_fixture(
        tmp_path,
        review_status="pending_review",
    )

    with pytest.raises(RealLLMFinalizationError, match="not reviewed"):
        runner.finalize_reviewed_report(
            report_path=report_path,
            review_queue_path=queue_path,
        )


def test_b3_finalizer_rejects_modified_evidence(tmp_path: Path) -> None:
    runner, report_path, queue_path = _write_review_fixture(
        tmp_path,
        review_status="pass",
        final_answer="changed after the model run",
    )

    with pytest.raises(RealLLMFinalizationError, match="evidence was modified"):
        runner.finalize_reviewed_report(
            report_path=report_path,
            review_queue_path=queue_path,
        )


def test_b3_failed_review_requires_notes(tmp_path: Path) -> None:
    runner, report_path, queue_path = _write_review_fixture(
        tmp_path,
        review_status="fail",
    )

    with pytest.raises(RealLLMFinalizationError, match="requires reviewer_notes"):
        runner.finalize_reviewed_report(
            report_path=report_path,
            review_queue_path=queue_path,
        )

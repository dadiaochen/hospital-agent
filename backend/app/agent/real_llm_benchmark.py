"""Optional 4D-B3 real-model benchmark.

The default project path stays deterministic.  This module only runs a model
when the caller explicitly passes ``live=True`` and the server configuration
contains an OpenAI-compatible provider.  Token counts are read from provider
usage; cost is calculated only when both prices are explicitly configured.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import fmean
from typing import Literal

from pydantic import Field

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_eval_runner import V2EvalRunner, V2RunExecutor
from app.agent.v2_eval_schemas import (
    ConfirmationDraftSnapshot,
    V2RunArtifacts,
    V2RunnerOptions,
)
from app.agent.v2_integration import (
    IntegrationIdentityMap,
    PostgresV2Materializer,
    UnifiedHealthGraphIntegrationExecutor,
)
from app.core.config import Settings, settings
from app.core.database import SessionLocal


B3ReportStatus = Literal["blocked", "preview", "completed"]
MetricStatus = Literal["measured", "not_available"]
HumanReviewStatus = Literal["pending_review", "reviewed_pass", "reviewed_fail"]


class RealLLMFinalizationError(ValueError):
    """Raised when a reviewed queue cannot safely finalize its source report."""


class ModelPricing(ContractModel):
    """Prices supplied by the user for one million input/output tokens."""

    input_price_per_1m_usd: float | None = Field(default=None, ge=0)
    output_price_per_1m_usd: float | None = Field(default=None, ge=0)


class RealLLMMetric(ContractModel):
    name: NonEmptyStr
    value: float | None = None
    status: MetricStatus
    sample_count: int = Field(ge=0)
    unit: NonEmptyStr
    note: NonEmptyStr


class RealLLMCaseResult(ContractModel):
    query_id: NonEmptyStr
    world_state_id: NonEmptyStr
    run_id: NonEmptyStr
    task_success: bool
    workflow_latency_ms: int = Field(ge=0)
    model_latency_ms: int = Field(ge=0)
    effective_provider: NonEmptyStr | None = None
    model_name: NonEmptyStr | None = None
    fallback_used: bool = False
    token_usage_available: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    failure_reasons: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class RealLLMReviewItem(ContractModel):
    """Synthetic case and answer bundle for manual badcase review."""

    query_id: NonEmptyStr
    world_state_id: NonEmptyStr
    run_id: NonEmptyStr
    user_input: NonEmptyStr
    final_answer: str
    expected_member_id: NonEmptyStr
    expected_intent: NonEmptyStr
    expected_safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_sources: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_human_confirmation_required: bool
    forbidden_phrases: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    automatic_task_success: bool
    automatic_failure_reasons: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    effective_provider: NonEmptyStr | None = None
    fallback_used: bool = False
    confirmation_draft: ConfirmationDraftSnapshot | None = None
    review_status: HumanReviewStatus = "pending_review"
    reviewer_notes: str | None = None


class RealLLMBenchmarkReport(ContractModel):
    report_id: NonEmptyStr
    generated_at: datetime
    status: B3ReportStatus
    runner_mode: Literal["real_llm"] = "real_llm"
    provider_name: NonEmptyStr
    model_name: NonEmptyStr
    dataset_version: NonEmptyStr | None = None
    dataset_split: Literal["all", "development", "validation", "holdout"]
    sample_count: int = Field(ge=0)
    pricing: ModelPricing
    case_results: tuple[RealLLMCaseResult, ...] = Field(default_factory=tuple)
    review_items: tuple[RealLLMReviewItem, ...] = Field(default_factory=tuple)
    metrics: tuple[RealLLMMetric, ...] = Field(default_factory=tuple)
    failure_counts: dict[str, int] = Field(default_factory=dict)
    world_states_sha256: str | None = None
    queries_sha256: str | None = None
    finalized_at: datetime | None = None
    reviewed_sample_count: int = Field(default=0, ge=0)
    reviewed_pass_count: int = Field(default=0, ge=0)
    reviewed_fail_count: int = Field(default=0, ge=0)
    review_queue_sha256: str | None = None
    notes: tuple[NonEmptyStr, ...] = Field(min_length=1)


class RealLLMFinalManifest(ContractModel):
    """Hashes that freeze the exact files emitted by a completed B3 review."""

    report_id: NonEmptyStr
    status: Literal["completed"] = "completed"
    finalized_at: datetime
    dataset_version: NonEmptyStr | None = None
    dataset_split: Literal["all", "development", "validation", "holdout"]
    sample_count: int = Field(ge=1)
    reviewed_pass_count: int = Field(ge=0)
    reviewed_fail_count: int = Field(ge=0)
    review_queue_canonical_sha256: NonEmptyStr
    artifact_sha256: dict[NonEmptyStr, NonEmptyStr]


class _RecordingExecutor:
    """Keep frozen artifacts while V2EvalRunner performs grading and cleanup."""

    def __init__(self, delegate: V2RunExecutor) -> None:
        self.delegate = delegate
        self.artifacts: list[V2RunArtifacts] = []

    def execute(self, materialized, *, repeat_index: int) -> V2RunArtifacts:
        artifacts = self.delegate.execute(materialized, repeat_index=repeat_index)
        self.artifacts.append(artifacts)
        return artifacts


SessionFactory = Callable[[], object]


class RealLLMBenchmarkRunner:
    """Run real-model observations through the existing integration evaluator."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        identity_map: IntegrationIdentityMap | None = None,
        configuration: Settings | None = None,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.identity_map = identity_map
        self.configuration = configuration or settings
        self.session_factory = session_factory

    def run(
        self,
        options: V2RunnerOptions | None = None,
        *,
        live: bool = False,
    ) -> RealLLMBenchmarkReport:
        options = options or V2RunnerOptions(
            runner_mode="integration",
            max_cases=1,
            allow_pending_review=True,
        )
        if not live:
            return self._blocked_report(
                options,
                "live=false; no model request was sent. Pass --live explicitly to run the optional experiment.",
            )

        configuration_error = self._configuration_error()
        if configuration_error is not None:
            return self._blocked_report(options, configuration_error)
        if self.identity_map is None:
            return self._blocked_report(
                options,
                "real LLM mode requires an explicit local identity/source map",
            )

        materializer = PostgresV2Materializer(self.session_factory)
        executor = _RecordingExecutor(
            UnifiedHealthGraphIntegrationExecutor(
                self.identity_map,
                model_configuration=self.configuration,
            )
        )
        report = V2EvalRunner(
            project_root=self.project_root,
            materializer=materializer,
            executor=executor,
        ).run(options.model_copy(update={"runner_mode": "integration"}))
        if len(report.case_results) != len(executor.artifacts):
            raise RuntimeError("real LLM report and artifact counts do not match")
        case_results = tuple(
            self._case_result(case, artifacts)
            for case, artifacts in zip(
                report.case_results,
                executor.artifacts,
                strict=True,
            )
        )
        _, queries, _ = load_v2_benchmark(project_root=self.project_root)
        queries_by_id = {query.query_id: query for query in queries.queries}
        review_items = tuple(
            self._review_item(
                queries_by_id[case.query_id],
                case,
                artifacts,
            )
            for case, artifacts in zip(
                report.case_results,
                executor.artifacts,
                strict=True,
            )
        )
        return RealLLMBenchmarkReport(
            report_id=f"4d-b3-{report.report_id}",
            generated_at=datetime.now(timezone.utc),
            status=report.status,
            provider_name=self.configuration.model_provider,
            model_name=self.configuration.model_name,
            dataset_version=report.dataset_version,
            dataset_split=report.dataset_split,
            sample_count=report.sample_count,
            pricing=self._pricing(),
            case_results=case_results,
            review_items=review_items,
            metrics=self._metrics(case_results),
            failure_counts=report.failure_counts,
            world_states_sha256=report.world_states_sha256,
            queries_sha256=report.queries_sha256,
            notes=(
                "The real provider was called only through ModelGateway and the final-answer node.",
                "Token values come only from provider usage; no character-based token estimate is used.",
                "Deterministic contract pass rate is not human-reviewed answer quality.",
                "Review badcases before writing any quality, safety or clinical claim into a resume.",
            ),
        )

    def write_report(
        self,
        report: RealLLMBenchmarkReport,
        *,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        import json

        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "agent_eval_report.4d-b3.real-llm.json"
        markdown_path = output_dir / "agent_eval_report.4d-b3.real-llm.md"
        json_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(self.render_markdown(report), encoding="utf-8")
        review_json_path = output_dir / "badcase_review_queue.4d-b3.json"
        review_markdown_path = output_dir / "badcase_review_queue.4d-b3.md"
        review_json_path.write_text(
            json.dumps(
                {
                    "report_id": report.report_id,
                    "review_items": [
                        item.model_dump(mode="json") for item in report.review_items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        review_markdown_path.write_text(
            self.render_review_queue(report),
            encoding="utf-8",
        )
        return json_path, markdown_path

    def finalize_reviewed_report(
        self,
        *,
        report_path: Path,
        review_queue_path: Path,
    ) -> RealLLMBenchmarkReport:
        """Merge a complete human review into its immutable preview report.

        Humans may enter ``pass``/``fail`` for convenience.  The frozen report
        stores canonical ``reviewed_pass``/``reviewed_fail`` values.  Every
        non-review field is compared with the source report so editing an
        answer, expected source or member ID cannot silently change evidence.
        """

        source_report = RealLLMBenchmarkReport.model_validate(
            json.loads(report_path.read_text(encoding="utf-8"))
        )
        if source_report.status == "blocked" or not source_report.review_items:
            raise RealLLMFinalizationError(
                "only a non-empty preview report can be finalized"
            )

        raw_queue = json.loads(review_queue_path.read_text(encoding="utf-8"))
        if not isinstance(raw_queue, dict):
            raise RealLLMFinalizationError("review queue must be a JSON object")
        if raw_queue.get("report_id") != source_report.report_id:
            raise RealLLMFinalizationError(
                "review queue report_id does not match the preview report"
            )
        raw_items = raw_queue.get("review_items")
        if not isinstance(raw_items, list):
            raise RealLLMFinalizationError("review_items must be a JSON array")

        status_aliases = {
            "pass": "reviewed_pass",
            "fail": "reviewed_fail",
            "reviewed_pass": "reviewed_pass",
            "reviewed_fail": "reviewed_fail",
        }
        reviewed_items: list[RealLLMReviewItem] = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise RealLLMFinalizationError(
                    f"review item {index} must be a JSON object"
                )
            normalized = dict(raw_item)
            raw_status = str(normalized.get("review_status", "pending_review"))
            canonical_status = status_aliases.get(raw_status)
            if canonical_status is None:
                raise RealLLMFinalizationError(
                    f"review item {index} is not reviewed: {raw_status}"
                )
            normalized["review_status"] = canonical_status
            notes = normalized.get("reviewer_notes")
            if canonical_status == "reviewed_fail" and not (
                isinstance(notes, str) and notes.strip()
            ):
                raise RealLLMFinalizationError(
                    f"failed review item {index} requires reviewer_notes"
                )
            reviewed_items.append(RealLLMReviewItem.model_validate(normalized))

        expected_ids = tuple(item.query_id for item in source_report.review_items)
        reviewed_ids = tuple(item.query_id for item in reviewed_items)
        if len(set(reviewed_ids)) != len(reviewed_ids):
            raise RealLLMFinalizationError("review queue contains duplicate query_id")
        if reviewed_ids != expected_ids:
            raise RealLLMFinalizationError(
                "review queue query order or membership does not match the preview report"
            )
        if source_report.sample_count != len(reviewed_items):
            raise RealLLMFinalizationError(
                "reviewed item count does not match report sample_count"
            )

        for original, reviewed in zip(
            source_report.review_items, reviewed_items, strict=True
        ):
            if self._immutable_review_fields(original) != self._immutable_review_fields(
                reviewed
            ):
                raise RealLLMFinalizationError(
                    f"review evidence was modified for query_id={original.query_id}"
                )

        pass_count = sum(
            item.review_status == "reviewed_pass" for item in reviewed_items
        )
        fail_count = len(reviewed_items) - pass_count
        quality_metric = RealLLMMetric(
            name="human_reviewed_answer_quality",
            value=pass_count / len(reviewed_items),
            status="measured",
            sample_count=len(reviewed_items),
            unit="ratio",
            note=(
                "Human-reviewed pass count divided by all frozen reviewed samples; "
                "review covers FinalAnswer plus its draft and evidence snapshot."
            ),
        )
        metrics = tuple(
            quality_metric
            if metric.name == "human_reviewed_answer_quality"
            else metric
            for metric in source_report.metrics
        )
        if not any(
            metric.name == "human_reviewed_answer_quality"
            for metric in source_report.metrics
        ):
            metrics = (*metrics, quality_metric)

        canonical_payload = self._canonical_review_payload(
            source_report.report_id,
            reviewed_items,
        )
        review_hash = hashlib.sha256(
            json.dumps(
                canonical_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        notes = tuple(
            note
            for note in source_report.notes
            if not note.startswith("Review badcases before")
        ) + (
            f"Human review completed: {pass_count} pass, {fail_count} fail, {len(reviewed_items)} total.",
            "Human review covered FinalAnswer plus the frozen draft and evidence snapshot.",
            "The reviewed sample scope is development preview data, not a production or clinical metric.",
        )
        return source_report.model_copy(
            update={
                "status": "completed",
                "finalized_at": datetime.now(timezone.utc),
                "review_items": tuple(reviewed_items),
                "metrics": metrics,
                "reviewed_sample_count": len(reviewed_items),
                "reviewed_pass_count": pass_count,
                "reviewed_fail_count": fail_count,
                "review_queue_sha256": review_hash,
                "failure_counts": {
                    **source_report.failure_counts,
                    "human_review_fail": fail_count,
                },
                "notes": notes,
            }
        )

    def write_finalized_report(
        self,
        report: RealLLMBenchmarkReport,
        *,
        output_dir: Path,
    ) -> tuple[Path, Path, Path]:
        if report.status != "completed" or report.finalized_at is None:
            raise RealLLMFinalizationError(
                "write_finalized_report requires a completed reviewed report"
            )
        json_path, markdown_path = self.write_report(report, output_dir=output_dir)
        review_json_path = output_dir / "badcase_review_queue.4d-b3.json"
        review_markdown_path = output_dir / "badcase_review_queue.4d-b3.md"
        artifacts = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                json_path,
                markdown_path,
                review_json_path,
                review_markdown_path,
            )
        }
        manifest = RealLLMFinalManifest(
            report_id=report.report_id,
            finalized_at=report.finalized_at,
            dataset_version=report.dataset_version,
            dataset_split=report.dataset_split,
            sample_count=report.sample_count,
            reviewed_pass_count=report.reviewed_pass_count,
            reviewed_fail_count=report.reviewed_fail_count,
            review_queue_canonical_sha256=report.review_queue_sha256 or "missing",
            artifact_sha256=artifacts,
        )
        manifest_path = output_dir / "benchmark_manifest.4d-b3.final.json"
        manifest_path.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return json_path, markdown_path, manifest_path

    @staticmethod
    def _immutable_review_fields(item: RealLLMReviewItem) -> dict[str, object]:
        return item.model_dump(
            mode="json",
            exclude={"review_status", "reviewer_notes"},
        )

    @staticmethod
    def _canonical_review_payload(
        report_id: str,
        items: Sequence[RealLLMReviewItem],
    ) -> dict[str, object]:
        return {
            "report_id": report_id,
            "review_items": [item.model_dump(mode="json") for item in items],
        }

    def _configuration_error(self) -> str | None:
        configured = self.configuration
        if configured.model_provider != "openai_compatible":
            return (
                "MODEL_PROVIDER is not openai_compatible; no real LLM request was sent. "
                "Keep deterministic mode for offline runs."
            )
        if not configured.model_api_base:
            return "MODEL_API_BASE is missing; no real LLM request was sent"
        if not configured.model_api_key or not configured.model_api_key.get_secret_value().strip():
            return "MODEL_API_KEY is missing; no real LLM request was sent"
        if not configured.model_name.strip() or configured.model_name == "deterministic-local":
            return "MODEL_NAME must identify a real model; no request was sent"
        return None

    def _pricing(self) -> ModelPricing:
        return ModelPricing(
            input_price_per_1m_usd=self.configuration.model_input_price_per_1m_usd,
            output_price_per_1m_usd=self.configuration.model_output_price_per_1m_usd,
        )

    def _blocked_report(
        self,
        options: V2RunnerOptions,
        reason: str,
    ) -> RealLLMBenchmarkReport:
        return RealLLMBenchmarkReport(
            report_id="4d-b3-blocked",
            generated_at=datetime.now(timezone.utc),
            status="blocked",
            provider_name=self.configuration.model_provider,
            model_name=self.configuration.model_name,
            dataset_split=options.dataset_split,
            sample_count=0,
            pricing=self._pricing(),
            metrics=(
                RealLLMMetric(
                    name="real_llm_call_available",
                    value=None,
                    status="not_available",
                    sample_count=0,
                    unit="boolean",
                    note=reason,
                ),
            ),
            notes=(
                reason,
                "This blocked report is safe to generate without a key and contains no customer data.",
            ),
        )

    def _case_result(self, case, artifacts: V2RunArtifacts) -> RealLLMCaseResult:
        observation = next(
            (
                item
                for item in artifacts.run_trace.observations
                if item.event_type == "model"
            ),
            None,
        )
        usage_available = bool(observation and observation.token_usage_available)
        input_tokens = observation.input_tokens if usage_available else None
        output_tokens = observation.output_tokens if usage_available else None
        total_tokens = observation.total_tokens if usage_available else None
        failure_reasons = list(case.failure_reasons)
        if observation and observation.fallback_reason:
            failure_reasons.append(
                f"model_provider.{observation.fallback_reason}"
            )
        return RealLLMCaseResult(
            query_id=case.query_id,
            world_state_id=case.world_state_id,
            run_id=case.run_id,
            task_success=case.task_success,
            workflow_latency_ms=case.latency_ms,
            model_latency_ms=observation.latency_ms if observation else 0,
            effective_provider=observation.provider_name if observation else None,
            model_name=observation.model_name if observation else None,
            fallback_used=bool(observation and observation.fallback_reason),
            token_usage_available=usage_available,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=self.calculate_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                pricing=self._pricing(),
            ),
            failure_reasons=tuple(dict.fromkeys(failure_reasons)),
        )

    @staticmethod
    def _review_item(query, case, artifacts: V2RunArtifacts) -> RealLLMReviewItem:
        return RealLLMReviewItem(
            query_id=query.query_id,
            world_state_id=query.world_state_id,
            run_id=artifacts.run_trace.run_id,
            user_input=query.user_input,
            final_answer=artifacts.run_trace.final_answer.content,
            expected_member_id=query.expected_member_id,
            expected_intent=query.expected_intent,
            expected_safety_flags=tuple(query.expected_safety_flags),
            expected_sources=tuple(query.expected_sources),
            expected_human_confirmation_required=(
                query.expected_human_confirmation_required
            ),
            forbidden_phrases=tuple(query.forbidden_phrases),
            automatic_task_success=case.task_success,
            automatic_failure_reasons=tuple(case.failure_reasons),
            effective_provider=next(
                (
                    item.provider_name
                    for item in artifacts.run_trace.observations
                    if item.event_type == "model" and item.provider_name
                ),
                None,
            ),
            fallback_used=any(
                item.event_type == "model" and item.fallback_reason
                for item in artifacts.run_trace.observations
            ),
            confirmation_draft=artifacts.confirmation_draft,
        )

    def _metrics(
        self,
        cases: Sequence[RealLLMCaseResult],
    ) -> tuple[RealLLMMetric, ...]:
        total = len(cases)
        usage = [item for item in cases if item.token_usage_available]
        costs = [item.cost_usd for item in cases if item.cost_usd is not None]
        real_provider = [
            item
            for item in cases
            if item.effective_provider == self.configuration.model_provider
            and not item.fallback_used
        ]
        return (
            self._ratio(
                "deterministic_contract_pass_rate",
                sum(item.task_success for item in cases),
                total,
                "ratio",
                "All nine deterministic graders pass; not human answer quality.",
            ),
            self._ratio(
                "real_provider_effective_rate",
                len(real_provider),
                total,
                "ratio",
                "Fraction of cases whose final answer came from the configured real provider.",
            ),
            self._ratio(
                "fallback_rate",
                sum(item.fallback_used for item in cases),
                total,
                "ratio",
                "Fraction of cases that used deterministic fallback.",
            ),
            self._ratio(
                "token_usage_available_rate",
                len(usage),
                total,
                "ratio",
                "Fraction of calls with complete provider input/output/total usage.",
            ),
            self._mean(
                "average_input_tokens",
                [float(item.input_tokens) for item in usage if item.input_tokens is not None],
                "tokens",
                "Recorded provider usage only.",
            ),
            self._mean(
                "average_output_tokens",
                [float(item.output_tokens) for item in usage if item.output_tokens is not None],
                "tokens",
                "Recorded provider usage only.",
            ),
            self._mean(
                "average_total_tokens",
                [float(item.total_tokens) for item in usage if item.total_tokens is not None],
                "tokens",
                "Recorded provider usage only.",
            ),
            self._mean(
                "average_cost_usd",
                [float(value) for value in costs],
                "usd",
                "Requires complete usage and both configured prices.",
            ),
            self._mean(
                "workflow_latency_avg_ms",
                [float(item.workflow_latency_ms) for item in cases],
                "ms",
                "Local wall-clock latency for the full integration run.",
            ),
            self._percentile(
                "workflow_latency_p95_ms",
                [float(item.workflow_latency_ms) for item in cases],
                "Local wall-clock p95 for the full integration run.",
            ),
            self._percentile(
                "model_latency_p95_ms",
                [float(item.model_latency_ms) for item in cases],
                "Model call p95 from ModelGateway Trace.",
            ),
            self._mean(
                "human_reviewed_answer_quality",
                [],
                "ratio",
                "N/A until badcases and the reviewed answer set are completed.",
            ),
        )

    @staticmethod
    def calculate_cost(
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        pricing: ModelPricing,
    ) -> float | None:
        if (
            input_tokens is None
            or output_tokens is None
            or pricing.input_price_per_1m_usd is None
            or pricing.output_price_per_1m_usd is None
        ):
            return None
        return round(
            input_tokens / 1_000_000 * pricing.input_price_per_1m_usd
            + output_tokens / 1_000_000 * pricing.output_price_per_1m_usd,
            10,
        )

    @staticmethod
    def _ratio(
        name: str,
        numerator: int,
        denominator: int,
        unit: str,
        note: str,
    ) -> RealLLMMetric:
        return RealLLMMetric(
            name=name,
            value=(numerator / denominator if denominator else None),
            status="measured" if denominator else "not_available",
            sample_count=denominator,
            unit=unit,
            note=note,
        )

    @staticmethod
    def _mean(
        name: str,
        values: list[float],
        unit: str,
        note: str,
    ) -> RealLLMMetric:
        return RealLLMMetric(
            name=name,
            value=fmean(values) if values else None,
            status="measured" if values else "not_available",
            sample_count=len(values),
            unit=unit,
            note=note,
        )

    @staticmethod
    def _percentile(
        name: str,
        values: list[float],
        note: str,
    ) -> RealLLMMetric:
        if not values:
            return RealLLMMetric(
                name=name,
                value=None,
                status="not_available",
                sample_count=0,
                unit="ms",
                note=note,
            )
        ordered = sorted(values)
        index = max(0, (95 * len(ordered) + 99) // 100 - 1)
        return RealLLMMetric(
            name=name,
            value=ordered[index],
            status="measured",
            sample_count=len(values),
            unit="ms",
            note=note,
        )

    @staticmethod
    def render_markdown(report: RealLLMBenchmarkReport) -> str:
        lines = [
            "# 4D-B3 Real LLM Benchmark",
            "",
            f"- Status: `{report.status}`",
            f"- Provider: `{report.provider_name}`",
            f"- Model: `{report.model_name}`",
            f"- Split: `{report.dataset_split}`",
            f"- Samples: `{report.sample_count}`",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Status | Samples | Unit | Note |",
            "|---|---:|---|---:|---|---|",
        ]
        for metric in report.metrics:
            value = "N/A" if metric.value is None else f"{metric.value:.6f}"
            lines.append(
                f"| {metric.name} | {value} | {metric.status} | {metric.sample_count} | {metric.unit} | {metric.note} |"
            )
        if report.status == "completed":
            lines.extend(
                [
                    "",
                    "## Human Review Freeze",
                    "",
                    f"- Reviewed samples: `{report.reviewed_sample_count}`",
                    f"- Reviewed pass: `{report.reviewed_pass_count}`",
                    f"- Reviewed fail: `{report.reviewed_fail_count}`",
                    f"- Review queue SHA-256: `{report.review_queue_sha256 or 'missing'}`",
                ]
            )
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def render_review_queue(report: RealLLMBenchmarkReport) -> str:
        lines = [
            "# 4D-B3 Badcase Review Queue",
            "",
            f"- Report: `{report.report_id}`",
            f"- Items: `{len(report.review_items)}`",
            (
                "- Human review is frozen in this completed report."
                if report.status == "completed"
                else "- Review status is pending until a human checks the answer."
            ),
            "",
        ]
        for item in report.review_items:
            lines.extend(
                [
                    f"## {item.query_id}",
                    "",
                    f"- Automatic task success: `{item.automatic_task_success}`",
                    f"- Automatic failure reasons: `{', '.join(item.automatic_failure_reasons) or 'none'}`",
                    f"- Provider: `{item.effective_provider or 'none'}`",
                    f"- Fallback used: `{item.fallback_used}`",
                    f"- Review status: `{item.review_status}`",
                    f"- Reviewer notes: `{item.reviewer_notes or 'none'}`",
                    f"- Expected member: `{item.expected_member_id}`",
                    f"- Expected intent: `{item.expected_intent}`",
                    f"- Expected confirmation: `{item.expected_human_confirmation_required}`",
                    "",
                    "### User input",
                    "",
                    item.user_input,
                    "",
                    "### Final answer",
                    "",
                    item.final_answer or "(empty answer)",
                    "",
                    "### Confirmation draft evidence",
                    "",
                    (
                        "```json\n"
                        + json.dumps(
                            item.confirmation_draft.model_dump(mode="json"),
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n```"
                        if item.confirmation_draft is not None
                        else "No local confirmation draft snapshot was captured."
                    ),
                    "",
                    "### Human review",
                    "",
                    "- [ ] Facts match the allowed evidence",
                    "- [ ] Member scope is correct",
                    "- [ ] Safety and confirmation wording is correct",
                    "- [ ] No forbidden phrase or unsupported claim",
                    "- [ ] Mark `review_status` in the JSON queue",
                    "",
                ]
            )
        return "\n".join(lines)


__all__ = [
    "ModelPricing",
    "RealLLMFinalizationError",
    "RealLLMFinalManifest",
    "RealLLMCaseResult",
    "RealLLMBenchmarkReport",
    "RealLLMBenchmarkRunner",
    "RealLLMMetric",
    "RealLLMReviewItem",
]

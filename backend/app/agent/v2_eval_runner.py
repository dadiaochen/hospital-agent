"""Unified local evaluation runner for the 4D-B2.5 benchmark.

The runner composes four deliberately small pieces:

1. the versioned WorldState/Query fixtures;
2. an isolated materializer;
3. an executor that returns frozen ``V2RunArtifacts``; and
4. nine deterministic graders plus report aggregation.

The default executor is a synthetic Gold projection.  It proves the runner
contract and is useful for grader tests.  It must not be described as an
application-quality score until an integration executor runs the real graph
against PostgreSQL, Provider sandbox state and the RAG index.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID, uuid5

from app.agent.final_claim_schemas import AnswerEnvelope
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RAGTrace,
    RunTrace,
    SafetyTrace,
    ToolCallTrace,
)
from app.agent.v2_benchmark_generator import (
    V2BenchmarkDataError,
    load_v2_benchmark,
)
from app.agent.v2_benchmark_schemas import (
    DatasetSplit,
    EvalQueryVariant,
    EvalWorldState,
    V2BenchmarkManifest,
    V2QueryDataset,
    V2WorldStateDataset,
)
from app.agent.v2_eval_schemas import (
    ConfirmationDraftSnapshot,
    V2CaseEvaluation,
    V2EvalReport,
    V2Metric,
    V2RunArtifacts,
    V2RunnerOptions,
)
from app.agent.v2_graders import V2DeterministicGraders, V2GradingContext
from app.agent.v2_materializer import MaterializedCase, WorldStateMaterializer
from app.agent.v2_integration import (
    PostgresMaterializedCase,
    PostgresV2Materializer,
)


_RUN_NAMESPACE = UUID("e2ddcc8d-5427-4222-8a29-5f6a2b4e8d2f")
_REPORT_NAMESPACE = UUID("9d2c09e4-72ac-4ed6-9b44-872c9a9b2513")


class V2RunExecutor(Protocol):
    """Adapter boundary for synthetic or future real graph execution."""

    def execute(
        self,
        materialized: MaterializedCase | PostgresMaterializedCase,
        *,
        repeat_index: int,
    ) -> V2RunArtifacts:
        ...


class V2Materializer(Protocol):
    def materialize(
        self, world: EvalWorldState, query: EvalQueryVariant
    ) -> MaterializedCase | PostgresMaterializedCase: ...

    def cleanup(
        self, materialized: MaterializedCase | PostgresMaterializedCase
    ): ...


class SyntheticProjectionExecutor:
    """Create a valid frozen trace from Gold without external side effects."""

    def execute(
        self, materialized: MaterializedCase, *, repeat_index: int
    ) -> V2RunArtifacts:
        world = materialized.world
        query = materialized.query
        gold = world.gold
        run_id = str(uuid5(_RUN_NAMESPACE, f"{query.query_id}:{repeat_index}"))
        expected_sources = tuple(query.expected_sources)
        source_owner = self._source_owners(world)

        tool_calls: list[ToolCallTrace] = []
        for index, tool_name in enumerate(query.expected_required_tools):
            source_id = (
                expected_sources[index] if index < len(expected_sources) else None
            )
            tool_calls.append(
                ToolCallTrace(
                    tool_name=tool_name,
                    member_id=query.expected_member_id,
                    tool_input=self._projected_tool_input(query, index),
                    source_id=source_id,
                    source_name=f"synthetic:{tool_name}",
                    success=source_id is not None,
                    schema_valid=True,
                    evidence_present=source_id is not None,
                )
            )

        used_by_tool = {
            call.source_id for call in tool_calls if call.source_id is not None
        }
        rag_traces = tuple(
            RAGTrace(
                source_id=source_id,
                source_name="synthetic:materialized-source",
                member_id=source_owner.get(source_id),
                retrieved=True,
                schema_valid=True,
            )
            for source_id in expected_sources
            if source_id not in used_by_tool
        )

        waiting = gold.expected_confirmation_required
        if query.expected_final_status == "failed":
            content = "No source-backed answer is available; the request was stopped safely."
        elif gold.expected_blocked:
            content = "The request is blocked pending a safety review."
        elif waiting:
            content = "A local draft is ready and is awaiting user confirmation."
        else:
            content = "The task result was prepared from frozen evidence and source references."

        answer_id = str(uuid5(_RUN_NAMESPACE, f"answer:{run_id}"))
        context_source_ids = expected_sources
        answer_envelope = AnswerEnvelope(
            answer_id=answer_id,
            run_id=run_id,
            task_id=query.query_id,
            member_id=query.expected_member_id,
            display_text=content,
            claims=tuple(gold.required_claims),
            waiting_for_user_confirmation=waiting,
            human_confirmation_present=False,
            action_status="awaiting_confirmation" if waiting else "none",
            context_source_ids=context_source_ids,
            dependency_result_ids=tuple(gold.expected_domain_steps),
        )
        trace = RunTrace(
            trace_schema_version="4d-b2.3",
            case_id=query.query_id,
            run_id=run_id,
            task_id=query.query_id,
            user_id=world.user.user_id,
            member_id=query.expected_member_id,
            intent=query.expected_intent,
            tool_calls=tuple(tool_calls),
            rag_traces=rag_traces,
            safety_trace=SafetyTrace(
                member_id=query.expected_member_id,
                flags=tuple(query.expected_safety_flags),
                blocked=gold.expected_blocked,
                requires_human_confirmation=waiting,
            ),
            final_answer=FinalAnswerTrace(
                answer_id=answer_id,
                content=content,
                contains_factual_claims=bool(gold.required_claims),
                waiting_for_user_confirmation=waiting,
                human_confirmation_present=False,
                action_status="awaiting_confirmation" if waiting else "none",
                answer_envelope=answer_envelope,
            ),
            context_source_ids=context_source_ids,
            dependency_result_ids=tuple(gold.expected_domain_steps),
            latency_ms=10 + len(tool_calls) * 3 + len(rag_traces) * 2,
            schema_valid=True,
        )

        fault = world.fault_injection
        retry_count = 1 if fault.enabled and fault.retryable else 0
        provider_attempts = 0 if fault.fault_type == "no_source" else 1 + retry_count
        if fault.enabled:
            fallback_action = fault.expected_fallback
        else:
            fallback_action = "none"
        if "local_confirmation_draft" in gold.expected_database_changes:
            external_action_status = "local_draft"
        elif fault.fault_type == "confirmation_race":
            external_action_status = "idempotent_replay"
        else:
            external_action_status = "none"
        confirmation_draft = None
        if "local_confirmation_draft" in gold.expected_database_changes:
            action_type = {
                "refill": "refill_request",
                "reminder": "reminder_create",
                "pharmacy": "pharmacy_option",
            }.get(query.expected_intent, "health_record")
            confirmation_draft = ConfirmationDraftSnapshot(
                draft_id=f"synthetic-draft:{run_id}",
                task_id=query.query_id,
                member_id=query.expected_member_id,
                action_type=action_type,
                status="DRAFT",
                draft_version=1,
                need_human_confirmation=True,
                local_only=True,
                external_action_status="not_submitted",
                summary="A local reminder draft is ready and awaits confirmation.",
                preview=(
                    {"schedule": {"frequency": "daily", "time": "08:00"}}
                    if action_type == "reminder_create"
                    else {}
                ),
            )
        return V2RunArtifacts(
            run_trace=trace,
            route_mode=query.expected_route,
            observed_intent=query.expected_intent,
            observed_agent_roles=tuple(query.expected_agent_roles),
            observed_domain_steps=tuple(gold.expected_domain_steps),
            observed_domain_dependency_edges=tuple(
                gold.expected_domain_dependency_edges
            ),
            observed_governance_steps=tuple(gold.expected_governance_steps),
            observed_governance_edges=tuple(gold.expected_governance_edges),
            observed_tool_names=tuple(query.expected_required_tools),
            observed_blocked=gold.expected_blocked,
            observed_source_ids=expected_sources,
            observed_rag_source_ids=tuple(rag.source_id for rag in rag_traces),
            observed_database_changes=tuple(gold.expected_database_changes),
            confirmation_draft=confirmation_draft,
            provider_attempts=provider_attempts,
            retry_count=retry_count,
            fallback_action=fallback_action,
            external_action_status=external_action_status,
            checkpoint_restored=False,
            foreign_member_ids=(),
            cleanup_succeeded=False,
        )

    @staticmethod
    def _projected_tool_input(query: EvalQueryVariant, index: int) -> dict[str, object]:
        if index >= len(query.expected_tool_invocations):
            return {}
        expected = query.expected_tool_invocations[index]
        payload = dict(expected.exact_parameters)
        for key, rule in expected.parameter_rules.items():
            if rule.get("match") == "non_empty_semantic_query":
                payload[key] = query.user_input
        return payload

    @staticmethod
    def _source_owners(world: EvalWorldState) -> dict[str, str]:
        owners: dict[str, str] = {}
        for member in world.members:
            owners[member.profile_source_id] = member.member_id
        for item in (*world.prescriptions, *world.medicine_box, *world.health_records):
            owners[item.source_id] = item.member_id
        return owners


class V2EvalRunner:
    """Load, materialize, execute, grade, clean and aggregate v2 cases."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        materializer: V2Materializer | None = None,
        graders: V2DeterministicGraders | None = None,
        executor: V2RunExecutor | None = None,
        dataset_loader: Callable[..., tuple[
            V2WorldStateDataset, V2QueryDataset, V2BenchmarkManifest
        ]] = load_v2_benchmark,
    ) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.materializer = materializer or WorldStateMaterializer()
        self.graders = graders or V2DeterministicGraders()
        self.executor = executor or SyntheticProjectionExecutor()
        self.dataset_loader = dataset_loader
        self._automatic_gold_mode = False

    def run(self, options: V2RunnerOptions | None = None) -> V2EvalReport:
        options = options or V2RunnerOptions()
        if options.runner_mode == "integration" and isinstance(
            self.materializer, WorldStateMaterializer
        ):
            raise V2BenchmarkDataError(
                "integration mode requires PostgresV2Materializer and a real graph executor"
            )
        if options.runner_mode == "integration" and isinstance(
            self.executor, SyntheticProjectionExecutor
        ):
            raise V2BenchmarkDataError(
                "integration mode cannot use SyntheticProjectionExecutor"
            )
        worlds, queries, manifest = self.dataset_loader(project_root=self.project_root)
        self._automatic_gold_mode = (
            manifest.dataset_version == "internet-hospital-agent-eval-v1"
        )
        self._ensure_review_gate(worlds, queries, manifest, options)
        selected = self._select_queries(queries, options)
        world_by_id = {world.world_state_id: world for world in worlds.world_states}
        def run_query_group(query: EvalQueryVariant) -> list[V2CaseEvaluation]:
            world = world_by_id[query.world_state_id]
            # The materializer namespace is intentionally derived from query_id.
            # Keep repeats of one query serial while other independent Query
            # groups use their own PostgreSQL transaction/session in parallel.
            return [
                self._run_one(world, query, repeat_index)
                for repeat_index in range(options.repeat)
            ]

        if options.concurrency == 1 or len(selected) <= 1:
            grouped_results = [run_query_group(query) for query in selected]
        else:
            with ThreadPoolExecutor(
                max_workers=min(options.concurrency, len(selected)),
                thread_name_prefix="agent-eval",
            ) as pool:
                # executor.map preserves selected Query order even though work
                # completes out of order, which keeps reports and hashes stable.
                grouped_results = list(pool.map(run_query_group, selected))
        results = [item for group in grouped_results for item in group]
        status = (
            "completed"
            if manifest.dataset_version == "internet-hospital-agent-eval-v1"
            else "preview"
            if worlds.review_status == "pending_review"
            else "completed"
        )
        report = V2EvalReport(
            report_id=self._report_id(options, selected),
            dataset_version=manifest.dataset_version,
            runner_mode=options.runner_mode,
            status=status,
            dataset_split=options.dataset_split,
            generated_at=datetime.now(timezone.utc),
            sample_count=len(results),
            case_results=tuple(results),
            metrics=self._metrics(
                results,
                status=status,
                unified=manifest.dataset_version == "internet-hospital-agent-eval-v1",
            ),
            failure_counts=self._failure_counts(results),
            world_states_sha256=manifest.world_states_sha256,
            queries_sha256=manifest.queries_sha256,
            notes=self._report_notes(
                options.runner_mode,
                unified=manifest.dataset_version == "internet-hospital-agent-eval-v1",
                concurrency=options.concurrency,
            ),
        )
        return report

    def write_report(
        self, report: V2EvalReport, *, output_dir: Path
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "preview" if report.runner_mode == "synthetic_projection" else "integration"
        dataset_label = (
            "unified"
            if report.dataset_version == "internet-hospital-agent-eval-v1"
            else "v2"
        )
        json_path = output_dir / f"agent_eval_report.{dataset_label}.{suffix}.json"
        markdown_path = output_dir / f"agent_eval_report.{dataset_label}.{suffix}.md"
        json_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(self.render_markdown(report), encoding="utf-8")
        return json_path, markdown_path

    @staticmethod
    def render_markdown(report: V2EvalReport) -> str:
        title = (
            "# Unified Agent Evaluation Report"
            if report.dataset_version == "internet-hospital-agent-eval-v1"
            else "# 4D-B2.5 v2 Evaluation Report"
            if report.runner_mode == "synthetic_projection"
            else "# 4D-B2.6 v2 Integration Evaluation Report"
        )
        lines = [
            title,
            "",
            f"- Status: `{report.status}`",
            f"- Runner: `{report.runner_mode}`",
            f"- Dataset: `{report.dataset_version}`",
            f"- Split: `{report.dataset_split}`",
            f"- Samples: `{report.sample_count}`",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Samples | Status |",
            "|---|---:|---:|---|",
        ]
        lines.extend(
            f"| {metric.name} | {metric.value:.4f} | {metric.sample_count} | {metric.status} |"
            for metric in report.metrics
        )
        lines.extend(["", "## Failure Reasons", ""])
        if report.failure_counts:
            lines.extend(
                f"- `{reason}`: {count}"
                for reason, count in sorted(report.failure_counts.items())
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)
        lines.extend(
            [
                "",
                (
                    "This is a local preview generated from deterministic Gold projection. "
                    "It is not evidence of real application quality."
                    if report.runner_mode == "synthetic_projection"
                    else "This report is integration evidence only after Docker, reviewed data, "
                    "identity/source mapping and cleanup checks pass. It is not a production SLO."
                ),
                "",
            ]
        )
        return "\n".join(lines)

    def _run_one(
        self, world: EvalWorldState, query: EvalQueryVariant, repeat_index: int
    ) -> V2CaseEvaluation:
        materialized: MaterializedCase | None = None
        cleanup_succeeded = False
        try:
            materialized = self.materializer.materialize(world, query)
            artifacts = self.executor.execute(
                materialized, repeat_index=repeat_index
            )
            grades = self.graders.grade(
                V2GradingContext(world=world, query=query, artifacts=artifacts)
            )
            failure_reasons = tuple(
                dict.fromkeys(
                    reason
                    for grade in grades
                    for reason in grade.failure_reasons
                )
            )
            tool_grade = next(grade for grade in grades if grade.grader == "tool")
            route_grade = next(grade for grade in grades if grade.grader == "route")
            claim_grade = next(grade for grade in grades if grade.grader == "claim")
            rag_grade = next(grade for grade in grades if grade.grader == "rag")
            safety_grade = next(grade for grade in grades if grade.grader == "safety")
            expected_tools = set(tool_grade.details.get("expected_tools", ()))
            observed_tools = set(tool_grade.details.get("observed_tools", ()))
            tool_call_correct = (
                expected_tools == observed_tools
                and "tool.trace_set_mismatch" not in tool_grade.failure_reasons
            )
            tool_parameter_correct = bool(
                tool_grade.details.get("parameter_match", False)
            )
            parameter_details = tuple(
                item
                for item in tool_grade.details.get("parameter_details", ())
                if isinstance(item, dict)
            )
            matched_parameter_call_count = sum(
                bool(item.get("call_present")) for item in parameter_details
            )
            correct_parameter_call_count = sum(
                bool(item.get("call_present")) and bool(item.get("matched"))
                for item in parameter_details
            )
            cleanup_receipt = self.materializer.cleanup(materialized)
            cleanup_succeeded = cleanup_receipt.cleanup_succeeded
            if not cleanup_succeeded:
                raise V2BenchmarkDataError(
                    f"evaluation namespace cleanup failed: {cleanup_receipt.namespace}"
                )
            return V2CaseEvaluation(
                query_id=query.query_id,
                world_state_id=world.world_state_id,
                dataset_split=query.dataset_split,
                run_id=artifacts.run_trace.run_id,
                task_success=not failure_reasons,
                intent_correct=(
                    route_grade.details.get("observed_intent")
                    == route_grade.details.get("expected_intent")
                ),
                route_correct=(
                    route_grade.details.get("observed_route")
                    == route_grade.details.get("expected_route")
                ),
                tool_call_correct=tool_call_correct,
                tool_parameter_correct=tool_parameter_correct,
                matched_parameter_call_count=matched_parameter_call_count,
                correct_parameter_call_count=correct_parameter_call_count,
                final_answer_correct=(
                    claim_grade.passed and rag_grade.passed and safety_grade.passed
                ),
                expected_blocked=query.expected_blocked,
                observed_blocked=artifacts.observed_blocked,
                tool_calls=artifacts.run_trace.tool_calls,
                layer_grades=grades,
                failure_reasons=failure_reasons,
                latency_ms=artifacts.run_trace.latency_ms,
                materialization_backend=cleanup_receipt.backend,
                cleanup_succeeded=cleanup_succeeded,
                review_status=(
                    "automatic_gold"
                    if self._automatic_gold_mode
                    else "pending_review"
                ),
            )
        finally:
            if materialized is not None and not cleanup_succeeded:
                self.materializer.cleanup(materialized)

    @staticmethod
    def _report_notes(
        runner_mode: str, *, unified: bool = False, concurrency: int = 1
    ) -> tuple[str, ...]:
        concurrency_note = (
            "independent Query groups use bounded concurrency="
            f"{concurrency}; each Query keeps its own materialization, "
            "transaction and deterministic result order"
        )
        if unified and runner_mode == "integration":
            return (
                "integration mode executes UnifiedHealthGraph inside isolated "
                "PostgreSQL transactions",
                "the unified dataset is synthetic, test-only and intentionally "
                "has no manual review gate",
                concurrency_note,
                "completed means all selected Queries ran; it is not clinical "
                "evidence or a production SLO",
            )
        if runner_mode == "integration":
            return (
                "integration mode executes the UnifiedHealthGraph inside a PostgreSQL transaction",
                "Provider and RAG observations must come from the configured runtime adapters",
                "reviewed WorldState data and a successful cleanup are required before formal metrics",
                concurrency_note,
            )
        return (
            "synthetic_projection does not call PostgreSQL, Provider, RAG or LLM",
            "preview metrics are pipeline checks, not final resume metrics",
            concurrency_note,
        )

    @staticmethod
    def _ensure_review_gate(
        worlds: V2WorldStateDataset,
        queries: V2QueryDataset,
        manifest: V2BenchmarkManifest,
        options: V2RunnerOptions,
    ) -> None:
        # ``internet-hospital-agent-eval-v1`` is the single synthetic test
        # dataset. Its Gold labels are generated from frozen business state,
        # so running it must never require a manual review switch. Keep the
        # old review gate only for the shelved legacy v2 fixtures.
        if manifest.dataset_version == "internet-hospital-agent-eval-v1":
            return
        if worlds.review_status != queries.review_status:
            raise V2BenchmarkDataError("WorldState and Query review status mismatch")
        if manifest.review_status != worlds.review_status:
            raise V2BenchmarkDataError("manifest review status mismatch")
        if worlds.review_status == "pending_review" and not options.allow_pending_review:
            raise V2BenchmarkDataError(
                "v2 benchmark is pending human review; pass allow_pending_review=True "
                "for a preview only"
            )

    @staticmethod
    def _select_queries(
        queries: V2QueryDataset, options: V2RunnerOptions
    ) -> tuple[EvalQueryVariant, ...]:
        by_id = {query.query_id: query for query in queries.queries}
        if options.query_ids:
            unknown = set(options.query_ids) - set(by_id)
            if unknown:
                raise V2BenchmarkDataError(
                    "unknown query IDs: " + ", ".join(sorted(unknown))
                )
            selected = [by_id[query_id] for query_id in options.query_ids]
        else:
            selected = list(queries.queries)
            if options.dataset_split != "all":
                selected = [
                    query
                    for query in selected
                    if query.dataset_split == options.dataset_split
                ]
        if options.max_cases is not None:
            selected = selected[: options.max_cases]
        return tuple(selected)

    @staticmethod
    def _report_id(
        options: V2RunnerOptions, selected: tuple[EvalQueryVariant, ...]
    ) -> str:
        selection = ":".join(query.query_id for query in selected)
        return str(
            uuid5(
                _REPORT_NAMESPACE,
                f"{options.dataset_split}:{options.runner_mode}:{options.repeat}:{selection}",
            )
        )

    @staticmethod
    def _metrics(
        results: list[V2CaseEvaluation], *, status: str, unified: bool = False
    ) -> tuple[V2Metric, ...]:
        sample_count = len(results)
        if not sample_count:
            return ()
        if unified:
            return V2EvalRunner._unified_metrics(results, status=status)
        metrics: list[V2Metric] = [
            V2Metric(
                name="task_success_rate",
                value=sum(result.task_success for result in results) / sample_count,
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="fraction of cases passing all nine deterministic graders",
            ),
            V2Metric(
                name="avg_latency_ms",
                value=sum(result.latency_ms for result in results) / sample_count,
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="synthetic trace latency; not a production latency measurement",
            ),
            V2Metric(
                name="p95_latency_ms",
                value=float(
                    V2EvalRunner._percentile(
                        [result.latency_ms for result in results], 0.95
                    )
                ),
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="nearest-rank percentile of synthetic trace latency",
            ),
        ]
        for layer in V2DeterministicGraders.LAYER_ORDER:
            passed = sum(
                any(
                    grade.grader == layer and grade.passed
                    for grade in result.layer_grades
                )
                for result in results
            )
            metrics.append(
                V2Metric(
                    name=f"{layer}_pass_rate",
                    value=passed / sample_count,
                    sample_count=sample_count,
                    status=status,  # type: ignore[arg-type]
                    note=f"fraction passing the {layer} grader",
                )
            )
        return tuple(metrics)

    @staticmethod
    def _unified_metrics(
        results: list[V2CaseEvaluation], *, status: str
    ) -> tuple[V2Metric, ...]:
        sample_count = len(results)
        latencies = [result.latency_ms for result in results]
        high_risk = [result for result in results if result.expected_blocked]
        ordinary = [result for result in results if not result.expected_blocked]
        matched_parameter_calls = sum(
            item.matched_parameter_call_count for item in results
        )
        correct_parameter_calls = sum(
            item.correct_parameter_call_count for item in results
        )

        def ratio(name: str, passed: int, total: int, note: str) -> V2Metric:
            return V2Metric(
                name=name,
                value=passed / total if total else 0.0,
                sample_count=total,
                status=status,  # type: ignore[arg-type]
                note=note,
            )

        return (
            ratio(
                "intent_accuracy",
                sum(item.intent_correct for item in results),
                sample_count,
                "observed intent exact match against unified Gold",
            ),
            ratio(
                "route_accuracy",
                sum(item.route_correct for item in results),
                sample_count,
                "single-domain/direct or complex/cross-domain exact match",
            ),
            ratio(
                "tool_call_accuracy",
                sum(item.tool_call_correct for item in results),
                sample_count,
                "expected and observed tool capability sets exact match",
            ),
            ratio(
                "tool_parameter_accuracy",
                correct_parameter_calls,
                matched_parameter_calls,
                "normalized exact/rule match among expected tools that were actually called",
            ),
            ratio(
                "final_answer_accuracy",
                sum(item.final_answer_correct for item in results),
                sample_count,
                "claim, source binding and safety answer contracts all pass",
            ),
            ratio(
                "end_to_end_task_success_rate",
                sum(item.task_success for item in results),
                sample_count,
                "all deterministic hard gates pass",
            ),
            ratio(
                "high_risk_block_rate",
                sum(item.observed_blocked for item in high_risk),
                len(high_risk),
                "correctly blocked high-risk tasks / expected high-risk tasks",
            ),
            ratio(
                "high_risk_false_block_rate",
                sum(item.observed_blocked for item in ordinary),
                len(ordinary),
                "incorrectly blocked ordinary tasks / expected ordinary tasks",
            ),
            V2Metric(
                name="latency_p50_ms",
                value=float(V2EvalRunner._percentile(latencies, 0.50)),
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="local wall-clock nearest-rank percentile",
            ),
            V2Metric(
                name="latency_p95_ms",
                value=float(V2EvalRunner._percentile(latencies, 0.95)),
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="local wall-clock nearest-rank percentile",
            ),
            V2Metric(
                name="latency_p99_ms",
                value=float(V2EvalRunner._percentile(latencies, 0.99)),
                sample_count=sample_count,
                status=status,  # type: ignore[arg-type]
                note="local wall-clock nearest-rank percentile",
            ),
        )

    @staticmethod
    def _failure_counts(results: list[V2CaseEvaluation]) -> dict[str, int]:
        counts: Counter[str] = Counter(
            reason for result in results for reason in result.failure_reasons
        )
        return dict(sorted(counts.items()))

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int:
        values = sorted(values)
        index = max(0, min(len(values) - 1, int(len(values) * percentile + 0.9999) - 1))
        return values[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 4D-B2.5 v2 preview")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--split", choices=("all", "development", "validation", "holdout"), default="all")
    parser.add_argument("--max-cases", type=int, default=10)
    parser.add_argument("--allow-pending-review", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("output/benchmarks/v2"))
    args = parser.parse_args()
    runner = V2EvalRunner(project_root=args.project_root)
    report = runner.run(
        V2RunnerOptions(
            dataset_split=args.split,
            max_cases=args.max_cases,
            allow_pending_review=args.allow_pending_review,
        )
    )
    paths = runner.write_report(report, output_dir=args.output_dir)
    print(f"report: {paths[0]}")
    print(f"markdown: {paths[1]}")
    print(f"status: {report.status}; samples: {report.sample_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SyntheticProjectionExecutor",
    "V2EvalRunner",
    "V2RunExecutor",
]

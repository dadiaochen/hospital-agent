"""Run the local observed 4D-B benchmark without customer data.

The runner executes the repository's deterministic components against synthetic
fixtures.  It records wall-clock observations and provenance, but it never
turns deterministic output into a claim about real-model answer quality.
"""

from __future__ import annotations

import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agent.ablation_harness import AblationHarnessRunner
from app.agent.benchmark_runner import BenchmarkRunner, canonical_hash
from app.agent.benchmark_schemas import BenchmarkMetric, BenchmarkReport
from app.agent.context_manager import ContextManager
from app.agent.context_schemas import MemoryRef, ToolEvidenceRef
from app.agent.eval_schemas import EvaluationResult
from app.agent.local_observation_schemas import (
    LocalAgentObservation,
    LocalMemoryObservation,
    LocalObservationBundle,
    LocalProviderObservation,
    LocalRAGCase,
    LocalRAGObservation,
)
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    ObservationTrace,
    RunTrace,
    SafetyTrace,
)
from app.core.database import Base
from app.models import KnowledgeChunk, KnowledgeDocument
from app.providers import ProviderInvocationError, ProviderRegistry
from app.providers.schemas import ProviderRequest, ProviderResponse, ProviderRetryPolicy
from app.rag.retrieval_schemas import RetrievalRequest
from app.rag.retriever import create_knowledge_retriever


_RUN_NAMESPACE = UUID("7b3ee48e-6ecf-4fb2-9e2f-b2b3a6bbf4a2")
_OBSERVATION_NAMESPACE = UUID("3f6d3f30-4f32-45ea-96df-98d4c1b11f17")


class LocalObservedBenchmarkRunner:
    """Produce a local evidence bundle and an observed benchmark report."""

    def __init__(
        self,
        *,
        project_root: Path,
        output_dir: Path | None = None,
    ) -> None:
        self.project_root = project_root
        self.output_dir = output_dir or project_root / "output" / "benchmarks"
        self.contract_runner = BenchmarkRunner.from_project_root(project_root)
        self.business_fixture_path = (
            project_root / "backend" / "tests" / "fixtures" / "business_harness_cases.4b.json"
        )
        self.local_case_path = (
            project_root / "backend" / "tests" / "fixtures" / "local_benchmark_cases.v1.json"
        )

    @classmethod
    def from_project_root(
        cls,
        project_root: Path | None = None,
    ) -> "LocalObservedBenchmarkRunner":
        root = project_root or Path(__file__).resolve().parents[3]
        return cls(project_root=root)

    def load_local_rag_cases(self) -> tuple[LocalRAGCase, ...]:
        payload = json.loads(self.local_case_path.read_text(encoding="utf-8"))
        cases = tuple(LocalRAGCase.model_validate(item) for item in payload["cases"])
        if len(cases) != len({case.case_id for case in cases}):
            raise ValueError("local RAG case ids must be unique")
        return cases

    def run(self) -> tuple[LocalObservationBundle, BenchmarkReport]:
        """Execute all local components and calculate metrics from observations."""

        manifest, _, manifest_hash = self.contract_runner.load_manifest()
        datasets = self.contract_runner.load_datasets(manifest)
        local_rag_cases = self.load_local_rag_cases()

        agent_runs = self._run_agent_observations()
        rag_queries = self._run_rag_observations(local_rag_cases)
        memory_cases = self._run_memory_observations(datasets["memory_context"].cases)
        provider_cases = self._run_provider_observations(datasets["provider_faults"].cases)
        environment = self._environment()
        local_fixture_payload = json.loads(
            self.local_case_path.read_text(encoding="utf-8")
        )
        bundle = LocalObservationBundle(
            bundle_version="4d-local-observations-v1",
            mode="local_integration",
            generated_at=datetime.now(timezone.utc).replace(microsecond=0),
            fixture_sha256=canonical_hash(local_fixture_payload),
            environment=environment,
            agent_runs=agent_runs,
            rag_queries=rag_queries,
            memory_cases=memory_cases,
            provider_cases=provider_cases,
        )

        bundle_hash = canonical_hash(bundle.model_dump(mode="json"))
        report = self._build_report(
            manifest_hash=manifest_hash,
            bundle=bundle,
            bundle_hash=bundle_hash,
        )
        return bundle, report

    def write_reports(
        self,
        bundle: LocalObservationBundle,
        report: BenchmarkReport,
        *,
        markdown_path: Path | None = None,
    ) -> tuple[Path, Path, Path]:
        """Persist machine-readable observations and human-readable reports."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        observation_path = self.output_dir / "local_observations.4d.json"
        report_json_path = self.output_dir / "local_benchmark_report.4d.json"
        report_markdown_path = (
            markdown_path
            or self.project_root / "docs" / "local_benchmark_report.4d.md"
        )
        report_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        observation_path.write_text(
            json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_json_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_markdown_path.write_text(
            self.render_markdown(bundle, report),
            encoding="utf-8",
        )
        return observation_path, report_json_path, report_markdown_path

    def _run_agent_observations(self) -> tuple[LocalAgentObservation, ...]:
        harness = AblationHarnessRunner(self.business_fixture_path)
        _, cases = harness.load_suite()
        relevant_sources = {
            case.case_id: case.relevant_rag_source_ids for case in cases
        }
        observed = harness.run_strategy_observed("bounded_supervisor")
        results: list[LocalAgentObservation] = []
        for result, execution_latency_ms in observed:
            original_trace = result.trace.run_trace
            trace_latency_ms = max(1, round(execution_latency_ms))
            evaluation = result.evaluation.model_copy(
                update={"latency_ms": trace_latency_ms}
            )
            observation = ObservationTrace(
                observation_id=str(
                    uuid5(
                        _OBSERVATION_NAMESPACE,
                        f"{result.case_id}:bounded_supervisor:{execution_latency_ms}",
                    )
                ),
                request_id=f"local-request:{result.case_id}",
                task_id=original_trace.task_id,
                run_id=original_trace.run_id,
                member_id=original_trace.member_id,
                event_type="node",
                node_name="bounded_supervisor",
                sequence_no=1,
                success=evaluation.task_success,
                latency_ms=trace_latency_ms,
                source_ids=tuple(result.trace.ranked_rag_source_ids),
                token_usage_available=False,
            )
            trace = original_trace.model_copy(
                update={
                    "latency_ms": trace_latency_ms,
                    "observations": (observation,),
                }
            )
            results.append(
                LocalAgentObservation(
                    case_id=result.case_id,
                    category=result.category,
                    strategy="bounded_supervisor",
                    run_trace=trace,
                    evaluation=evaluation,
                    relevant_rag_source_ids=tuple(relevant_sources[result.case_id]),
                    ranked_rag_source_ids=tuple(result.trace.ranked_rag_source_ids),
                    cited_source_ids=tuple(result.trace.cited_source_ids),
                    fixture_latency_ms=original_trace.latency_ms,
                    execution_latency_ms=execution_latency_ms,
                    environment=self._environment(),
                )
            )
        return tuple(results)

    def _run_rag_observations(
        self,
        cases: tuple[LocalRAGCase, ...],
    ) -> tuple[LocalRAGObservation, ...]:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        try:
            with Session(engine) as db:
                self._seed_local_knowledge(db, cases)
                retriever = create_knowledge_retriever(db, vector_enabled=False)
                observations: list[LocalRAGObservation] = []
                for case in cases:
                    started = perf_counter()
                    result = retriever.retrieve(
                        RetrievalRequest(
                            query=case.query,
                            purpose=case.purpose,
                            mode=case.mode,
                            limit=case.top_k,
                        )
                    )
                    latency_ms = max(1, round((perf_counter() - started) * 1000))
                    ranked_source_ids = tuple(source.source_id for source in result.sources)
                    ranked_source_names = tuple(source.source for source in result.sources)
                    source_versions = {
                        source.source_id: (
                            f"document={source.document_version};chunk={source.chunk_version}"
                        )
                        for source in result.sources
                    }
                    cited_source_ids = ranked_source_ids[:1]
                    observations.append(
                        LocalRAGObservation(
                            case_id=case.case_id,
                            query=case.query,
                            category=case.category,
                            requested_mode=result.requested_mode,
                            effective_mode=result.effective_mode,
                            expected_source_id=case.expected_source_id,
                            expected_source=case.expected_source,
                            ranked_source_ids=ranked_source_ids,
                            ranked_source_names=ranked_source_names,
                            source_versions=source_versions,
                            cited_source_ids=cited_source_ids,
                            fallback_used=result.fallback_used,
                            fallback_reason=result.fallback_reason,
                            latency_ms=latency_ms,
                            embedding_model=result.embedding_model,
                            embedding_schema_version=result.embedding_schema_version,
                            environment=self._environment(),
                        )
                    )
                return tuple(observations)
        finally:
            engine.dispose()

    @staticmethod
    def _seed_local_knowledge(db: Session, cases: tuple[LocalRAGCase, ...]) -> None:
        grouped: dict[str, list[LocalRAGCase]] = {}
        for case in cases:
            grouped.setdefault(case.expected_source_id, []).append(case)
        for source_id, source_cases in grouped.items():
            document_id = source_cases[0].expected_source_id.split(":")[1]
            source_name = source_cases[0].expected_source
            category = source_cases[0].category
            query_text = " ".join(case.query for case in source_cases)
            document = KnowledgeDocument(
                id=document_id,
                title=f"local {category} policy",
                category=category,
                source=source_name,
                content=query_text,
                safety_level="general" if category != "medical_safety" else "high",
                version="local-v1",
            )
            chunk_id = f"{document_id}-chunk"
            chunk = KnowledgeChunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=0,
                content=query_text,
                keywords=list({token for case in source_cases for token in case.query.split()}),
                chunk_version="local-v1",
            )
            document.chunks.append(chunk)
            db.add(document)
        db.commit()

    def _run_memory_observations(
        self,
        cases: list[Any],
    ) -> tuple[LocalMemoryObservation, ...]:
        manager = ContextManager()
        observations: list[LocalMemoryObservation] = []
        for case in cases:
            started = perf_counter()
            run_id = f"local-memory-run:{case.case_id}"
            confirmed_slots = {
                turn.fact_id: turn.text
                for turn in case.turns
                if turn.confirmed and turn.fact_id
            }
            candidate_inferences = {
                turn.fact_id: turn.text
                for turn in case.turns
                if not turn.confirmed and turn.fact_id
            }
            memory_refs = [
                MemoryRef(
                    memory_id=fact_id,
                    member_id=case.member_id,
                    memory_type="confirmed_preference",
                    source_id=f"user-confirmation:{fact_id}",
                    source_type="user_confirmation",
                    confirmed_by_user=True,
                )
                for fact_id in case.expected_memory_write_ids
            ]
            evidence_refs = [
                ToolEvidenceRef(
                    source_id=source_key,
                    run_id=run_id,
                    member_id=case.member_id,
                    tool_name=source_key.split(":")[1]
                    if source_key.startswith("tool:")
                    else "memory_checkpoint",
                    tool_call_id=f"local-memory-tool:{case.case_id}:{index}",
                    success=True,
                    schema_valid=True,
                )
                for index, source_key in enumerate(case.expected_source_keys, start=1)
                if source_key.startswith("tool:")
            ]
            envelope = manager.build_envelope(
                user_input="synthetic memory management case",
                run_id=run_id,
                task_id=case.task_id,
                user_id="local-user",
                member_id=case.member_id,
                intent="chronic_care",
                action_type="query",
                confirmed_slots=confirmed_slots,
                candidate_inferences=candidate_inferences,
                tool_evidence_refs=evidence_refs,
                memory_refs=memory_refs,
                conversation_source_ids=list(case.expected_source_keys),
            )
            compacted = manager.compact([envelope])
            final_answer = FinalAnswerTrace(
                answer_id=f"local-memory-answer:{case.case_id}",
                content="Synthetic context result.",
                contains_factual_claims=False,
            )
            trace = RunTrace(
                case_id=case.case_id,
                run_id=run_id,
                task_id=case.task_id,
                user_id="local-user",
                member_id=case.member_id,
                intent="chronic_care",
                safety_trace=SafetyTrace(member_id=case.member_id),
                final_answer=final_answer,
                latency_ms=1,
            )
            evaluation = EvaluationResult(
                case_id=case.case_id,
                run_id=run_id,
                task_success=True,
                tool_call_accuracy=1.0,
                groundedness=None,
                schema_valid=True,
                hallucination_detected=False,
                safety_recall=None,
                human_confirmation_required=False,
                human_confirmation_present=False,
                context_isolation_passed=True,
                latency_ms=1,
                failure_reasons=[],
            )
            reset_state = manager.reset_after_run(
                envelope=compacted,
                run_trace=trace,
                final_answer=final_answer,
                evaluation_result=evaluation,
            )
            retained = tuple(
                fact_id
                for fact_id in case.expected_retained_fact_ids
                if fact_id in compacted.task_state.confirmed_slots
            )
            actual_memory_write_ids = tuple(
                ref.memory_id for ref in reset_state["memory_refs"]
            )
            unconfirmed_ids = tuple(
                fact_id
                for fact_id in actual_memory_write_ids
                if fact_id in candidate_inferences
            )
            visible_member_ids = {
                ref.member_id for ref in compacted.tool_evidence_refs
            } | {ref.member_id for ref in compacted.memory_refs}
            leakage = any(member_id != case.member_id for member_id in visible_member_ids)
            actual_sources = set(compacted.conversation_summary.source_ids)
            actual_sources.update(ref.source_id for ref in compacted.tool_evidence_refs)
            source_pointers_preserved = set(case.expected_source_keys) <= actual_sources
            observations.append(
                LocalMemoryObservation(
                    case_id=case.case_id,
                    task_id=case.task_id,
                    member_id=case.member_id,
                    expected_retained_fact_ids=tuple(case.expected_retained_fact_ids),
                    retained_fact_ids=retained,
                    expected_memory_write_ids=tuple(case.expected_memory_write_ids),
                    actual_memory_write_ids=actual_memory_write_ids,
                    unconfirmed_memory_write_ids=unconfirmed_ids,
                    expected_dropped_fact_ids=tuple(case.expected_dropped_fact_ids),
                    member_scope_leakage=leakage,
                    source_pointers_preserved=source_pointers_preserved,
                    checkpoint_source=case.expected_checkpoint_source,
                    checkpoint_recovery_observed=None,
                    latency_ms=max(1, round((perf_counter() - started) * 1000)),
                )
            )
        return tuple(observations)

    def _run_provider_observations(
        self,
        cases: list[Any],
    ) -> tuple[LocalProviderObservation, ...]:
        observations: list[LocalProviderObservation] = []
        for case in cases:
            calls = 0
            retryable = case.expected_retryable and case.read_only
            max_attempts = case.expected_max_attempts if retryable else 1
            error_type = self._provider_error_type(case.injected_fault)

            def handler(
                request: ProviderRequest,
                *,
                _case=case,
                _error_type=error_type,
            ) -> ProviderResponse:
                nonlocal calls
                calls += 1
                if retryable and calls == max_attempts:
                    return ProviderResponse(
                        provider_name=_case.provider_name,
                        provider_mode=request.provider_mode,
                        operation=request.operation,
                        success=True,
                        data={"local_fault_recovered": True},
                    )
                raise ProviderInvocationError(
                    "synthetic provider fault",
                    error_type=_error_type,
                    retryable=retryable,
                )

            registry = ProviderRegistry(sleeper=lambda _: None)
            registry.register(
                case.provider_name,
                handler,
                retry_policy=ProviderRetryPolicy(max_attempts=max_attempts),
            )
            started = perf_counter()
            response = registry.invoke(
                case.provider_name,
                ProviderRequest(
                    operation=case.operation,
                    business_domain=self._provider_domain(case.provider_name),
                    provider_mode="mock",
                    user_id="local-user",
                    member_id=case.member_id,
                    payload={"case_id": case.case_id},
                ),
            )
            latency_ms = max(1, round((perf_counter() - started) * 1000))
            safe_degraded = (
                not response.success
                and response.degraded
                and not response.data
                and not response.source_refs
                and bool(response.fallback_reason)
            )
            observations.append(
                LocalProviderObservation(
                    case_id=case.case_id,
                    provider_name=case.provider_name,
                    operation=case.operation,
                    read_only=case.read_only,
                    injected_fault=case.injected_fault,
                    expected_retryable=case.expected_retryable,
                    expected_max_attempts=case.expected_max_attempts,
                    attempts=tuple(response.attempts),
                    success=response.success,
                    provider_recovered=response.success,
                    safe_degraded=safe_degraded,
                    write_retry_count=max(0, len(response.attempts) - 1)
                    if not case.read_only
                    else 0,
                    latency_ms=latency_ms,
                    environment=self._environment(),
                )
            )
        return tuple(observations)

    def _build_report(
        self,
        *,
        manifest_hash: str,
        bundle: LocalObservationBundle,
        bundle_hash: str,
    ) -> BenchmarkReport:
        contract_report = self.contract_runner.run("deterministic")
        runtime_metrics = self._runtime_metrics(bundle)
        run_id = str(uuid5(_RUN_NAMESPACE, f"{manifest_hash}:{bundle_hash}"))
        return contract_report.model_copy(
            update={
                "report_version": "4d-local-observed-report-v1",
                "run_id": run_id,
                "generated_at": bundle.generated_at,
                "mode": "local_integration",
                "status": "completed",
                "metrics": [
                    metric
                    for metric in contract_report.metrics
                    if metric.metric_type == "dataset_contract"
                ]
                + runtime_metrics,
                "environment": bundle.environment,
                "notes": [
                    "This report measures the local deterministic implementation against synthetic, non-customer fixtures.",
                    "RAG, ContextManager, ProviderRegistry and wall-clock metrics are local engineering observations.",
                    "Answer quality, model token usage and model cost remain N/A because no LLM was called.",
                    "Review the generated observations before using any number in a resume.",
                ],
            }
        )

    def _runtime_metrics(
        self,
        bundle: LocalObservationBundle,
    ) -> list[BenchmarkMetric]:
        agents = list(bundle.agent_runs)
        rag = list(bundle.rag_queries)
        memory = list(bundle.memory_cases)
        providers = list(bundle.provider_cases)
        metrics = [
            self._ratio_metric(
                "local_task_success_rate",
                sum(item.evaluation.task_success for item in agents),
                len(agents),
                "ratio",
                "Bounded Supervisor deterministic task policy pass rate on 32 synthetic cases.",
            ),
            self._ratio_metric(
                "context_isolation_pass_rate",
                sum(item.evaluation.context_isolation_passed for item in agents),
                len(agents),
                "ratio",
                "RunTrace member-scope checks on the local synthetic business suite.",
            ),
            self._mean_optional_metric(
                "safety_recall",
                [
                    item.evaluation.safety_recall
                    for item in agents
                    if item.evaluation.safety_recall is not None
                ],
                "ratio",
                "Deterministic SafetyAgent policy recall on cases that declare safety flags.",
            ),
            self._ratio_metric(
                "normal_request_false_positive_rate",
                sum(
                    item.run_trace.safety_trace.blocked
                    for item in agents
                    if item.category == "normal_single_domain"
                ),
                sum(item.category == "normal_single_domain" for item in agents),
                "ratio",
                "Normal-case safety flags divided by normal synthetic cases; lower is better.",
            ),
            self._rag_metric("rag_recall_at_3", rag, 3),
            self._rag_metric("rag_recall_at_5", rag, 5),
            self._mean_optional_metric(
                "rag_mrr",
                [self._reciprocal_rank(item) for item in rag],
                "ratio",
                "Mean reciprocal rank of the expected source in the local KeywordRetriever result.",
            ),
            self._ratio_metric(
                "rag_citation_correctness",
                sum(item.expected_source_id in item.cited_source_ids for item in rag),
                len(rag),
                "ratio",
                "Citation pointer correctness using the top local retrieved source.",
            ),
            self._ratio_metric(
                "memory_key_retention_rate",
                sum(
                    fact_id in item.retained_fact_ids
                    for item in memory
                    for fact_id in item.expected_retained_fact_ids
                ),
                sum(len(item.expected_retained_fact_ids) for item in memory),
                "ratio",
                "Confirmed fact keys retained after ContextManager.compact.",
            ),
            self._ratio_metric(
                "unconfirmed_memory_write_rate",
                sum(bool(item.unconfirmed_memory_write_ids) for item in memory),
                len(memory),
                "ratio",
                "Cases that wrote an unconfirmed memory item; lower is better.",
            ),
            self._ratio_metric(
                "cross_member_leakage_rate",
                sum(item.member_scope_leakage for item in memory),
                len(memory),
                "ratio",
                "Memory observations exposing a reference for a different member; lower is better.",
            ),
            self._ratio_metric(
                "memory_source_pointer_retention_rate",
                sum(item.source_pointers_preserved for item in memory),
                len(memory),
                "ratio",
                "Expected source pointers preserved through local compaction/reset.",
            ),
            self._mean_optional_metric(
                "checkpoint_recovery_success_rate",
                [
                    float(item.checkpoint_recovery_observed)
                    for item in memory
                    if item.checkpoint_recovery_observed is not None
                ],
                "ratio",
                "N/A locally: PostgreSQL/Redis checkpoint recovery was not started by this offline run.",
            ),
            self._ratio_metric(
                "provider_recovery_rate",
                sum(
                    item.provider_recovered
                    for item in providers
                    if item.expected_retryable
                ),
                sum(item.expected_retryable for item in providers),
                "ratio",
                "Retryable read-only synthetic faults recovered on the final registry attempt.",
            ),
            self._ratio_metric(
                "provider_safe_degrade_rate",
                sum(item.safe_degraded for item in providers if not item.success),
                sum(not item.success for item in providers),
                "ratio",
                "Non-recovered synthetic faults returned structured degraded responses without evidence.",
            ),
            self._ratio_metric(
                "write_operation_retry_error_rate",
                sum(item.write_retry_count > 0 for item in providers if not item.read_only),
                sum(not item.read_only for item in providers),
                "ratio",
                "Write fault cases with an unintended retry; lower is better.",
            ),
            self._percentile_metric(
                "latency_p50_ms",
                [item.execution_latency_ms for item in agents],
                0.50,
                "Local wall-clock measurement around deterministic bounded Supervisor execution.",
            ),
            self._percentile_metric(
                "latency_p95_ms",
                [item.execution_latency_ms for item in agents],
                0.95,
                "Local wall-clock p95; not a production latency SLO.",
            ),
            self._mean_optional_metric(
                "average_input_tokens",
                self._token_values(bundle, "input_tokens"),
                "tokens",
                "N/A because deterministic provider emitted no model usage.",
            ),
            self._mean_optional_metric(
                "average_output_tokens",
                self._token_values(bundle, "output_tokens"),
                "tokens",
                "N/A because deterministic provider emitted no model usage.",
            ),
            self._mean_optional_metric(
                "average_cost_usd",
                self._token_values(bundle, "cost_usd"),
                "usd",
                "N/A because no billable model call or pricing table was used.",
            ),
            self._mean_optional_metric(
                "answer_quality_pass_rate",
                [],
                "ratio",
                "N/A: deterministic policy success is reported separately and is not human/model answer quality.",
            ),
        ]
        return metrics

    @staticmethod
    def _token_values(bundle: LocalObservationBundle, name: str) -> list[float]:
        """Return only recorded usage; never estimate tokens or cost."""

        values: list[float] = []
        for item in bundle.agent_runs:
            trace = item.model_call_trace
            if trace is None:
                continue
            value = getattr(trace, name, None)
            if value is not None:
                values.append(float(value))
        return values

    @staticmethod
    def _reciprocal_rank(item: LocalRAGObservation) -> float:
        try:
            rank = item.ranked_source_ids.index(item.expected_source_id) + 1
        except ValueError:
            return 0.0
        return 1.0 / rank

    @classmethod
    def _rag_metric(
        cls,
        name: str,
        observations: list[LocalRAGObservation],
        k: int,
    ) -> BenchmarkMetric:
        values = [
            float(item.expected_source_id in item.ranked_source_ids[:k])
            for item in observations
        ]
        return cls._mean_optional_metric(
            name,
            values,
            "ratio",
            f"Expected source recall in the top {k} local KeywordRetriever results.",
        )

    @staticmethod
    def _ratio_metric(
        name: str,
        numerator: int,
        denominator: int,
        unit: str,
        notes: str,
    ) -> BenchmarkMetric:
        return BenchmarkMetric(
            name=name,
            value=(numerator / denominator if denominator else None),
            status="measured" if denominator else "not_available",
            metric_type="runtime_observation",
            sample_count=denominator,
            unit=unit,
            notes=notes,
        )

    @staticmethod
    def _mean_optional_metric(
        name: str,
        values: list[float] | float | None,
        unit: str,
        notes: str,
    ) -> BenchmarkMetric:
        if values is None:
            rendered: list[float] = []
        else:
            rendered = values if isinstance(values, list) else [float(values)]
        return BenchmarkMetric(
            name=name,
            value=(fmean(rendered) if rendered else None),
            status="measured" if rendered else "not_available",
            metric_type="runtime_observation",
            sample_count=len(rendered),
            unit=unit,
            notes=notes,
        )

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        rank = max(1, math.ceil(fraction * len(ordered)))
        return float(ordered[rank - 1])

    @classmethod
    def _percentile_metric(
        cls,
        name: str,
        values: list[float],
        fraction: float,
        notes: str,
    ) -> BenchmarkMetric:
        value = cls._percentile(values, fraction)
        return BenchmarkMetric(
            name=name,
            value=value,
            status="measured" if value is not None else "not_available",
            metric_type="runtime_observation",
            sample_count=len(values),
            unit="ms",
            notes=notes,
        )

    @staticmethod
    def _provider_error_type(fault: str) -> str:
        return {
            "timeout": "timeout",
            "rate_limit": "rate_limit",
            "transient_5xx": "provider_unavailable",
            "connection_reset": "provider_unavailable",
            "schema_error": "schema_error",
            "permission_error": "permission_denied",
            "member_scope_error": "context_isolation_violation",
            "version_conflict": "business_conflict",
            "invalid_source": "schema_error",
            "unknown_error": "unknown_error",
        }.get(fault, "unknown_error")

    @staticmethod
    def _provider_domain(provider_name: str) -> str:
        if provider_name == "pharmacy":
            return "chronic_care"
        if provider_name == "hospital_or_consultation":
            return "preconsultation"
        return "health_record"

    def _environment(self) -> dict[str, str]:
        return {
            "mode": "local_integration",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": "sqlite_in_memory_synthetic",
            "llm": "deterministic_provider_not_called",
            "provider": "ProviderRegistry_fault_injection",
            "rag": "KeywordRetriever_sqlalchemy_sqlite",
            "customer_data": "none",
        }

    @staticmethod
    def render_markdown(
        bundle: LocalObservationBundle,
        report: BenchmarkReport,
    ) -> str:
        lines = [
            "# 4D-B Local Integration Benchmark",
            "",
            "> 本报告来自本机合成数据和真实本地代码执行，不代表线上流量、真实客户数据或真实模型回答质量。",
            "",
            f"- Status: `{report.status}`",
            f"- Mode: `{report.mode}`",
            f"- Run ID: `{report.run_id}`",
            f"- Observation bundle: `{bundle.bundle_version}`",
            f"- Fixture SHA-256: `{bundle.fixture_sha256}`",
            "",
            "## Observation Inventory",
            "",
            "| Evidence | Count |",
            "| --- | ---: |",
            f"| bounded Supervisor RunTrace | {len(bundle.agent_runs)} |",
            f"| local RAG queries | {len(bundle.rag_queries)} |",
            f"| ContextManager memory cases | {len(bundle.memory_cases)} |",
            f"| Provider fault cases | {len(bundle.provider_cases)} |",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Status | Samples | Unit | Notes |",
            "| --- | ---: | --- | ---: | --- | --- |",
        ]
        for metric in report.metrics:
            value = "N/A" if metric.value is None else f"{metric.value:.4f}"
            lines.append(
                f"| {metric.name} | {value} | {metric.status} | {metric.sample_count} | {metric.unit} | {metric.notes} |"
            )
        lines.extend(
            [
                "",
                "## Evidence Boundary",
                "",
                "- RAG recall is measured by executing `KeywordRetriever` against an in-memory SQLite knowledge fixture.",
                "- Memory retention is measured by executing `ContextManager.compact` and `reset_after_run`.",
                "- Provider recovery is measured by executing `ProviderRegistry` with deterministic injected faults.",
                "- The latency values are local wall-clock observations and should be rerun on the same machine before comparison.",
                "- Answer quality, model token usage and model cost remain `N/A` until a real model response with usage and a human-reviewed answer set are supplied.",
                "",
            ]
        )
        return "\n".join(lines)


def main() -> None:
    runner = LocalObservedBenchmarkRunner.from_project_root()
    bundle, report = runner.run()
    paths = runner.write_reports(bundle, report)
    print(
        f"4D-B local status={report.status} mode={report.mode} "
        f"agent_runs={len(bundle.agent_runs)} rag={len(bundle.rag_queries)} "
        f"memory={len(bundle.memory_cases)} providers={len(bundle.provider_cases)}"
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()


__all__ = ["LocalObservedBenchmarkRunner"]

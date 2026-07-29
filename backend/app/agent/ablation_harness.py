"""Deterministic 32-case harness and same-condition A/B/C ablation runner."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, cast
from uuid import UUID, uuid5

from app.agent.ablation_schemas import (
    AblationCaseResult,
    AblationHarnessOutput,
    AblationRunTrace,
    AblationStrategy,
    AblationToolCallTrace,
    BusinessHarnessCase,
    ExpectedToolInvocation,
    FairnessConfig,
    SliceMetrics,
    StrategyMetrics,
)
from app.agent.eval_schemas import ExpectedCase, ExpectedSource
from app.agent.evaluator import DeterministicEvaluator
from app.agent.orchestration import DeterministicBoundedSupervisor
from app.agent.orchestration_schemas import ComplexityRoutingRequest
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    RAGTrace,
    RunTrace,
    SafetyTrace,
    ToolCallTrace,
)


_RUN_NAMESPACE = UUID("48d7d4fc-4d33-477c-a56d-a98caa8a44fc")
_ANSWER_NAMESPACE = UUID("34e5a725-2e97-4de5-ad9e-003cbd4b2f73")
_STRATEGIES: tuple[AblationStrategy, ...] = (
    "single_agent",
    "fixed_router",
    "bounded_supervisor",
)
_EXPECTED_CATEGORY_COUNTS = {
    "normal_single_domain": 6,
    "complex_cross_domain": 6,
    "missing_information": 3,
    "high_risk_medical": 5,
    "rag_and_source": 4,
    "provider_or_tool_failure": 3,
    "member_isolation_attack": 3,
    "confirmation_idempotency": 2,
}
_GOVERNANCE_STAGES = ("request", "action", "final_output", "evaluator")


class AblationHarnessRunner:
    """Run three orchestration policies over one frozen evidence/governance suite.

    The harness is deliberately offline. It uses real ``RunTrace`` contracts and
    the current deterministic bounded Supervisor, but fixture latencies are not
    production wall-clock measurements and missing provider token usage remains
    unavailable rather than being estimated.
    """

    def __init__(
        self,
        fixture_path: Path,
        *,
        evaluator: DeterministicEvaluator | None = None,
        supervisor: DeterministicBoundedSupervisor | None = None,
    ) -> None:
        self.fixture_path = fixture_path
        self.evaluator = evaluator or DeterministicEvaluator()
        self.supervisor = supervisor or DeterministicBoundedSupervisor()

    def load_suite(self) -> tuple[FairnessConfig, tuple[BusinessHarnessCase, ...]]:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        fairness = FairnessConfig.model_validate(payload["fairness_config"])
        cases = tuple(BusinessHarnessCase.model_validate(item) for item in payload["cases"])
        self._validate_case_inventory(cases)
        return fairness, cases

    def run(self) -> AblationHarnessOutput:
        fairness, cases = self.load_suite()
        results = tuple(
            self._evaluate_case(case, strategy, fairness)
            for case in cases
            for strategy in _STRATEGIES
        )
        metrics = tuple(
            self.aggregate_strategy(
                strategy,
                [result for result in results if result.strategy == strategy],
            )
            for strategy in _STRATEGIES
        )
        return AblationHarnessOutput(
            fairness_config=fairness,
            results=results,
            metrics=metrics,
        )

    def _evaluate_case(
        self,
        case: BusinessHarnessCase,
        strategy: AblationStrategy,
        fairness: FairnessConfig,
    ) -> AblationCaseResult:
        role_sequence = self._role_sequence(case, strategy)
        selected_tools = self._select_tools(case, strategy, role_sequence)
        trace = self._build_trace(case, strategy, fairness, role_sequence, selected_tools)
        expected = self._build_expected_case(case)
        evaluation = self.evaluator.evaluate(expected, trace.run_trace)
        behavior_matches = self._behavior_matches(case, trace.run_trace)
        if not behavior_matches:
            evaluation = evaluation.model_copy(
                update={
                    "task_success": False,
                    "failure_reasons": list(
                        dict.fromkeys([*evaluation.failure_reasons, "behavior_mismatch"])
                    ),
                }
            )

        expected_tools = tuple(case.expected_tool_calls)
        tool_set_exact = {item.tool_name for item in selected_tools} == {
            item.tool_name for item in expected_tools
        }
        parameter_exact = self._tool_parameter_multiset(selected_tools) == self._tool_parameter_multiset(
            expected_tools
        )
        role_order_exact = (
            None
            if strategy == "single_agent"
            else tuple(role_sequence) == tuple(case.expected_role_order)
        )
        role_coverage = (
            1.0
            if strategy == "single_agent"
            else self._coverage(case.expected_role_order, set(role_sequence))
        )
        expected_handoffs = max(0, len(case.expected_role_order) - 1)
        actual_handoffs = max(0, len(role_sequence) - 1)
        unnecessary_handoffs = (
            0
            if strategy == "single_agent"
            else max(0, actual_handoffs - expected_handoffs)
        )
        duplicate_tools = sum(
            count - 1 for count in Counter(item.tool_name for item in selected_tools).values()
        )
        safety_precision = self._precision(
            set(case.expected_safety_flags),
            set(trace.run_trace.safety_trace.flags),
        )
        governance_coverage = self._coverage(
            _GOVERNANCE_STAGES,
            set(trace.governance_stages),
        )
        rag_recall_3 = self._rag_recall(case.relevant_rag_source_ids, trace.ranked_rag_source_ids[:3])
        rag_recall_5 = self._rag_recall(case.relevant_rag_source_ids, trace.ranked_rag_source_ids[:5])
        citation_correctness = self._citation_correctness(
            case.relevant_rag_source_ids,
            trace.cited_source_ids,
        )
        return AblationCaseResult(
            case_id=case.case_id,
            category=case.category,
            complexity=case.complexity,
            strategy=strategy,
            evaluation=evaluation,
            trace=trace,
            task_completed=evaluation.task_success and behavior_matches,
            tool_set_exact_match=tool_set_exact,
            tool_parameter_exact_match=parameter_exact,
            role_order_exact_match=role_order_exact,
            required_role_coverage=role_coverage,
            unnecessary_handoffs=unnecessary_handoffs,
            duplicate_tool_calls=duplicate_tools,
            safety_precision=safety_precision,
            governance_coverage=governance_coverage,
            rag_recall_at_3=rag_recall_3,
            rag_recall_at_5=rag_recall_5,
            citation_correctness=citation_correctness,
        )

    def _role_sequence(
        self,
        case: BusinessHarnessCase,
        strategy: AblationStrategy,
    ) -> tuple[str, ...]:
        if strategy == "single_agent":
            return ("SingleAgent",)
        if strategy == "fixed_router":
            return (case.primary_role,)

        orchestration = self.supervisor.run(
            ComplexityRoutingRequest(
                task_id=case.case_id,
                user_id=case.user_id,
                member_id=case.member_id,
                user_input=case.user_input,
                intent=case.intent,
            )
        )
        return tuple(result.agent_role for result in orchestration.results)

    @staticmethod
    def _select_tools(
        case: BusinessHarnessCase,
        strategy: AblationStrategy,
        role_sequence: tuple[str, ...],
    ) -> tuple[ExpectedToolInvocation, ...]:
        expected = list(case.expected_tool_calls)
        if strategy == "single_agent":
            selected = list(expected)
            if case.complexity == "complex":
                shared = next(
                    (item for item in expected if item.tool_name == "query_health_profile"),
                    None,
                )
                if shared is not None:
                    selected.append(shared)
            if expected and not any(
                item.tool_name == "search_safety_knowledge" for item in expected
            ):
                selected.append(
                    ExpectedToolInvocation(
                        tool_name="search_safety_knowledge",
                        owner_role=case.primary_role,
                        parameters={"member_id": case.member_id, "purpose": "broad_baseline_guard"},
                        success=True,
                        schema_valid=True,
                        evidence_present=False,
                    )
                )
            return tuple(selected)
        allowed_roles = set(cast(tuple[str, ...], role_sequence))
        return tuple(item for item in expected if item.owner_role in allowed_roles)

    @staticmethod
    def _build_trace(
        case: BusinessHarnessCase,
        strategy: AblationStrategy,
        fairness: FairnessConfig,
        role_sequence: tuple[str, ...],
        selected_tools: tuple[ExpectedToolInvocation, ...],
    ) -> AblationRunTrace:
        run_id = str(uuid5(_RUN_NAMESPACE, f"{case.case_id}:{strategy}"))
        tool_audit = tuple(
            AblationToolCallTrace(
                tool_name=item.tool_name,
                agent_role=(
                    "SingleAgent" if strategy == "single_agent" else item.owner_role
                ),
                parameters=item.parameters,
                success=item.success,
                schema_valid=item.schema_valid,
                evidence_present=item.evidence_present,
                source_id=item.source_id,
                source_name=item.source_name,
            )
            for item in selected_tools
        )
        run_tool_calls = tuple(
            ToolCallTrace(
                tool_name=item.tool_name,
                member_id=case.member_id,
                source_id=item.source_id,
                source_name=item.source_name,
                success=item.success,
                schema_valid=item.schema_valid,
                evidence_present=item.evidence_present,
            )
            for item in selected_tools
        )
        rag_traces = tuple(
            RAGTrace(
                source_id=source_id,
                source_name=source_id,
                member_id=case.member_id,
                retrieved=True,
                schema_valid=True,
            )
            for source_id in case.ranked_rag_source_ids[:5]
        )
        waiting = case.expected_behavior == "needs_confirmation"
        blocked = case.expected_behavior == "blocked"
        content = {
            "blocked": "The request was blocked by the medical safety policy.",
            "needs_clarification": "Please provide the missing task information.",
            "needs_confirmation": "A local draft is ready and is awaiting user confirmation.",
            "degraded": "The dependency is unavailable; no unsupported factual claim was generated.",
            "completed": "The task result was prepared from frozen evidence and source references.",
        }[case.expected_behavior]
        latency = AblationHarnessRunner._fixture_latency(
            strategy,
            len(role_sequence),
            len(selected_tools),
            case.complexity,
        )
        run_trace = RunTrace(
            case_id=case.case_id,
            run_id=run_id,
            task_id=case.case_id,
            user_id=case.user_id,
            member_id=case.member_id,
            intent=case.intent,
            tool_calls=run_tool_calls,
            rag_traces=rag_traces,
            safety_trace=SafetyTrace(
                member_id=case.member_id,
                flags=case.expected_safety_flags,
                blocked=blocked,
                requires_human_confirmation=waiting,
            ),
            final_answer=FinalAnswerTrace(
                answer_id=str(uuid5(_ANSWER_NAMESPACE, f"{case.case_id}:{strategy}")),
                content=content,
                contains_factual_claims=case.contains_factual_claims,
                waiting_for_user_confirmation=waiting,
                human_confirmation_present=False,
                action_status="awaiting_confirmation" if waiting else "none",
            ),
            latency_ms=latency,
            schema_valid=True,
        )
        return AblationRunTrace(
            strategy=strategy,
            fairness_config_id=fairness.config_id,
            run_trace=run_trace,
            role_sequence=role_sequence,
            tool_calls=tool_audit,
            governance_stages=cast(Any, _GOVERNANCE_STAGES),
            ranked_rag_source_ids=case.ranked_rag_source_ids,
            cited_source_ids=case.cited_source_ids,
            token_usage_available=False,
        )

    @staticmethod
    def _build_expected_case(case: BusinessHarnessCase) -> ExpectedCase:
        category = {
            "normal_single_domain": "refill",
            "complex_cross_domain": "consultation",
            "missing_information": "consultation",
            "high_risk_medical": "safety",
            "rag_and_source": "consultation",
            "provider_or_tool_failure": "tool_failure",
            "member_isolation_attack": "isolation",
            "confirmation_idempotency": "reminder",
        }[case.category]
        sources = [
            ExpectedSource(
                source_type="tool_evidence",
                source_name=item.source_name or item.tool_name,
            )
            for item in case.expected_tool_calls
            if item.evidence_present
        ]
        sources.extend(
            ExpectedSource(source_type="rag_source", source_name=source_id)
            for source_id in case.relevant_rag_source_ids
        )
        return ExpectedCase(
            case_id=case.case_id,
            input_category=cast(Any, category),
            user_input=case.user_input,
            expected_intent=case.intent,
            expected_member_id=case.member_id,
            expected_required_tools=list(
                dict.fromkeys(item.tool_name for item in case.expected_tool_calls)
            ),
            expected_safety_flags=list(case.expected_safety_flags),
            expected_human_confirmation_required=case.expected_human_confirmation_required,
            forbidden_phrases=list(case.forbidden_phrases),
            expected_sources=sources,
        )

    @staticmethod
    def _behavior_matches(case: BusinessHarnessCase, trace: RunTrace) -> bool:
        if case.expected_behavior == "blocked":
            return trace.safety_trace.blocked
        if case.expected_behavior == "needs_confirmation":
            return trace.final_answer.waiting_for_user_confirmation
        if case.expected_behavior in {"needs_clarification", "degraded"}:
            return not trace.final_answer.contains_factual_claims
        return not trace.safety_trace.blocked

    @staticmethod
    def aggregate_strategy(
        strategy: AblationStrategy,
        results: list[AblationCaseResult],
    ) -> StrategyMetrics:
        route_values = [
            result.role_order_exact_match
            for result in results
            if result.role_order_exact_match is not None
        ]
        safety_recall = [
            result.evaluation.safety_recall
            for result in results
            if result.evaluation.safety_recall is not None
        ]
        safety_precision = [
            result.safety_precision
            for result in results
            if result.safety_precision is not None
        ]
        rag3 = [result.rag_recall_at_3 for result in results if result.rag_recall_at_3 is not None]
        rag5 = [result.rag_recall_at_5 for result in results if result.rag_recall_at_5 is not None]
        citations = [
            result.citation_correctness
            for result in results
            if result.citation_correctness is not None
        ]
        latencies = [result.trace.run_trace.latency_ms for result in results]
        token_results = [result for result in results if result.trace.token_usage_available]
        total_tokens = [
            cast(int, result.trace.total_tokens)
            for result in token_results
            if result.trace.total_tokens is not None
        ]
        costs = [
            result.trace.billed_cost_usd
            for result in token_results
            if result.trace.billed_cost_usd is not None
        ]
        return StrategyMetrics(
            strategy=strategy,
            case_count=len(results),
            task_completion_rate=AblationHarnessRunner._mean_bool(
                result.task_completed for result in results
            ),
            tool_set_exact_match_rate=AblationHarnessRunner._mean_bool(
                result.tool_set_exact_match for result in results
            ),
            tool_parameter_exact_match_rate=AblationHarnessRunner._mean_bool(
                result.tool_parameter_exact_match for result in results
            ),
            route_order_exact_match_rate=(
                fmean(cast(list[bool], route_values)) if route_values else None
            ),
            required_role_coverage_avg=(
                fmean(result.required_role_coverage for result in results)
                if results
                else 0.0
            ),
            unnecessary_handoffs_avg=(
                fmean(result.unnecessary_handoffs for result in results)
                if results
                else 0.0
            ),
            duplicate_tool_calls_avg=(
                fmean(result.duplicate_tool_calls for result in results)
                if results
                else 0.0
            ),
            safety_recall_rate=fmean(cast(list[float], safety_recall)) if safety_recall else None,
            safety_precision_rate=(
                fmean(cast(list[float], safety_precision)) if safety_precision else None
            ),
            context_isolation_pass_rate=AblationHarnessRunner._mean_bool(
                result.evaluation.context_isolation_passed for result in results
            ),
            governance_coverage_rate=(
                fmean(result.governance_coverage for result in results)
                if results
                else 0.0
            ),
            rag_recall_at_3=fmean(cast(list[float], rag3)) if rag3 else None,
            rag_recall_at_5=fmean(cast(list[float], rag5)) if rag5 else None,
            citation_correctness_rate=(
                fmean(cast(list[float], citations)) if citations else None
            ),
            p50_latency_ms=AblationHarnessRunner._percentile(latencies, 0.50),
            p95_latency_ms=AblationHarnessRunner._percentile(latencies, 0.95),
            token_usage_available_rate=(len(token_results) / len(results) if results else 0.0),
            avg_total_tokens=fmean(total_tokens) if total_tokens else None,
            total_billed_cost_usd=sum(cast(list[float], costs)) if costs else None,
            simple=AblationHarnessRunner._slice_metrics(
                [result for result in results if result.complexity == "simple"]
            ),
            complex=AblationHarnessRunner._slice_metrics(
                [result for result in results if result.complexity == "complex"]
            ),
        )

    @staticmethod
    def render_markdown(output: AblationHarnessOutput) -> str:
        fairness = output.fairness_config
        lines = [
            "# 4B Task 11 Deterministic Harness and Ablation Report",
            "",
            "> This report uses frozen deterministic fixtures and modeled fixture latency. "
            "It is not a production, clinical, real-provider latency, token, or billing claim.",
            "",
            "## Fairness Contract",
            "",
            "| Field | Shared value |",
            "| --- | --- |",
            f"| config_id | {fairness.config_id} |",
            f"| model | {fairness.model_provider}/{fairness.model_name} |",
            f"| tool_catalog_version | {fairness.tool_catalog_version} |",
            f"| rag_index_version | {fairness.rag_index_version} |",
            f"| safety_policy_version | {fairness.safety_policy_version} |",
            f"| confirmation_policy_version | {fairness.confirmation_policy_version} |",
            f"| context_token_limit | {fairness.context_token_limit} |",
            f"| max_output_tokens | {fairness.max_output_tokens} |",
            "",
            "## Strategy Metrics",
            "",
            "| Strategy | cases | success | tool set exact | tool params exact | route order | dup tools avg | safety recall | isolation | R@3 | R@5 | citation | p50 ms* | p95 ms* | token usage |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for metric in output.metrics:
            lines.append(
                "| "
                f"{metric.strategy} | {metric.case_count} | {metric.task_completion_rate:.4f} | "
                f"{metric.tool_set_exact_match_rate:.4f} | {metric.tool_parameter_exact_match_rate:.4f} | "
                f"{AblationHarnessRunner._format_optional(metric.route_order_exact_match_rate)} | "
                f"{metric.duplicate_tool_calls_avg:.4f} | "
                f"{AblationHarnessRunner._format_optional(metric.safety_recall_rate)} | "
                f"{metric.context_isolation_pass_rate:.4f} | "
                f"{AblationHarnessRunner._format_optional(metric.rag_recall_at_3)} | "
                f"{AblationHarnessRunner._format_optional(metric.rag_recall_at_5)} | "
                f"{AblationHarnessRunner._format_optional(metric.citation_correctness_rate)} | "
                f"{metric.p50_latency_ms} | {metric.p95_latency_ms} | "
                f"{metric.token_usage_available_rate:.4f} |"
            )
        lines.extend(
            [
                "",
                "*Latency is a frozen fixture field for repeatable regression comparison; task 12 owns real wall-clock validation.*",
                "",
                "## Governance and Orchestration Attribution",
                "",
                "| Strategy | role coverage | unnecessary handoffs avg | safety precision | governance coverage | token count | billed cost |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for metric in output.metrics:
            lines.append(
                f"| {metric.strategy} | {metric.required_role_coverage_avg:.4f} | "
                f"{metric.unnecessary_handoffs_avg:.4f} | "
                f"{AblationHarnessRunner._format_optional(metric.safety_precision_rate)} | "
                f"{metric.governance_coverage_rate:.4f} | "
                f"{AblationHarnessRunner._format_optional(metric.avg_total_tokens)} | "
                f"{AblationHarnessRunner._format_optional(metric.total_billed_cost_usd)} |"
            )
        lines.extend(
            [
                "",
                "## Case Inventory",
                "",
                "| Category | Cases |",
                "| --- | ---: |",
                "| normal_single_domain | 6 |",
                "| complex_cross_domain | 6 |",
                "| missing_information | 3 |",
                "| high_risk_medical | 5 |",
                "| rag_and_source | 4 |",
                "| provider_or_tool_failure | 3 |",
                "| member_isolation_attack | 3 |",
                "| confirmation_idempotency | 2 |",
                "",
                "## Simple vs Complex",
                "",
                "| Strategy | simple cases | simple success | complex cases | complex success |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for metric in output.metrics:
            lines.append(
                f"| {metric.strategy} | {metric.simple.case_count} | "
                f"{metric.simple.task_completion_rate:.4f} | {metric.complex.case_count} | "
                f"{metric.complex.task_completion_rate:.4f} |"
            )
        lines.extend(
            [
                "",
                "## Interpretation Boundary",
                "",
                "- Safety, member isolation, RAG ranking, citations, confirmation policy, model identity and token limits are shared controls.",
                "- Their pass rates must not be attributed to the bounded Supervisor.",
                "- Token and billed cost remain `N/A` because the deterministic provider returned no usage; the harness does not estimate them.",
                "- A/B/C differences only support claims about orchestration regression behavior in this fixed suite.",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def write_reports(
        output: AblationHarnessOutput,
        *,
        json_path: Path,
        markdown_path: Path,
    ) -> None:
        json_payload = json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2)
        markdown_payload = AblationHarnessRunner.render_markdown(output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        if not json_path.exists() or json_path.read_text(encoding="utf-8") != json_payload:
            json_path.write_text(json_payload, encoding="utf-8")
        if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != markdown_payload:
            markdown_path.write_text(markdown_payload, encoding="utf-8")

    @staticmethod
    def _validate_case_inventory(cases: tuple[BusinessHarnessCase, ...]) -> None:
        if len(cases) != 32:
            raise ValueError(f"task-eleven suite must contain exactly 32 cases, got {len(cases)}")
        ids = [case.case_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("task-eleven case_id values must be unique")
        counts = Counter(case.category for case in cases)
        if dict(counts) != _EXPECTED_CATEGORY_COUNTS:
            raise ValueError(
                f"task-eleven category inventory mismatch: expected={_EXPECTED_CATEGORY_COUNTS}, actual={dict(counts)}"
            )

    @staticmethod
    def _tool_parameter_multiset(
        calls: Iterable[ExpectedToolInvocation] | Iterable[AblationToolCallTrace],
    ) -> Counter[tuple[str, str]]:
        return Counter(
            (
                item.tool_name,
                json.dumps(item.parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            for item in calls
        )

    @staticmethod
    def _coverage(expected: Iterable[str], actual: set[str]) -> float:
        expected_items = tuple(dict.fromkeys(expected))
        if not expected_items:
            return 1.0
        return sum(item in actual for item in expected_items) / len(expected_items)

    @staticmethod
    def _precision(expected: set[str], actual: set[str]) -> float | None:
        if not expected and not actual:
            return None
        if not actual:
            return 0.0
        return len(expected & actual) / len(actual)

    @staticmethod
    def _rag_recall(relevant: tuple[str, ...], retrieved: tuple[str, ...]) -> float | None:
        if not relevant:
            return None
        return len(set(relevant) & set(retrieved)) / len(set(relevant))

    @staticmethod
    def _citation_correctness(relevant: tuple[str, ...], cited: tuple[str, ...]) -> float | None:
        if not relevant:
            return None
        if not cited:
            return 0.0
        return len(set(relevant) & set(cited)) / len(set(cited))

    @staticmethod
    def _fixture_latency(
        strategy: AblationStrategy,
        role_count: int,
        tool_count: int,
        complexity: str,
    ) -> int:
        base = {"single_agent": 42, "fixed_router": 34, "bounded_supervisor": 38}[strategy]
        planner = 11 if strategy == "bounded_supervisor" and complexity == "complex" else 0
        handoff = max(0, role_count - 1) * 4
        return base + planner + role_count * 8 + tool_count * 6 + handoff

    @staticmethod
    def _slice_metrics(results: list[AblationCaseResult]) -> SliceMetrics:
        return SliceMetrics(
            case_count=len(results),
            task_completion_rate=AblationHarnessRunner._mean_bool(
                result.task_completed for result in results
            ),
            tool_set_exact_match_rate=AblationHarnessRunner._mean_bool(
                result.tool_set_exact_match for result in results
            ),
            tool_parameter_exact_match_rate=AblationHarnessRunner._mean_bool(
                result.tool_parameter_exact_match for result in results
            ),
        )

    @staticmethod
    def _mean_bool(values: Iterable[bool]) -> float:
        rendered = list(values)
        return fmean(rendered) if rendered else 0.0

    @staticmethod
    def _percentile(values: list[int], fraction: float) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        rank = max(1, math.ceil(fraction * len(ordered)))
        return ordered[rank - 1]

    @staticmethod
    def _format_optional(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.4f}"


def default_ablation_runner(project_root: Path | None = None) -> AblationHarnessRunner:
    root = project_root or Path(__file__).resolve().parents[3]
    return AblationHarnessRunner(
        root / "backend" / "tests" / "fixtures" / "business_harness_cases.4b.json"
    )


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    output = default_ablation_runner(root).run()
    AblationHarnessRunner.write_reports(
        output,
        json_path=root / "output" / "agent_ablation_report.4b.json",
        markdown_path=root / "output" / "agent_ablation_report.4b.md",
    )


if __name__ == "__main__":
    main()


__all__ = ["AblationHarnessRunner", "default_ablation_runner"]

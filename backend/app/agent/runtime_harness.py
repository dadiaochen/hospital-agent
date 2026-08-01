from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, FinalStatus, Intent
from app.agent.eval_schemas import (
    EvaluationResult,
    ExpectedCase,
    ExpectedSource,
    HarnessCaseCategory,
)
from app.agent.evaluator import DeterministicEvaluator
from app.agent.harness_runner import AggregatedMetrics, HarnessRunner
from app.agent.run_trace_schemas import RunTrace
from app.agent.runtime_trace_adapter import RuntimeTraceAdapter


MemberRelationship = Literal["self", "father", "mother"]
GuardType = Literal["cross_member_rejected", "initial_confirmation_rejected"]


class RuntimeTraceCaseDefinition(ContractModel):
    case_id: str = Field(min_length=1)
    input_category: HarnessCaseCategory
    user_input: str = Field(min_length=1)
    expected_intent: Intent
    member_relationship: MemberRelationship
    medication_name: str | None = None
    city: str | None = None
    expected_required_tools: tuple[str, ...] = Field(default_factory=tuple)
    expected_safety_flags: tuple[str, ...] = Field(default_factory=tuple)
    expected_human_confirmation_required: bool
    forbidden_phrases: tuple[str, ...] = Field(default_factory=tuple)
    expected_sources: tuple[ExpectedSource, ...] = Field(default_factory=tuple)
    continue_after_confirmation: bool = False
    expected_initial_status: FinalStatus
    expected_final_status: FinalStatus
    minimum_tool_sources: int = Field(default=0, ge=0)
    minimum_rag_sources: int = Field(default=0, ge=0)
    minimum_failed_tool_calls: int = Field(default=0, ge=0)
    maximum_available_sources: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_confirmation_flow(self) -> "RuntimeTraceCaseDefinition":
        if self.continue_after_confirmation and not self.expected_human_confirmation_required:
            raise ValueError("continued cases must require human confirmation")
        return self

    def to_expected_case(self, member_id: str) -> ExpectedCase:
        return ExpectedCase(
            case_id=self.case_id,
            input_category=self.input_category,
            user_input=self.user_input,
            expected_intent=self.expected_intent,
            expected_member_id=member_id,
            expected_required_tools=list(self.expected_required_tools),
            expected_safety_flags=list(self.expected_safety_flags),
            expected_human_confirmation_required=(
                self.expected_human_confirmation_required
            ),
            forbidden_phrases=list(self.forbidden_phrases),
            expected_sources=list(self.expected_sources),
        )


class RuntimeGuardCaseDefinition(ContractModel):
    case_id: str = Field(min_length=1)
    guard_type: GuardType
    user_input: str = Field(min_length=1)
    member_relationship: MemberRelationship | None = None
    medication_name: str | None = None
    city: str | None = None
    expected_status_code: int = Field(ge=400, le=499)
    expected_error_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_member_for_confirmation_guard(self) -> "RuntimeGuardCaseDefinition":
        if (
            self.guard_type == "initial_confirmation_rejected"
            and self.member_relationship is None
        ):
            raise ValueError("confirmation guards require a discoverable member")
        return self


class RuntimeHarnessSuite(ContractModel):
    trace_cases: tuple[RuntimeTraceCaseDefinition, ...]
    guard_cases: tuple[RuntimeGuardCaseDefinition, ...]

    @model_validator(mode="after")
    def reject_duplicate_case_ids(self) -> "RuntimeHarnessSuite":
        case_ids = [
            case.case_id for case in (*self.trace_cases, *self.guard_cases)
        ]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("runtime harness case_id values must be unique")
        return self


class RuntimeTraceCaseResult(ContractModel):
    case_id: str
    initial_run_id: str
    evaluated_run_id: str
    task_id: str
    member_id: str
    initial_status: FinalStatus
    final_status: FinalStatus
    continued: bool
    external_action_status: str
    runtime_contract_passed: bool
    source_ids: tuple[str, ...] = Field(default_factory=tuple)
    redacted_paths: tuple[str, ...] = Field(default_factory=tuple)
    trace: RunTrace
    evaluation: EvaluationResult


class RuntimeGuardResult(ContractModel):
    case_id: str
    passed: bool
    expected_status_code: int
    actual_status_code: int
    expected_error_code: str
    actual_error_code: str | None
    failure_reasons: tuple[str, ...] = Field(default_factory=tuple)


class RuntimeHarnessMetrics(AggregatedMetrics):
    trace_contract_pass_rate: float = Field(ge=0.0, le=1.0)
    guard_pass_rate: float = Field(ge=0.0, le=1.0)
    overall_case_pass_rate: float = Field(ge=0.0, le=1.0)


class RuntimeHarnessOutput(ContractModel):
    report_kind: Literal["local_runtime_e2e"] = "local_runtime_e2e"
    environment: str = Field(min_length=1)
    generated_at: datetime
    run_key_prefix: str = Field(min_length=1)
    trace_results: tuple[RuntimeTraceCaseResult, ...]
    guard_results: tuple[RuntimeGuardResult, ...]
    metrics: RuntimeHarnessMetrics


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> Any: ...


class RuntimeTransport(Protocol):
    def get(self, url: str) -> ResponseLike: ...

    def post(self, url: str, *, json: Mapping[str, Any]) -> ResponseLike: ...


class RuntimeHarnessError(RuntimeError):
    pass


class RuntimeE2EHarnessRunner:
    def __init__(
        self,
        transport: RuntimeTransport,
        *,
        run_key_prefix: str,
        environment: str,
        evaluator: DeterministicEvaluator | None = None,
        trace_adapter: RuntimeTraceAdapter | None = None,
    ) -> None:
        self.transport = transport
        self.run_key_prefix = run_key_prefix
        self.environment = environment
        self.evaluator = evaluator or DeterministicEvaluator()
        self.trace_adapter = trace_adapter or RuntimeTraceAdapter()

    @staticmethod
    def load_suite(path: Path) -> RuntimeHarnessSuite:
        return RuntimeHarnessSuite.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def run(self, suite: RuntimeHarnessSuite) -> RuntimeHarnessOutput:
        required_relationships = {
            case.member_relationship for case in suite.trace_cases
        } | {
            case.member_relationship
            for case in suite.guard_cases
            if case.member_relationship is not None
        }
        member_ids = self._discover_member_ids(required_relationships)
        trace_results = tuple(
            self._run_trace_case(case, member_ids)
            for case in suite.trace_cases
        )
        guard_results = tuple(
            self._run_guard_case(case, member_ids)
            for case in suite.guard_cases
        )
        return RuntimeHarnessOutput(
            environment=self.environment,
            generated_at=datetime.now(timezone.utc),
            run_key_prefix=self.run_key_prefix,
            trace_results=trace_results,
            guard_results=guard_results,
            metrics=self._aggregate(trace_results, guard_results),
        )

    def _discover_member_ids(
        self,
        required_relationships: set[MemberRelationship],
    ) -> dict[str, str]:
        response = self.transport.get("/api/family-members")
        if response.status_code != 200:
            raise RuntimeHarnessError(
                f"member discovery failed with HTTP {response.status_code}"
            )
        payload = _as_mapping(response.json(), "family member response")
        items = _as_sequence(payload.get("items", ()), "family member items")
        member_ids: dict[str, str] = {}
        for item in items:
            member = _as_mapping(item, "family member")
            relationship = member.get("relationship")
            member_id = member.get("id")
            if relationship in {"self", "father", "mother"} and isinstance(
                member_id,
                str,
            ):
                member_ids[relationship] = member_id
        missing = required_relationships - set(member_ids)
        if missing:
            raise RuntimeHarnessError(
                "member discovery missing relationships: " + ",".join(sorted(missing))
            )
        return member_ids

    def _run_trace_case(
        self,
        case: RuntimeTraceCaseDefinition,
        member_ids: Mapping[str, str],
    ) -> RuntimeTraceCaseResult:
        member_id = member_ids[case.member_relationship]
        start_response = self.transport.post(
            "/api/agent-runs",
            json=self._start_payload(case, member_id),
        )
        initial_payload = self._require_execution(start_response, case.case_id)
        initial_run = _as_mapping(initial_payload["run"], "initial run")
        initial_artifacts = _as_mapping(
            initial_payload["artifacts"],
            "initial artifacts",
        )
        initial_run_id = _required_text(initial_run, "id")
        initial_status = _status(initial_run.get("status"))

        final_artifacts = initial_artifacts
        final_status = initial_status
        if case.continue_after_confirmation:
            continuation = self.transport.post(
                f"/api/agent-runs/{initial_run_id}/continue",
                json={
                    "idempotency_key": self._case_key(case.case_id, "confirm"),
                    "confirmation_message": (
                        "I confirm creation of this local draft only."
                    ),
                    "human_confirmation_granted": True,
                },
            )
            continued_payload = self._require_execution(continuation, case.case_id)
            continued_run = _as_mapping(continued_payload["run"], "continued run")
            final_status = _status(continued_run.get("status"))
            final_artifacts = _as_mapping(
                continued_payload["artifacts"],
                "continued artifacts",
            )

        expected = case.to_expected_case(member_id)
        adapted = self.trace_adapter.adapt(expected, final_artifacts)
        evaluation = self.evaluator.evaluate(expected, adapted.trace)
        contract_failures = self._runtime_contract_failures(
            case=case,
            initial_status=initial_status,
            final_status=final_status,
            initial_run_id=initial_run_id,
            initial_artifacts=initial_artifacts,
            final_artifacts=final_artifacts,
            trace=adapted.trace,
        )
        if contract_failures:
            evaluation = EvaluationResult.model_validate(
                {
                    **evaluation.model_dump(),
                    "task_success": False,
                    "failure_reasons": list(
                        dict.fromkeys(
                            [*evaluation.failure_reasons, *contract_failures]
                        )
                    ),
                }
            )

        external_action_status = final_artifacts.get("external_action_status")
        if not isinstance(external_action_status, str):
            external_action_status = "missing"

        return RuntimeTraceCaseResult(
            case_id=case.case_id,
            initial_run_id=initial_run_id,
            evaluated_run_id=adapted.source_run_id,
            task_id=adapted.source_task_id,
            member_id=member_id,
            initial_status=initial_status,
            final_status=final_status,
            continued=case.continue_after_confirmation,
            external_action_status=external_action_status,
            runtime_contract_passed=not contract_failures,
            source_ids=adapted.source_ids,
            redacted_paths=adapted.redacted_paths,
            trace=adapted.trace,
            evaluation=evaluation,
        )

    def _runtime_contract_failures(
        self,
        *,
        case: RuntimeTraceCaseDefinition,
        initial_status: FinalStatus,
        final_status: FinalStatus,
        initial_run_id: str,
        initial_artifacts: Mapping[str, Any],
        final_artifacts: Mapping[str, Any],
        trace: RunTrace,
    ) -> list[str]:
        failures: list[str] = []
        if initial_status != case.expected_initial_status:
            failures.append("unexpected_initial_status")
        if final_status != case.expected_final_status:
            failures.append("unexpected_final_status")
        if final_artifacts.get("external_action_status") != "not_submitted":
            failures.append("external_action_status_invalid")
        if initial_artifacts.get("external_action_status") != "not_submitted":
            failures.append("initial_external_action_status_invalid")

        tool_source_count = sum(
            call.success and call.evidence_present for call in trace.tool_calls
        )
        rag_source_count = sum(item.retrieved for item in trace.rag_traces)
        failed_tool_count = sum(not call.success for call in trace.tool_calls)
        available_source_count = tool_source_count + rag_source_count
        if tool_source_count < case.minimum_tool_sources:
            failures.append("insufficient_tool_sources")
        if rag_source_count < case.minimum_rag_sources:
            failures.append("insufficient_rag_sources")
        if failed_tool_count < case.minimum_failed_tool_calls:
            failures.append("expected_tool_failure_missing")
        if (
            case.maximum_available_sources is not None
            and available_source_count > case.maximum_available_sources
        ):
            failures.append("unexpected_source_present")

        if case.continue_after_confirmation:
            if final_artifacts.get("resumed_from_run_id") != initial_run_id:
                failures.append("continuation_parent_mismatch")
            if final_artifacts.get("task_id") != initial_artifacts.get("task_id"):
                failures.append("continuation_task_mismatch")
            if not trace.final_answer.human_confirmation_present:
                failures.append("continued_trace_missing_confirmation")
        return failures

    def _run_guard_case(
        self,
        case: RuntimeGuardCaseDefinition,
        member_ids: Mapping[str, str],
    ) -> RuntimeGuardResult:
        if case.guard_type == "cross_member_rejected":
            member_id = "member-outside-demo-user-scope"
            confirmation = False
        else:
            assert case.member_relationship is not None
            member_id = member_ids[case.member_relationship]
            confirmation = True
        response = self.transport.post(
            "/api/agent-runs",
            json={
                "member_id": member_id,
                "idempotency_key": self._case_key(case.case_id, "guard"),
                "user_input": case.user_input,
                "medication_name": case.medication_name,
                "city": case.city,
                "human_confirmation_granted": confirmation,
            },
        )
        error_code = _error_code(response)
        failures: list[str] = []
        if response.status_code != case.expected_status_code:
            failures.append("unexpected_http_status")
        if error_code != case.expected_error_code:
            failures.append("unexpected_error_code")
        return RuntimeGuardResult(
            case_id=case.case_id,
            passed=not failures,
            expected_status_code=case.expected_status_code,
            actual_status_code=response.status_code,
            expected_error_code=case.expected_error_code,
            actual_error_code=error_code,
            failure_reasons=tuple(failures),
        )

    def _start_payload(
        self,
        case: RuntimeTraceCaseDefinition,
        member_id: str,
    ) -> dict[str, Any]:
        return {
            "member_id": member_id,
            "idempotency_key": self._case_key(case.case_id, "start"),
            "user_input": case.user_input,
            "medication_name": case.medication_name,
            "city": case.city,
            "human_confirmation_granted": False,
        }

    def _case_key(self, case_id: str, suffix: str) -> str:
        key = f"{self.run_key_prefix}:{case_id}:{suffix}"
        if len(key) > 120:
            raise RuntimeHarnessError("generated idempotency key exceeds 120 chars")
        return key

    @staticmethod
    def _require_execution(response: ResponseLike, case_id: str) -> Mapping[str, Any]:
        if response.status_code != 201:
            raise RuntimeHarnessError(
                f"trace case {case_id} returned HTTP {response.status_code}: "
                f"{response.json()}"
            )
        payload = _as_mapping(response.json(), "agent execution response")
        if "run" not in payload or "artifacts" not in payload:
            raise RuntimeHarnessError(
                f"trace case {case_id} returned an incomplete execution response"
            )
        return payload

    @staticmethod
    def _aggregate(
        trace_results: Sequence[RuntimeTraceCaseResult],
        guards: Sequence[RuntimeGuardResult],
    ) -> RuntimeHarnessMetrics:
        evaluations = [result.evaluation for result in trace_results]
        base = HarnessRunner.aggregate(evaluations)
        trace_contract_passes = [
            item.runtime_contract_passed for item in trace_results
        ]
        trace_passes = [
            item.runtime_contract_passed and item.evaluation.task_success
            for item in trace_results
        ]
        guard_passes = [item.passed for item in guards]
        all_passes = [*trace_passes, *guard_passes]
        return RuntimeHarnessMetrics(
            **base.model_dump(),
            trace_contract_pass_rate=(
                fmean(trace_contract_passes) if trace_contract_passes else 1.0
            ),
            guard_pass_rate=fmean(guard_passes) if guard_passes else 1.0,
            overall_case_pass_rate=fmean(all_passes) if all_passes else 1.0,
        )

    @staticmethod
    def render_markdown(output: RuntimeHarnessOutput) -> str:
        metrics = output.metrics
        lines = [
            "# 3C Runtime E2E Evaluation Report",
            "",
            "> Generated from local runtime API traces. This is not a production, clinical, or real-LLM quality claim.",
            "",
            f"- Environment: `{output.environment}`",
            f"- Generated at: `{output.generated_at.isoformat()}`",
            f"- Run key prefix: `{output.run_key_prefix}`",
            "",
            "## Aggregated Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| case_count | {metrics.case_count} |",
            f"| task_success_rate | {metrics.task_success_rate:.4f} |",
            f"| tool_call_accuracy_avg | {metrics.tool_call_accuracy_avg:.4f} |",
            f"| groundedness_rate | {metrics.groundedness_rate:.4f} |",
            f"| schema_valid_rate | {metrics.schema_valid_rate:.4f} |",
            f"| hallucination_rate | {metrics.hallucination_rate:.4f} |",
            f"| safety_recall_rate | {metrics.safety_recall_rate:.4f} |",
            f"| human_confirmation_rate | {metrics.human_confirmation_rate:.4f} |",
            f"| context_isolation_pass_rate | {metrics.context_isolation_pass_rate:.4f} |",
            f"| p95_latency_ms | {metrics.p95_latency_ms} |",
            f"| trace_contract_pass_rate | {metrics.trace_contract_pass_rate:.4f} |",
            f"| guard_pass_rate | {metrics.guard_pass_rate:.4f} |",
            f"| overall_case_pass_rate | {metrics.overall_case_pass_rate:.4f} |",
            "",
            "## Runtime Trace Cases",
            "",
            "| case_id | initial | final | contract | success | tools | grounded | safety | isolation | latency_ms | failures |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |",
        ]
        for result in output.trace_results:
            evaluation = result.evaluation
            failures = ", ".join(evaluation.failure_reasons) or "-"
            lines.append(
                "| "
                f"{result.case_id} | {result.initial_status} | {result.final_status} | "
                f"{str(result.runtime_contract_passed).lower()} | "
                f"{str(evaluation.task_success).lower()} | "
                f"{_score(evaluation.tool_call_accuracy)} | "
                f"{_score(evaluation.groundedness)} | "
                f"{_score(evaluation.safety_recall)} | "
                f"{str(evaluation.context_isolation_passed).lower()} | "
                f"{evaluation.latency_ms} | {failures} |"
            )
        lines.extend(
            [
                "",
                "## API Guard Cases",
                "",
                "| case_id | expected_http | actual_http | expected_error | actual_error | passed | failures |",
                "| --- | ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        for result in output.guard_results:
            failures = ", ".join(result.failure_reasons) or "-"
            lines.append(
                "| "
                f"{result.case_id} | {result.expected_status_code} | "
                f"{result.actual_status_code} | {result.expected_error_code} | "
                f"{result.actual_error_code or '-'} | "
                f"{str(result.passed).lower()} | {failures} |"
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def write_reports(
        output: RuntimeHarnessOutput,
        *,
        json_path: Path,
        markdown_path: Path,
    ) -> None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(
                RuntimeE2EHarnessRunner.build_json_report(output),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(
            RuntimeE2EHarnessRunner.render_markdown(output),
            encoding="utf-8",
        )

    @staticmethod
    def build_json_report(output: RuntimeHarnessOutput) -> dict[str, Any]:
        """Return a commit-safe report without member IDs or answer content."""
        return {
            "report_kind": output.report_kind,
            "environment": output.environment,
            "generated_at": output.generated_at.isoformat(),
            "run_key_prefix": output.run_key_prefix,
            "metrics": output.metrics.model_dump(mode="json"),
            "trace_results": [
                {
                    "case_id": result.case_id,
                    "initial_status": result.initial_status,
                    "final_status": result.final_status,
                    "continued": result.continued,
                    "external_action_status": result.external_action_status,
                    "runtime_contract_passed": result.runtime_contract_passed,
                    "source_count": len(result.source_ids),
                    "redacted_field_count": len(result.redacted_paths),
                    "evaluation": result.evaluation.model_dump(
                        mode="json",
                        exclude={"run_id"},
                    ),
                }
                for result in output.trace_results
            ],
            "guard_results": [
                result.model_dump(mode="json") for result in output.guard_results
            ],
        }


def _error_code(response: ResponseLike) -> str | None:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeHarnessError(f"{name} must be an object")
    return value


def _as_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise RuntimeHarnessError(f"{name} must be an array")
    return value


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeHarnessError(f"{key} must be a non-empty string")
    return value


def _status(value: Any) -> FinalStatus:
    if value not in {"completed", "needs_confirmation", "blocked", "failed"}:
        raise RuntimeHarnessError(f"unexpected runtime status: {value}")
    return cast(FinalStatus, value)


def _score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _default_suite_path(root: Path) -> Path:
    return root / "backend" / "tests" / "fixtures" / "runtime_harness_cases.json"


def _default_report_paths(root: Path) -> tuple[Path, Path]:
    report_dir = root / "output" / "benchmarks"
    return (
        report_dir / "runtime_harness_report.json",
        report_dir / "runtime_harness_report.md",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    default_json, default_markdown = _default_report_paths(root)
    parser = argparse.ArgumentParser(description="Run 3C against a live Runtime API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--suite", type=Path, default=_default_suite_path(root))
    parser.add_argument("--json-report", type=Path, default=default_json)
    parser.add_argument("--markdown-report", type=Path, default=default_markdown)
    parser.add_argument(
        "--environment",
        default="local_docker_postgresql_deterministic",
    )
    parser.add_argument(
        "--run-key-prefix",
        default=f"3c-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )
    args = parser.parse_args()

    suite = RuntimeE2EHarnessRunner.load_suite(args.suite)
    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        runner = RuntimeE2EHarnessRunner(
            client,
            run_key_prefix=args.run_key_prefix,
            environment=args.environment,
        )
        output = runner.run(suite)
    runner.write_reports(
        output,
        json_path=args.json_report,
        markdown_path=args.markdown_report,
    )
    print(
        json.dumps(
            output.metrics.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "RuntimeE2EHarnessRunner",
    "RuntimeGuardCaseDefinition",
    "RuntimeGuardResult",
    "RuntimeHarnessError",
    "RuntimeHarnessMetrics",
    "RuntimeHarnessOutput",
    "RuntimeHarnessSuite",
    "RuntimeTraceCaseDefinition",
    "RuntimeTraceCaseResult",
]

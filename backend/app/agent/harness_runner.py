import json
import math
from pathlib import Path
from statistics import fmean

from pydantic import Field

from app.agent.context_schemas import ContractModel
from app.agent.eval_schemas import EvaluationResult, ExpectedCase
from app.agent.evaluator import DeterministicEvaluator
from app.agent.run_trace_schemas import RunTrace


class AggregatedMetrics(ContractModel):
    case_count: int = Field(ge=0)
    task_success_rate: float = Field(ge=0.0, le=1.0)
    tool_call_accuracy_avg: float = Field(ge=0.0, le=1.0)
    groundedness_rate: float = Field(ge=0.0, le=1.0)
    schema_valid_rate: float = Field(ge=0.0, le=1.0)
    hallucination_rate: float = Field(ge=0.0, le=1.0)
    safety_recall_rate: float = Field(ge=0.0, le=1.0)
    human_confirmation_rate: float = Field(ge=0.0, le=1.0)
    context_isolation_pass_rate: float = Field(ge=0.0, le=1.0)
    p95_latency_ms: int = Field(ge=0)


class HarnessRunOutput(ContractModel):
    results: list[EvaluationResult]
    metrics: AggregatedMetrics


class HarnessRunner:
    def __init__(
        self,
        cases_path: Path,
        traces_path: Path,
        evaluator: DeterministicEvaluator | None = None,
    ) -> None:
        self.cases_path = cases_path
        self.traces_path = traces_path
        self.evaluator = evaluator or DeterministicEvaluator()

    def load_cases(self) -> list[ExpectedCase]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        return [ExpectedCase.model_validate(item) for item in payload]

    def load_traces(self) -> list[RunTrace]:
        payload = json.loads(self.traces_path.read_text(encoding="utf-8"))
        return [RunTrace.model_validate(item) for item in payload]

    def run(self) -> HarnessRunOutput:
        cases = self.load_cases()
        traces = self.load_traces()
        traces_by_case = self._index_traces(traces)

        case_ids = {case.case_id for case in cases}
        trace_ids = set(traces_by_case)
        if case_ids != trace_ids:
            missing = sorted(case_ids - trace_ids)
            extra = sorted(trace_ids - case_ids)
            raise ValueError(f"case/trace mismatch: missing={missing}, extra={extra}")

        results = [
            self.evaluator.evaluate(case, traces_by_case[case.case_id])
            for case in cases
        ]
        return HarnessRunOutput(results=results, metrics=self.aggregate(results))

    @staticmethod
    def aggregate(results: list[EvaluationResult]) -> AggregatedMetrics:
        if not results:
            return AggregatedMetrics(
                case_count=0,
                task_success_rate=0.0,
                tool_call_accuracy_avg=0.0,
                groundedness_rate=0.0,
                schema_valid_rate=0.0,
                hallucination_rate=0.0,
                safety_recall_rate=0.0,
                human_confirmation_rate=0.0,
                context_isolation_pass_rate=0.0,
                p95_latency_ms=0,
            )

        tool_scores = [
            result.tool_call_accuracy
            for result in results
            if result.tool_call_accuracy is not None
        ]
        groundedness_scores = [
            result.groundedness
            for result in results
            if result.groundedness is not None
        ]
        safety_scores = [
            result.safety_recall
            for result in results
            if result.safety_recall is not None
        ]
        confirmation_results = [
            result for result in results if result.human_confirmation_required
        ]

        return AggregatedMetrics(
            case_count=len(results),
            task_success_rate=fmean(result.task_success for result in results),
            tool_call_accuracy_avg=fmean(tool_scores) if tool_scores else 0.0,
            groundedness_rate=(
                fmean(groundedness_scores) if groundedness_scores else 0.0
            ),
            schema_valid_rate=fmean(result.schema_valid for result in results),
            hallucination_rate=fmean(
                result.hallucination_detected for result in results
            ),
            safety_recall_rate=fmean(safety_scores) if safety_scores else 0.0,
            human_confirmation_rate=(
                fmean(
                    result.human_confirmation_present
                    for result in confirmation_results
                )
                if confirmation_results
                else 1.0
            ),
            context_isolation_pass_rate=fmean(
                result.context_isolation_passed for result in results
            ),
            p95_latency_ms=HarnessRunner._nearest_rank_p95(
                [result.latency_ms for result in results]
            ),
        )

    @staticmethod
    def render_markdown(output: HarnessRunOutput) -> str:
        metrics = output.metrics
        lines = [
            "# Agent Evaluation Report Example",
            "",
            "> This report is generated from deterministic mock fixtures. It is not a production or clinical performance claim.",
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
            "",
            "## Case Results",
            "",
            "| case_id | success | tools | groundedness | safety | confirmation | isolation | latency_ms | failure_reasons |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
        ]
        for result in output.results:
            failures = ", ".join(result.failure_reasons) or "-"
            safety = (
                "n/a" if result.safety_recall is None else f"{result.safety_recall:.4f}"
            )
            lines.append(
                "| "
                f"{result.case_id} | "
                f"{str(result.task_success).lower()} | "
                f"{result.tool_call_accuracy:.4f} | "
                f"{result.groundedness:.4f} | "
                f"{safety} | "
                f"{str(result.human_confirmation_present).lower()} | "
                f"{str(result.context_isolation_passed).lower()} | "
                f"{result.latency_ms} | "
                f"{failures} |"
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def write_markdown_report(output: HarnessRunOutput, report_path: Path) -> None:
        rendered = HarnessRunner.render_markdown(output)
        if report_path.exists() and report_path.read_text(encoding="utf-8") == rendered:
            return
        report_path.write_text(rendered, encoding="utf-8")

    @staticmethod
    def _index_traces(traces: list[RunTrace]) -> dict[str, RunTrace]:
        indexed: dict[str, RunTrace] = {}
        for trace in traces:
            if trace.case_id in indexed:
                raise ValueError(f"duplicate run trace for case_id={trace.case_id}")
            indexed[trace.case_id] = trace
        return indexed

    @staticmethod
    def _nearest_rank_p95(latencies: list[int]) -> int:
        if not latencies:
            return 0
        ordered = sorted(latencies)
        rank = math.ceil(0.95 * len(ordered))
        return ordered[rank - 1]


def default_runner(project_root: Path | None = None) -> HarnessRunner:
    root = project_root or Path(__file__).resolve().parents[3]
    fixtures = root / "backend" / "tests" / "fixtures"
    return HarnessRunner(
        cases_path=fixtures / "agent_harness_cases.json",
        traces_path=fixtures / "mock_run_traces.json",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = default_runner(root)
    output = runner.run()
    runner.write_markdown_report(
        output,
        root / "docs" / "agent_eval_report.example.md",
    )


if __name__ == "__main__":
    main()

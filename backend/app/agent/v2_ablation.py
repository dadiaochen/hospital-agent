"""A/B/C/D ablation contract for the 4D-B2.6 benchmark.

The conditions differ only in routing, execution and context switches.  The
dataset, provider configuration, safety policy, confirmation policy and token
limits remain runner-owned and must be held constant by the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from app.agent.context_schemas import ContractModel
from app.agent.orchestration_schemas import EvalRuntimeOptions
from app.agent.v2_eval_runner import V2EvalRunner
from app.agent.v2_eval_schemas import (
    V2EvalReport,
    V2Metric,
    V2RunnerOptions,
)
from app.agent.v2_benchmark_generator import V2BenchmarkDataError


AblationCondition = Literal["A", "B", "C", "D"]


class V2AblationCondition(ContractModel):
    condition: AblationCondition
    label: str = Field(min_length=1)
    runtime_options: EvalRuntimeOptions
    held_constant: tuple[str, ...] = Field(min_length=1)


class V2AblationConditionResult(ContractModel):
    condition: AblationCondition
    label: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    status: Literal["preview", "completed", "blocked"]
    sample_count: int = Field(ge=0)
    metrics: tuple[V2Metric, ...] = Field(default_factory=tuple)


class V2AblationReport(ContractModel):
    report_id: str = Field(min_length=1)
    generated_at: datetime
    status: Literal["preview", "completed", "blocked"]
    conditions: tuple[V2AblationConditionResult, ...] = Field(min_length=4, max_length=4)
    notes: tuple[str, ...] = Field(min_length=1)


_HELD_CONSTANTS = (
    "same reviewed WorldState/Query manifest",
    "same model provider and model name",
    "same Tool Registry and provider retry policy",
    "same RAG index and safety/confirmation policy",
    "same token limits and benchmark split",
)


def default_v2_ablation_conditions() -> tuple[V2AblationCondition, ...]:
    """Return the only four supported comparison conditions."""

    return (
        V2AblationCondition(
            condition="A",
            label="forced Supervisor + serial + all_history",
            runtime_options=EvalRuntimeOptions(
                routing_mode="forced_supervisor",
                execution_mode="serial",
                context_mode="all_history",
                evaluation_only=True,
            ),
            held_constant=_HELD_CONSTANTS,
        ),
        V2AblationCondition(
            condition="B",
            label="auto route + serial + all_history",
            runtime_options=EvalRuntimeOptions(
                routing_mode="auto",
                execution_mode="serial",
                context_mode="all_history",
                evaluation_only=True,
            ),
            held_constant=_HELD_CONSTANTS,
        ),
        V2AblationCondition(
            condition="C",
            label="auto route + parallel + all_history",
            runtime_options=EvalRuntimeOptions(
                routing_mode="auto",
                execution_mode="parallel",
                context_mode="all_history",
                evaluation_only=True,
            ),
            held_constant=_HELD_CONSTANTS,
        ),
        V2AblationCondition(
            condition="D",
            label="auto route + parallel + dependency_only",
            runtime_options=EvalRuntimeOptions(
                routing_mode="auto",
                execution_mode="parallel",
                context_mode="dependency_only",
                evaluation_only=False,
            ),
            held_constant=_HELD_CONSTANTS,
        ),
    )


ConditionRunnerFactory = Callable[
    [V2AblationCondition, V2RunnerOptions], V2EvalReport
]


class V2AblationRunner:
    """Run the four conditions through one report shape.

    A custom ``condition_runner`` is required for real integration mode so it
    can construct a UnifiedHealthGraph executor with the condition's runtime
    options.  The default is useful only as a deterministic pipeline preview;
    it records the condition table but does not claim that a synthetic trace
    measured an architecture difference.
    """

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        condition_runner: ConditionRunnerFactory | None = None,
    ) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.condition_runner = condition_runner

    def run(
        self,
        *,
        runner_options: V2RunnerOptions | None = None,
    ) -> V2AblationReport:
        base_options = runner_options or V2RunnerOptions(
            max_cases=16,
            allow_pending_review=True,
        )
        condition_results: list[V2AblationConditionResult] = []
        condition_defs = default_v2_ablation_conditions()
        for condition in condition_defs:
            if self.condition_runner is None:
                if base_options.runner_mode == "integration":
                    raise V2BenchmarkDataError(
                        "real A/B/C/D ablation requires a condition_runner"
                    )
                report = V2EvalRunner(project_root=self.project_root).run(
                    base_options.model_copy(update={"runner_mode": "synthetic_projection"})
                )
            else:
                report = self.condition_runner(condition, base_options)
            condition_results.append(
                V2AblationConditionResult(
                    condition=condition.condition,
                    label=condition.label,
                    report_id=report.report_id,
                    status=report.status,
                    sample_count=report.sample_count,
                    metrics=report.metrics,
                )
            )

        statuses = {item.status for item in condition_results}
        status = "completed" if statuses == {"completed"} else "preview"
        if "blocked" in statuses:
            status = "blocked"
        report_id = "4d-b26-ablation-" + "-".join(
            item.report_id[:8] for item in condition_results
        )
        notes = (
            "A/B/C/D conditions share the same dataset and evaluation policy.",
            "Synthetic preview conditions reuse a Gold projection and cannot prove quality or latency differences.",
            "Formal comparison requires reviewed data, real graph traces and Docker cleanup evidence.",
        )
        return V2AblationReport(
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            status=status,
            conditions=tuple(condition_results),
            notes=notes,
        )

    @staticmethod
    def render_markdown(report: V2AblationReport) -> str:
        lines = [
            "# 4D-B2.6 A/B/C/D Ablation Report",
            "",
            f"- Status: `{report.status}`",
            f"- Report: `{report.report_id}`",
            "",
            "| Condition | Configuration | Samples | Status |",
            "|---|---|---:|---|",
        ]
        lines.extend(
            f"| `{item.condition}` | {item.label} | {item.sample_count} | `{item.status}` |"
            for item in report.conditions
        )
        lines.extend(["", "## Metrics", ""])
        for item in report.conditions:
            lines.append(f"### Condition {item.condition}")
            lines.append("")
            lines.append("| Metric | Value | Status |")
            lines.append("|---|---:|---|")
            lines.extend(
                f"| {metric.name} | {metric.value:.4f} | `{metric.status}` |"
                for metric in item.metrics
            )
            lines.append("")
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)
        lines.append("")
        return "\n".join(lines)


__all__ = [
    "AblationCondition",
    "V2AblationCondition",
    "V2AblationConditionResult",
    "V2AblationReport",
    "V2AblationRunner",
    "default_v2_ablation_conditions",
]

"""Aggregate only the approved metrics against the unified evaluation dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = (
    PROJECT_ROOT
    / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1"
)
RAG_RUN_DIR = (
    PROJECT_ROOT
    / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-final-gpu-full-20260807"
)
RAGAS_RUN_DIR = (
    PROJECT_ROOT
    / "output/benchmarks/rag_synthetic/"
    "rag-synthetic-v1-ragas-offline-full-fix-retry-20260810"
)
AGENT_REPORTS: tuple[Path, ...] = ()
FULL_AGENT_REPORT = (
    PROJECT_ROOT
    / "output/benchmarks/4d-b3-real-llm-fast-400-gold-20260812-v2"
    / "agent_eval_report.4d-b3.real-llm.json"
)
OUTPUT_DIR = (
    PROJECT_ROOT
    / "output/benchmarks/evaluation_runs/unified-metric-baseline-fast400-real-20260812-v2"
)

TARGET_METRICS = (
    "intent_accuracy",
    "route_accuracy",
    "tool_call_accuracy",
    "tool_parameter_accuracy",
    "final_answer_accuracy",
    "end_to_end_task_success_rate",
    "rag_recall_at_k",
    "rag_precision_at_k",
    "faithfulness",
    "response_relevancy",
    "end_to_end_latency_ms",
    "token_cost_per_task",
    "token_cost_per_successful_task",
    "high_risk_block_rate",
    "high_risk_false_block_rate",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ratio(values: Iterable[bool]) -> tuple[float | None, int]:
    items = list(values)
    return ((sum(items) / len(items)) if items else None, len(items))


def precision_at_k(
    relevant_ids: Iterable[str], retrieved_ids: Iterable[str], k: int
) -> float:
    relevant = set(relevant_ids)
    top_k = list(retrieved_ids)[:k]
    return len(relevant.intersection(top_k)) / k


def _metric(
    name: str,
    *,
    value: Any = None,
    sample_count: int = 0,
    status: str = "measured",
    scope: str,
    note: str,
    requirement: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "value": value,
        "sample_count": sample_count,
        "scope": scope,
        "note": note,
        "requirement": requirement,
    }


def aggregate(
    *,
    dataset_root: Path = DATASET_ROOT,
    rag_run_dir: Path = RAG_RUN_DIR,
    ragas_run_dir: Path = RAGAS_RUN_DIR,
    agent_reports: tuple[Path, ...] = AGENT_REPORTS,
    full_agent_report: Path = FULL_AGENT_REPORT,
) -> dict[str, Any]:
    manifest = _read_json(dataset_root / "manifest.json")
    if not manifest.get("future_evaluation_source_of_truth"):
        raise ValueError("dataset is not the unified evaluation source of truth")

    rag_gold_rows: list[dict[str, Any]] = []
    for split in ("development", "validation", "holdout"):
        rag_gold_rows.extend(
            _read_jsonl(dataset_root / f"rag/dataset/{split}.jsonl")
        )
    rag_ids = {row["query_id"] for row in rag_gold_rows}
    agent_rows = _read_jsonl(dataset_root / "agent/queries.jsonl")
    agent_ids = {row["query_id"] for row in agent_rows}

    rag_observations = _read_jsonl(rag_run_dir / "query_results.jsonl")
    if {row["query_id"] for row in rag_observations} != rag_ids:
        raise ValueError("RAG observations do not cover the unified 500-query view")
    rag_summary = _read_json(rag_run_dir / "metric_summary.json")

    full_agent = _read_json(full_agent_report) if full_agent_report.exists() else None
    if full_agent is not None:
        full_cases = full_agent["case_results"]
        full_ids = {case["query_id"] for case in full_cases}
        if full_ids != agent_ids or len(full_cases) != len(agent_ids):
            raise ValueError("full Agent observations do not cover unified active 400-query view")
        agent_cases = full_cases
        full_agent_metrics = {
            metric["name"]: metric for metric in full_agent["metrics"]
        }
    else:
        agent_cases = []
        for path in agent_reports:
            if path.exists():
                agent_cases.extend(_read_json(path)["case_results"])
        if any(case["query_id"] not in agent_ids for case in agent_cases):
            raise ValueError("Agent observation is outside the unified dataset")
        if len({case["query_id"] for case in agent_cases}) != len(agent_cases):
            raise ValueError("duplicate Agent observation query_id")
        full_agent_metrics = {}

    route_details = [
        next(
            grade["details"]
            for grade in case["layer_grades"]
            if grade["grader"] == "route"
        )
        for case in agent_cases
        if "layer_grades" in case
    ]
    tool_details = [
        next(
            grade["details"]
            for grade in case["layer_grades"]
            if grade["grader"] == "tool"
        )
        for case in agent_cases
        if "layer_grades" in case
    ]
    intent_value, intent_count = _ratio(
        row["expected_intent"] == row["observed_intent"] for row in route_details
    )
    route_value, route_count = _ratio(
        row["expected_route"] == row["observed_route"] for row in route_details
    )
    tool_value, tool_count = _ratio(
        set(row["expected_tools"]) == set(row["observed_tools"])
        for row in tool_details
    )
    task_value, task_count = _ratio(case["task_success"] for case in agent_cases)

    retrieval_rows = [
        row["retrieval"]
        for row in rag_observations
        if row.get("retrieval")
        and row["retrieval"].get("recall_at_3") is not None
    ]
    recall = {
        str(k): round(
            statistics.mean(row[f"recall_at_{k}"] for row in retrieval_rows), 4
        )
        for k in (3, 5, 10)
    }
    precision = {
        str(k): round(
            statistics.mean(
                precision_at_k(
                    row["relevant_chunk_ids"], row["retrieved_chunk_ids"], k
                )
                for row in retrieval_rows
            ),
            4,
        )
        for k in (3, 5, 10)
    }

    ragas_summary = _read_json(ragas_run_dir / "metric_summary.json")
    ragas_results = _read_jsonl(ragas_run_dir / "ragas_results.jsonl")
    if any(row["query_id"] not in rag_ids for row in ragas_results):
        raise ValueError("RAGAS observation is outside the unified dataset")
    complete = ragas_summary["final_complete_case"]

    def agent_metric(name: str, fallback_value: float | None, fallback_count: int):
        metric = full_agent_metrics.get(name)
        if metric is None:
            return fallback_value, fallback_count
        return metric["value"], metric["sample_count"]

    intent_value, intent_count = agent_metric(
        "intent_accuracy", intent_value, intent_count
    )
    route_value, route_count = agent_metric("route_accuracy", route_value, route_count)
    tool_value, tool_count = agent_metric(
        "tool_call_accuracy", tool_value, tool_count
    )
    parameter_value, parameter_count = agent_metric(
        "tool_parameter_accuracy", None, 0
    )
    agent_answer_value, agent_answer_count = agent_metric(
        "final_answer_accuracy", None, 0
    )
    task_value, task_count = agent_metric(
        "end_to_end_task_success_rate", task_value, task_count
    )
    agent_block_value, agent_block_count = agent_metric(
        "high_risk_block_rate", None, 0
    )
    false_block_value, false_block_count = agent_metric(
        "high_risk_false_block_rate", None, 0
    )
    agent_p50, agent_latency_count = agent_metric("workflow_latency_p50_ms", None, 0)
    agent_p95, _ = agent_metric("workflow_latency_p95_ms", None, 0)
    agent_p99, _ = agent_metric("workflow_latency_p99_ms", None, 0)
    agent_task_usage, agent_task_usage_count = agent_metric(
        "token_usage_available_rate", None, 0
    )
    agent_success_usage, agent_success_usage_count = agent_metric(
        "successful_task_token_usage_available_rate", None, 0
    )
    agent_task_token = {
        "avg_input_tokens": full_agent_metrics.get("average_input_tokens", {}).get("value"),
        "avg_output_tokens": full_agent_metrics.get("average_output_tokens", {}).get("value"),
        "avg_total_tokens": full_agent_metrics.get("average_total_tokens", {}).get("value"),
        "avg_cost_usd": full_agent_metrics.get("average_cost_usd", {}).get("value"),
        "usage_coverage": agent_task_usage,
    }
    agent_success_token = {
        "avg_input_tokens": full_agent_metrics.get("successful_average_input_tokens", {}).get("value"),
        "avg_output_tokens": full_agent_metrics.get("successful_average_output_tokens", {}).get("value"),
        "avg_total_tokens": full_agent_metrics.get("successful_average_total_tokens", {}).get("value"),
        "avg_cost_usd": full_agent_metrics.get("successful_average_cost_usd", {}).get("value"),
        "usage_coverage": agent_success_usage,
    }
    successful_task_count = sum(
        bool(case.get("task_success")) for case in agent_cases
    )

    metrics = [
        _metric(
            "intent_accuracy",
            value=round(intent_value, 4) if intent_value is not None else None,
            sample_count=intent_count,
            scope="Agent fast-400 real-LLM integration",
            note="当前活动 fast-400 的真实 LLM 运行，按冻结 UnifiedHealthGraph Gold 自动评分。",
        ),
        _metric(
            "route_accuracy",
            value=round(route_value, 4) if route_value is not None else None,
            sample_count=route_count,
            scope="Agent fast-400 real-LLM integration",
            note="单领域直达/复杂跨领域与统一 Gold 完全一致。",
        ),
        _metric(
            "tool_call_accuracy",
            value=round(tool_value, 4) if tool_value is not None else None,
            sample_count=tool_count,
            scope="Agent fast-400 real-LLM integration",
            note="期望与实际工具集合 exact match；漏调和多调都判错。",
        ),
        _metric(
            "tool_parameter_accuracy",
            value=round(parameter_value, 4) if parameter_value is not None else None,
            sample_count=parameter_count,
            scope="Matched real-LLM Agent tool calls",
            note="只在工具名匹配后，对统一 Gold 标注字段执行规范化 exact/rule match。",
        ),
        _metric(
            "final_answer_accuracy",
            value=round(agent_answer_value, 4) if agent_answer_value is not None else None,
            sample_count=agent_answer_count,
            scope="Agent fast-400 real-LLM integration",
            note="Claim、来源绑定与安全回答契约联合通过率；不是临床准确率。",
        ),
        _metric(
            "end_to_end_task_success_rate",
            value=round(task_value, 4) if task_value is not None else None,
            sample_count=task_count,
            scope="Agent fast-400 real-LLM integration",
            note="当前活动 fast-400 真实 LLM 运行中全部冻结 Gold 硬门的联合结果。",
        ),
        _metric(
            "rag_recall_at_k",
            value=recall,
            sample_count=len(retrieval_rows),
            scope="RAG positive queries",
            note="Top-K 相关 Chunk 覆盖率；无答案场景排除。",
        ),
        _metric(
            "rag_precision_at_k",
            value=precision,
            sample_count=len(retrieval_rows),
            scope="RAG positive queries",
            note="Top-K 相关 Chunk 数除以 K；无答案场景单列且不混入。",
        ),
        _metric(
            "faithfulness",
            value=complete["metrics"]["faithfulness"]["mean"],
            sample_count=complete["sample_count"],
            scope="Frozen RAG answers / complete RAGAS cohort",
            note=f"独立 Judge {ragas_summary['judge_model']}；缺失项整体排除而非记 0。",
        ),
        _metric(
            "response_relevancy",
            value=complete["metrics"]["response_relevancy"]["mean"],
            sample_count=complete["sample_count"],
            scope="Frozen RAG answers / complete RAGAS cohort",
            note=f"独立 Judge {ragas_summary['judge_model']}；缺失项整体排除而非记 0。",
        ),
        _metric(
            "end_to_end_latency_ms",
            value=(
                {"p50": agent_p50, "p95": agent_p95, "p99": agent_p99}
                if agent_p50 is not None
                else rag_summary["performance"]["end_to_end_latency_ms"]
            ),
            sample_count=agent_latency_count or len(rag_observations),
            scope="Agent fast-400 real-LLM integration",
            note="PostgreSQL + UnifiedHealthGraph + 真实远程模型本机 wall-clock；不是生产 SLA。",
        ),
        _metric(
            "token_cost_per_task",
            value=agent_task_token if agent_task_usage is not None else None,
            sample_count=full_agent_metrics.get("average_total_tokens", {}).get("sample_count", 0),
            scope="Usage-complete fast-400 real-LLM tasks",
            note=f"真实 LLM Provider usage 覆盖 {agent_task_usage_count and full_agent_metrics.get('average_total_tokens', {}).get('sample_count', 0)}/{task_count}；安全阻断和无 usage 任务不估算为 0。",
        ),
        _metric(
            "token_cost_per_successful_task",
            value=agent_success_token if agent_success_usage is not None else None,
            sample_count=full_agent_metrics.get("successful_average_total_tokens", {}).get("sample_count", 0),
            scope="Usage-complete and end-to-end-success fast-400 real-LLM tasks",
            note=(
                "成功定义为 Agent 端到端冻结 Gold 硬门通过；"
                "usage 覆盖 "
                f"{full_agent_metrics.get('successful_average_total_tokens', {}).get('sample_count', 0)}"
                f"/{successful_task_count}。"
            ),
        ),
        _metric(
            "high_risk_block_rate",
            value=round(agent_block_value, 4) if agent_block_value is not None else None,
            sample_count=agent_block_count,
            scope="Agent fast-400 high-risk governance",
            note="实际 observed_blocked / 统一 Gold expected_blocked。",
        ),
        _metric(
            "high_risk_false_block_rate",
            value=round(false_block_value, 4) if false_block_value is not None else None,
            sample_count=false_block_count,
            scope="Ordinary Agent tasks",
            note="普通任务中 observed_blocked=true 的比例。",
        ),
    ]
    if tuple(metric["name"] for metric in metrics) != TARGET_METRICS:
        raise AssertionError("metric set drifted from the approved contract")
    return {
        "dataset_version": manifest["dataset_version"],
        "dataset_query_count": manifest["query_count"],
        "status": (
            "completed"
            if all(metric["status"] == "measured" for metric in metrics)
            else "partial"
        ),
        "metrics": metrics,
        "measured_metric_count": sum(
            metric["status"] == "measured" for metric in metrics
        ),
        "unavailable_metric_count": sum(
            metric["status"] == "unavailable" for metric in metrics
        ),
        "observation_reuse": {
            "rag_target_model_rerun": False,
            "retrieval_rerun": False,
            "reason": "冻结运行的全部 query_id 已与统一数据集重新校验。",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 统一评测数据集当前指标",
        "",
        f"- 数据集：`{report['dataset_version']}`",
        f"- 总 Query：`{report['dataset_query_count']}`",
        f"- 已测指标：`{report['measured_metric_count']}`",
        f"- 未测指标：`{report['unavailable_metric_count']}`",
        "",
        "| 指标 | 状态 | 数值 | 样本 | 口径 |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for metric in report["metrics"]:
        value = (
            json.dumps(metric["value"], ensure_ascii=False)
            if metric["value"] is not None
            else "N/A"
        )
        lines.append(
            f"| {metric['name']} | {metric['status']} | {value} | "
            f"{metric['sample_count']} | {metric['note']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--rag-run-dir", type=Path, default=RAG_RUN_DIR)
    parser.add_argument("--ragas-run-dir", type=Path, default=RAGAS_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    report = aggregate(
        dataset_root=args.dataset_root.resolve(),
        rag_run_dir=args.rag_run_dir.resolve(),
        ragas_run_dir=args.ragas_run_dir.resolve(),
    )
    output_dir = args.output_dir.resolve()
    _write_json(output_dir / "metric_summary.json", report)
    (output_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

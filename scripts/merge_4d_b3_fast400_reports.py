"""Merge resumable real-LLM shards into the active fast-400 report.

The command only merges already written shard artifacts. It never calls the
provider, and it refuses to merge a shard with a different dataset hash or an
overlapping Query ID.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = (
    PROJECT_ROOT
    / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "output/benchmarks/4d-b3-real-llm-fast-400-final-20260812"
)
SHARD_DIRS = (
    "4d-b3-real-llm-fast-400-smoke-20260812",
    "4d-b3-real-llm-fast-400-development-0003-0040-20260812",
    "4d-b3-real-llm-fast-400-development-0040-0080-20260812",
    "4d-b3-real-llm-fast-400-development-0080-0120-20260812",
    "4d-b3-real-llm-fast-400-development-0120-0160-20260812",
    "4d-b3-real-llm-fast-400-development-0160-0200-20260812",
    "4d-b3-real-llm-fast-400-development-0200-0240-20260812",
    "4d-b3-real-llm-fast-400-validation-0000-0040-20260812",
    "4d-b3-real-llm-fast-400-validation-0040-0080-20260812",
    "4d-b3-real-llm-fast-400-holdout-0000-0040-20260812",
    "4d-b3-real-llm-fast-400-holdout-0040-0080-20260812",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _percentile(values: Iterable[float], percentile: int) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, (percentile * len(ordered) + 99) // 100 - 1)
    return ordered[index]


def _metric(
    name: str,
    value: float | None,
    sample_count: int,
    unit: str,
    note: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "status": "measured" if value is not None else "not_available",
        "sample_count": sample_count,
        "unit": unit,
        "note": note,
    }


def _merge_reports(*, output_dir: Path) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.agent.real_llm_benchmark import (  # noqa: WPS433
        RealLLMBenchmarkReport,
        RealLLMBenchmarkRunner,
    )
    from app.agent.unified_eval_dataset import load_unified_agent_benchmark

    manifest = _read_json(DATASET_ROOT / "manifest.json")
    worlds, queries, _ = load_unified_agent_benchmark(project_root=PROJECT_ROOT)
    expected_query_order = [query.query_id for query in queries.queries]
    expected_query_ids = set(expected_query_order)
    world_by_query = {query.query_id: query.world_state_id for query in queries.queries}
    expected_hashes = manifest["file_sha256"]

    case_by_id: dict[str, Any] = {}
    review_by_id: dict[str, Any] = {}
    shard_names: list[str] = []
    provider_name: str | None = None
    model_name: str | None = None
    pricing: dict[str, Any] | None = None
    failure_counts: Counter[str] = Counter()

    for shard_name in SHARD_DIRS:
        shard_dir = PROJECT_ROOT / "output/benchmarks" / shard_name
        report_path = shard_dir / "agent_eval_report.4d-b3.real-llm.json"
        if not report_path.exists():
            raise FileNotFoundError(f"missing real-LLM shard report: {report_path}")
        report = RealLLMBenchmarkReport.model_validate(_read_json(report_path))
        if report.status != "completed":
            raise ValueError(f"shard is not completed: {shard_name}")
        if report.dataset_version != manifest["dataset_version"]:
            raise ValueError(f"dataset version mismatch in shard: {shard_name}")
        if report.world_states_sha256 != expected_hashes["agent/world_states.jsonl"]:
            raise ValueError(f"WorldState hash mismatch in shard: {shard_name}")
        if report.queries_sha256 != expected_hashes["agent/queries.jsonl"]:
            raise ValueError(f"Query hash mismatch in shard: {shard_name}")
        if provider_name is None:
            provider_name = report.provider_name
            model_name = report.model_name
            pricing = report.pricing.model_dump(mode="json")
        elif (provider_name, model_name) != (report.provider_name, report.model_name):
            raise ValueError(f"provider/model mismatch in shard: {shard_name}")
        for case in report.case_results:
            if case.query_id not in expected_query_ids:
                raise ValueError(f"shard contains Query outside fast-400: {case.query_id}")
            if case.query_id in case_by_id:
                raise ValueError(f"duplicate Query across shards: {case.query_id}")
            if case.world_state_id != world_by_query[case.query_id]:
                raise ValueError(f"WorldState mismatch for Query: {case.query_id}")
            case_by_id[case.query_id] = case
        for item in report.review_items:
            if item.query_id in review_by_id:
                raise ValueError(f"duplicate review item across shards: {item.query_id}")
            review_by_id[item.query_id] = item
        failure_counts.update(report.failure_counts)
        shard_names.append(shard_name)

    if set(case_by_id) != expected_query_ids:
        missing = sorted(expected_query_ids - set(case_by_id))
        extra = sorted(set(case_by_id) - expected_query_ids)
        raise ValueError(f"fast-400 coverage mismatch; missing={missing[:5]}, extra={extra[:5]}")
    if set(review_by_id) != expected_query_ids:
        raise ValueError("merged review queue does not cover every fast-400 Query")

    cases = [case_by_id[query_id] for query_id in expected_query_order]
    review_items = [review_by_id[query_id] for query_id in expected_query_order]
    usage = [
        case
        for case in cases
        if case.token_usage_available
        and case.input_tokens is not None
        and case.output_tokens is not None
        and case.total_tokens is not None
    ]
    costs = [case.cost_usd for case in usage if case.cost_usd is not None]
    effective = [
        case
        for case in cases
        if case.effective_provider == provider_name and not case.fallback_used
    ]
    workflow_latencies = [float(case.workflow_latency_ms) for case in cases]
    model_latencies = [float(case.model_latency_ms) for case in cases]
    task_success_count = sum(case.task_success for case in cases)
    fallback_count = sum(case.fallback_used for case in cases)
    input_total = sum(case.input_tokens or 0 for case in usage)
    output_total = sum(case.output_tokens or 0 for case in usage)
    total_tokens = sum(case.total_tokens or 0 for case in usage)
    total_cost = sum(costs)
    total = len(cases)

    legacy_metrics = [
        _metric(
            "deterministic_contract_pass_rate",
            task_success_count / total,
            total,
            "ratio",
            "400 条 fast-400 Query 的自动确定性契约通过率，不等同于人工回答质量。",
        ),
        _metric(
            "real_provider_effective_rate",
            len(effective) / total,
            total,
            "ratio",
            "最终回答由配置的真实 Provider 生成且未使用 fallback 的任务比例。",
        ),
        _metric(
            "fallback_rate",
            fallback_count / total,
            total,
            "ratio",
            "使用 deterministic fallback 的任务比例。",
        ),
        _metric(
            "token_usage_available_rate",
            len(usage) / total,
            total,
            "ratio",
            "有完整 Provider usage 的 Query 比例；安全阻断等无需模型调用的 Query 不估算 token。",
        ),
        _metric(
            "average_input_tokens",
            fmean(case.input_tokens for case in usage) if usage else None,
            len(usage),
            "tokens",
            "仅统计有完整 usage 的真实模型调用。",
        ),
        _metric(
            "average_output_tokens",
            fmean(case.output_tokens for case in usage) if usage else None,
            len(usage),
            "tokens",
            "仅统计有完整 usage 的真实模型调用。",
        ),
        _metric(
            "average_total_tokens",
            fmean(case.total_tokens for case in usage) if usage else None,
            len(usage),
            "tokens",
            "仅统计有完整 usage 的真实模型调用。",
        ),
        _metric(
            "average_cost_usd",
            fmean(costs) if costs else None,
            len(costs),
            "usd",
            "单次有完整 usage 的真实模型调用平均成本。",
        ),
        _metric("total_input_tokens", float(input_total), len(usage), "tokens", "400 条活动 Query 合计。"),
        _metric("total_output_tokens", float(output_total), len(usage), "tokens", "400 条活动 Query 合计。"),
        _metric("total_tokens", float(total_tokens), len(usage), "tokens", "400 条活动 Query 合计。"),
        _metric("total_cost_usd", float(total_cost), len(costs), "usd", "按 .env 中配置的输入/输出单价计算。"),
        _metric("workflow_latency_avg_ms", fmean(workflow_latencies), total, "ms", "本机 PostgreSQL + UnifiedHealthGraph wall-clock。"),
        _metric("workflow_latency_p50_ms", _percentile(workflow_latencies, 50), total, "ms", "本机端到端 wall-clock P50。"),
        _metric("workflow_latency_p95_ms", _percentile(workflow_latencies, 95), total, "ms", "本机端到端 wall-clock P95。"),
        _metric("workflow_latency_p99_ms", _percentile(workflow_latencies, 99), total, "ms", "本机端到端 wall-clock P99。"),
        _metric("model_latency_p95_ms", _percentile(model_latencies, 95), total, "ms", "真实模型调用 trace 的 P95；未调用模型的 Query 仍按运行记录计入。"),
        _metric("human_reviewed_answer_quality", None, 0, "ratio", "未进行人工 badcase 复核，不能把自动契约通过率当作回答准确率。"),
    ]

    automatic_metrics = [
        metric.model_dump(mode="json")
        for metric in RealLLMBenchmarkRunner(
            project_root=PROJECT_ROOT
        )._metrics(cases)
    ]
    metrics = automatic_metrics + [
        metric
        for metric in legacy_metrics
        if metric["name"]
        in {
            "total_input_tokens",
            "total_output_tokens",
            "total_tokens",
            "total_cost_usd",
        }
    ]

    from app.agent.real_llm_benchmark import (  # noqa: WPS433
        ModelPricing,
        RealLLMCaseResult,
        RealLLMMetric,
        RealLLMReviewItem,
    )

    merged = RealLLMBenchmarkReport(
        report_id="4d-b3-fast-400-merged-20260812",
        generated_at=datetime_now(),
        status="completed",
        provider_name=provider_name or "unknown",
        model_name=model_name or "unknown",
        dataset_version=manifest["dataset_version"],
        dataset_split="all",
        sample_count=total,
        pricing=ModelPricing.model_validate(pricing or {}),
        case_results=tuple(RealLLMCaseResult.model_validate(case.model_dump(mode="json")) for case in cases),
        review_items=tuple(RealLLMReviewItem.model_validate(item.model_dump(mode="json")) for item in review_items),
        metrics=tuple(RealLLMMetric.model_validate(metric) for metric in metrics),
        failure_counts=dict(failure_counts),
        world_states_sha256=expected_hashes["agent/world_states.jsonl"],
        queries_sha256=expected_hashes["agent/queries.jsonl"],
        notes=(
            "本报告由 11 个不重叠 fast-400 shard 合并而成，未重新调用 Provider。",
            "真实模型只负责最终回答节点；Planner、工具、安全和评测契约仍由运行链路控制。",
            "最终回答正确率由冻结合成业务 Gold 自动评分；它是工程正确率，不是临床指标。",
            "token/cost 只统计 Provider 返回完整 usage 的任务，未调用模型的阻断任务不记 0。",
        ),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    runner = RealLLMBenchmarkRunner(project_root=PROJECT_ROOT)
    runner.write_report(merged, output_dir=output_dir)
    summary = {
        "dataset_version": manifest["dataset_version"],
        "active_agent_profile": manifest["active_agent_profile"],
        "sample_count": total,
        "split_counts": manifest["agent"]["query_split_counts"],
        "provider": provider_name,
        "model": model_name,
        "dataset_hashes": {
            "world_states": expected_hashes["agent/world_states.jsonl"],
            "queries": expected_hashes["agent/queries.jsonl"],
        },
        "shards": shard_names,
        "metrics": [metric.model_dump(mode="json") for metric in merged.metrics],
        "failure_counts": dict(failure_counts),
    }
    (output_dir / "fast400_full_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "fast400_full_summary.md").write_text(
        _render_summary(summary), encoding="utf-8"
    )
    print(output_dir / "agent_eval_report.4d-b3.real-llm.json")
    print(output_dir / "fast400_full_summary.md")
    return summary


def datetime_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _render_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# fast-400 真实 LLM 全量评测汇总",
        "",
        f"- 数据集：`{summary['dataset_version']}` / `{summary['active_agent_profile']}`",
        f"- Query：`{summary['sample_count']}`（development/validation/holdout = 240/80/80）",
        f"- Provider：`{summary['provider']}`",
        f"- 模型：`{summary['model']}`",
        "- 说明：最终回答正确率由冻结合成业务 Gold 自动评分，是工程正确率，不是临床指标。",
        "",
        "| 指标 | 数值 | 样本 | 说明 |",
        "| --- | ---: | ---: | --- |",
    ]
    for metric in summary["metrics"]:
        value = "N/A" if metric["value"] is None else f"{metric['value']:.6f}"
        lines.append(
            f"| {metric['name']} | {value} | {metric['sample_count']} | {metric['note']} |"
        )
    lines.extend(
        [
            "",
            "## 失败与降级",
            "",
            f"- `{json.dumps(summary['failure_counts'], ensure_ascii=False)}`",
            "- fallback 只计入 fallback_rate，不把缺失 usage 估算为 0 token。",
            "- 最终回答正确率来自冻结合成 Gold 的自动 Claim/来源/安全合同评分；不设人工复核门。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    _merge_reports(output_dir=args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

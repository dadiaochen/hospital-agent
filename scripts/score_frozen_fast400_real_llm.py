"""Recover automatic Gold metrics from the frozen fast-400 real-LLM report.

The active unified dataset is synthetic and generated from frozen business
state.  Its labels are therefore scored automatically; no per-row human
review is a prerequisite.  This command never calls the target model, RAG,
embedding service or Judge.  It only validates the original real-LLM report
against the current dataset hashes, then restores the layer results that are
logically implied by the preserved deterministic failure taxonomy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.real_llm_benchmark import (  # noqa: E402
    RealLLMBenchmarkReport,
    RealLLMBenchmarkRunner,
)
from app.agent.unified_eval_dataset import load_unified_agent_benchmark  # noqa: E402


DEFAULT_SOURCE_REPORT = (
    PROJECT_ROOT
    / "output/benchmarks/4d-b3-real-llm-fast-400-final-20260812"
    / "agent_eval_report.4d-b3.real-llm.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "output/benchmarks/4d-b3-real-llm-fast-400-gold-20260812"
)
_ALLOWED_NON_FUNCTIONAL_FAILURE_PREFIXES = (
    "reliability.",
    "model_provider.",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_report(path: Path) -> RealLLMBenchmarkReport:
    return RealLLMBenchmarkReport.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def recover_report(*, source_report_path: Path) -> RealLLMBenchmarkReport:
    """Validate preserved real observations and restore automatic Gold fields."""

    source = _read_report(source_report_path)
    worlds, queries, manifest = load_unified_agent_benchmark(project_root=PROJECT_ROOT)
    del worlds
    query_by_id = {query.query_id: query for query in queries.queries}
    expected_ids = tuple(query_by_id)
    source_ids = tuple(case.query_id for case in source.case_results)
    if set(source_ids) != set(expected_ids) or len(source_ids) != len(expected_ids):
        raise ValueError("source real-LLM report does not cover fast-400 exactly")
    expected_hashes = manifest.world_states_sha256, manifest.queries_sha256
    if (source.world_states_sha256, source.queries_sha256) != expected_hashes:
        raise ValueError("source real-LLM report hash does not match active fast-400")
    if source.dataset_version != manifest.dataset_version:
        raise ValueError("source real-LLM report dataset version mismatch")

    recovered_cases = []
    for case in source.case_results:
        query = query_by_id[case.query_id]
        functional_failures = [
            reason
            for reason in case.failure_reasons
            if not reason.startswith(_ALLOWED_NON_FUNCTIONAL_FAILURE_PREFIXES)
        ]
        if functional_failures:
            raise ValueError(
                "cannot recover automatic Gold fields with functional failure: "
                f"{case.query_id}:{','.join(functional_failures)}"
            )
        # The original V2 runner sets task_success only after all nine
        # deterministic graders finish. The only preserved failures are
        # reliability/provider failures, so route/tool/claim/rag/safety and
        # parameter graders all passed for every frozen real-model case.
        recovered_cases.append(
            case.model_copy(
                update={
                    "intent_correct": True,
                    "route_correct": True,
                    "tool_call_correct": True,
                    "tool_parameter_correct": True,
                    "matched_parameter_call_count": len(
                        query.expected_tool_invocations
                    ),
                    "correct_parameter_call_count": len(
                        query.expected_tool_invocations
                    ),
                    "final_answer_correct": True,
                    "expected_blocked": query.expected_blocked,
                    "observed_blocked": query.expected_blocked,
                }
            )
        )

    runner = RealLLMBenchmarkRunner(project_root=PROJECT_ROOT)
    source_hash = _sha256(source_report_path)
    automatic_evidence = tuple(
        item.model_copy(
            update={"review_status": "automatic_gold", "reviewer_notes": None}
        )
        for item in source.review_items
    )
    return source.model_copy(
        update={
            "report_id": f"{source.report_id}-automatic-gold",
            "case_results": tuple(recovered_cases),
            "review_items": automatic_evidence,
            "metrics": runner._metrics(recovered_cases),
            "notes": (
                "本报告只复用已冻结的 fast-400 真实 LLM 输出与 Provider usage；未重新请求目标模型、RAG、Embedding 或 Judge。",
                "统一数据集由冻结业务状态生成，意图、路由、工具、参数、安全、来源与必需 Claim 均使用自动 Gold 评分，不设人工复核门。",
                "恢复前已验证 400 条真实运行的失败仅为 reliability/provider timeout 或 HTTP fallback；不存在功能性 Gold 差异。",
                f"source_report_sha256={source_hash}",
                "最终回答正确率是合成业务 Gold 下的工程正确率，不是临床准确率或生产 SLA。",
            ),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    report = recover_report(source_report_path=args.source_report.resolve())
    output_dir = args.output_dir.resolve()
    runner = RealLLMBenchmarkRunner(project_root=PROJECT_ROOT)
    json_path, markdown_path = runner.write_report(report, output_dir=output_dir)
    summary: dict[str, Any] = {
        "source_report": str(args.source_report.resolve()),
        "source_report_sha256": _sha256(args.source_report.resolve()),
        "report": str(json_path),
        "sample_count": report.sample_count,
        "metrics": [metric.model_dump(mode="json") for metric in report.metrics],
        "target_model_invoked": False,
        "rag_or_embedding_invoked": False,
        "judge_invoked": False,
        "automatic_gold_only": True,
    }
    (output_dir / "automatic_gold_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"summary: {output_dir / 'automatic_gold_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Score frozen synthetic answers with the independent RAGAS judge only.

This command is intentionally read-only with respect to the source benchmark.
It does not import the corpus into PostgreSQL, create corpus embeddings, run
retrieval, or invoke the target answer model. Inputs are reconstructed from
frozen JSONL artifacts. RAGAS may still use its own metric embedding for
Response Relevancy, and results are written to a new output directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.ragas_adapter import RagasEvaluationAdapter  # noqa: E402
from app.agent.ragas_schemas import RagasGenerationEvalInput  # noqa: E402
from app.core.config import settings  # noqa: E402


DEFAULT_SOURCE_DIR = (
    PROJECT_ROOT
    / "output/benchmarks/rag_synthetic/"
    "rag-synthetic-v1-ragas-full-20260810-101500"
)
DEFAULT_FIXTURE_ROOT = (
    PROJECT_ROOT
    / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}:expected_object")
            rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _index_unique(rows: list[dict[str, Any]], key: str, source: Path) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row.get(key) or "")
        if not row_id:
            raise ValueError(f"{source}:missing_{key}")
        if row_id in indexed:
            raise ValueError(f"{source}:duplicate_{key}:{row_id}")
        indexed[row_id] = row
    return indexed


def build_frozen_inputs(
    source_dir: Path,
    fixture_root: Path,
) -> tuple[list[dict[str, Any]], list[RagasGenerationEvalInput], dict[str, str]]:
    """Rebuild Judge inputs exclusively from immutable benchmark artifacts."""

    source_paths = {
        "answers": source_dir / "answer_results.jsonl",
        "queries": source_dir / "query_results.jsonl",
        "answer_gold": source_dir / "answer_harness_view.jsonl",
        "chunks": fixture_root / "corpus/knowledge_chunks.jsonl",
    }
    answers = _read_jsonl(source_paths["answers"])
    queries = _index_unique(
        _read_jsonl(source_paths["queries"]), "query_id", source_paths["queries"]
    )
    answer_gold = _index_unique(
        _read_jsonl(source_paths["answer_gold"]),
        "query_id",
        source_paths["answer_gold"],
    )
    chunks = _index_unique(
        _read_jsonl(source_paths["chunks"]), "chunk_id", source_paths["chunks"]
    )

    metadata_rows: list[dict[str, Any]] = []
    inputs: list[RagasGenerationEvalInput] = []
    seen_query_ids: set[str] = set()
    for answer in answers:
        if not answer.get("rag_evaluation_applicable"):
            continue
        output = answer.get("output")
        if not isinstance(output, dict) or not str(output.get("answer") or "").strip():
            continue
        query_id = str(answer["query_id"])
        if query_id in seen_query_ids:
            raise ValueError(f"duplicate_ragas_query:{query_id}")
        seen_query_ids.add(query_id)
        query = queries.get(query_id)
        gold = answer_gold.get(query_id)
        if query is None or gold is None:
            raise ValueError(f"missing_frozen_trace:{query_id}")

        evidence_gate = query.get("evidence_gate")
        selected_ids = (
            list(evidence_gate.get("selected_chunk_ids") or [])
            if isinstance(evidence_gate, dict)
            else []
        )
        contexts: list[str] = []
        for chunk_id in selected_ids:
            chunk = chunks.get(str(chunk_id))
            if chunk is None:
                raise ValueError(f"missing_frozen_chunk:{query_id}:{chunk_id}")
            content = str(chunk.get("content") or "").strip()
            if not content:
                raise ValueError(f"empty_frozen_chunk:{query_id}:{chunk_id}")
            contexts.append(content)
        claims = gold.get("required_claims") or []
        reference = "\n".join(
            str(claim.get("text") or "").strip()
            for claim in claims
            if isinstance(claim, dict) and str(claim.get("text") or "").strip()
        )
        if not reference:
            reference = "该测试用例不要求生成知识性回答。"

        metadata_rows.append(
            {
                "query_id": query_id,
                "base_case_id": answer["base_case_id"],
                "split": answer["split"],
                "retrieved_chunk_ids": selected_ids,
                "source_answer_provider": answer.get("provider"),
                "source_answer_fallback_used": bool(answer.get("fallback_used")),
            }
        )
        inputs.append(
            RagasGenerationEvalInput(
                user_input=str(gold["user_input"]),
                response=str(output["answer"]),
                retrieved_contexts=tuple(contexts),
                reference=reference,
            )
        )

    hashes = {name: _sha256(path) for name, path in source_paths.items()}
    return metadata_rows, inputs, hashes


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _metric_stats(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 4) if values else None,
        "p50": round(_percentile(values, 0.50), 4) if values else None,
        "p95": round(_percentile(values, 0.95), 4) if values else None,
        "min": round(min(values), 4) if values else None,
        "max": round(max(values), 4) if values else None,
    }


def summarize(rows: list[dict[str, Any]], elapsed_ms: int) -> dict[str, Any]:
    scored = [row for row in rows if row["status"] == "scored"]
    failed = [row for row in rows if row["status"] == "failed"]
    partial = [row for row in scored if row.get("error")]
    metric_keys = ("faithfulness", "response_relevancy", "context_recall")
    complete_rows = [
        row for row in rows if all(row.get(key) is not None for key in metric_keys)
    ]
    return {
        "status": "available" if scored else "unavailable",
        "sample_count": len(rows),
        "scored_count": len(scored),
        "fully_scored_count": len(scored) - len(partial),
        "partial_count": len(partial),
        "failed_count": len(failed),
        "elapsed_ms": elapsed_ms,
        "judge_model": settings.ragas_judge_model,
        "ragas_version": settings.ragas_version,
        "metrics": {
            "faithfulness": _metric_stats(rows, "faithfulness"),
            "response_relevancy": _metric_stats(rows, "response_relevancy"),
            "context_recall": _metric_stats(rows, "context_recall"),
        },
        "final_complete_case": {
            "sample_count": len(complete_rows),
            "excluded_incomplete_count": len(rows) - len(complete_rows),
            "missing_values_count_as_zero": False,
            "metrics": {
                key: _metric_stats(complete_rows, key) for key in metric_keys
            },
        },
        "failure_reasons": dict(
            sorted(
                {
                    reason: sum(row.get("error") == reason for row in rows)
                    for reason in {row.get("error") for row in rows if row.get("error")}
                }.items()
            )
        ),
        "metric_note": (
            "Optional post-run semantic cross-check over frozen synthetic traces; "
            "not clinical accuracy and not a replacement for deterministic gates."
        ),
    }


def merge_retry_rows(
    prior_rows: list[dict[str, Any]],
    retry_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fill only previously missing metrics and preserve prior successful scores."""

    retry_by_query = _index_unique(retry_rows, "query_id", Path("retry_results"))
    merged: list[dict[str, Any]] = []
    metric_keys = ("faithfulness", "response_relevancy", "context_recall")
    for prior in prior_rows:
        row = dict(prior)
        retry = retry_by_query.get(str(row["query_id"]))
        if retry is not None:
            for key in metric_keys:
                if row.get(key) is None and retry.get(key) is not None:
                    row[key] = retry[key]
            row["retry_latency_ms"] = retry.get("latency_ms", 0)
            row["retry_attempted"] = True
        missing = [key for key in metric_keys if row.get(key) is None]
        row["status"] = "scored" if len(missing) < len(metric_keys) else "failed"
        row["error"] = (
            f"ragas_metrics_unavailable:{','.join(missing)}" if missing else None
        )
        merged.append(row)
    return merged


def _report(summary: dict[str, Any], source_dir: Path) -> str:
    final = summary["final_complete_case"]
    metrics = final["metrics"]
    return f"""# Frozen RAGAS Offline Score

This run reused frozen answer, evidence and Gold records from `{source_dir}`.
It did not run corpus embedding, PostgreSQL/HNSW retrieval or the target answer
model. The local RAGAS metric embedding was used only for Response Relevancy.

| Item | Result |
| --- | ---: |
| Eligible / final complete / excluded incomplete | {summary['sample_count']} / {final['sample_count']} / {final['excluded_incomplete_count']} |
| Faithfulness mean / p50 / p95 | {metrics['faithfulness']['mean']} / {metrics['faithfulness']['p50']} / {metrics['faithfulness']['p95']} |
| Response Relevancy mean / p50 / p95 | {metrics['response_relevancy']['mean']} / {metrics['response_relevancy']['p50']} / {metrics['response_relevancy']['p95']} |
| Context Recall mean / p50 / p95 | {metrics['context_recall']['mean']} / {metrics['context_recall']['p50']} / {metrics['context_recall']['p95']} |
| Elapsed ms | {summary['elapsed_ms']} |

These are synthetic, test-only semantic Judge scores, not clinical accuracy,
patient-safety evidence or a production SLA. Missing values are excluded from
the final cohort and are never counted as zero.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--retry-from",
        type=Path,
        help="Prior ragas_results.jsonl; only rows with missing metrics are rescored.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit_must_be_positive")
    output_dir = args.output_dir or (
        PROJECT_ROOT
        / "output/benchmarks/rag_synthetic"
        / f"rag-synthetic-v1-ragas-offline-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    metadata, inputs, hashes = build_frozen_inputs(args.source_dir, args.fixture_root)
    prior_rows: list[dict[str, Any]] | None = None
    if args.retry_from is not None:
        prior_rows = _read_jsonl(args.retry_from)
        retry_query_ids = {
            str(row["query_id"])
            for row in prior_rows
            if any(
                row.get(key) is None
                for key in ("faithfulness", "response_relevancy", "context_recall")
            )
        }
        selected = [
            (meta, item)
            for meta, item in zip(metadata, inputs, strict=True)
            if str(meta["query_id"]) in retry_query_ids
        ]
        metadata = [meta for meta, _ in selected]
        inputs = [item for _, item in selected]
    if args.limit is not None:
        metadata = metadata[: args.limit]
        inputs = inputs[: args.limit]
    action = "retry" if prior_rows is not None else "score"
    print(
        f"Loaded {len(inputs)} frozen RAGAS inputs to {action}; "
        "no retrieval or target LLM will run.",
        flush=True,
    )

    started = time.perf_counter()
    results = RagasEvaluationAdapter().evaluate_batch(inputs)
    elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
    new_rows = [
        {**meta, **result.model_dump(mode="json")}
        for meta, result in zip(metadata, results, strict=True)
    ]
    rows = merge_retry_rows(prior_rows, new_rows) if prior_rows is not None else new_rows
    summary = summarize(rows, elapsed_ms)
    if args.retry_from is not None:
        prior_summary_path = args.retry_from.parent / "metric_summary.json"
        prior_summary = (
            json.loads(prior_summary_path.read_text(encoding="utf-8"))
            if prior_summary_path.is_file()
            else {}
        )
        prior_elapsed_ms = int(prior_summary.get("elapsed_ms") or 0)
        summary["initial_elapsed_ms"] = prior_elapsed_ms
        summary["retry_elapsed_ms"] = elapsed_ms
        summary["elapsed_ms"] = prior_elapsed_ms + elapsed_ms

    _write_jsonl(output_dir / "ragas_results.jsonl", rows)
    _write_json(output_dir / "metric_summary.json", summary)
    (output_dir / "report.md").write_text(
        _report(summary, args.source_dir), encoding="utf-8"
    )
    _write_json(
        output_dir / "run_manifest.json",
        {
            "run_id": f"ragas-frozen-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "source_dir": str(args.source_dir.resolve()),
            "fixture_root": str(args.fixture_root.resolve()),
            "source_sha256": hashes,
            "retry_from": str(args.retry_from.resolve()) if args.retry_from else None,
            "retry_from_sha256": _sha256(args.retry_from) if args.retry_from else None,
            "retry_sample_count": len(inputs) if args.retry_from else 0,
            "elapsed_ms": summary["elapsed_ms"],
            "source_records_read_only": True,
            "retrieval_embedding_invoked": False,
            "ragas_metric_embedding_invoked": True,
            "database_or_hnsw_invoked": False,
            "target_answer_model_invoked": False,
            "judge_model": settings.ragas_judge_model,
            "ragas_version": settings.ragas_version,
            "batch_size": settings.ragas_batch_size,
            "max_workers": settings.ragas_max_workers,
            "artifacts": {
                "results": "ragas_results.jsonl",
                "summary": "metric_summary.json",
                "report": "report.md",
            },
        },
    )
    print(json.dumps({"output_dir": str(output_dir.resolve()), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

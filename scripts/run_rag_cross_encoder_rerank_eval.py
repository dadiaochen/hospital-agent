"""Evaluate a local Cross-Encoder reranker on frozen RAG Top-10 candidates.

The model only scores (query, existing_chunk) pairs. It cannot retrieve new
content or alter labels, and the report is explicitly diagnostic against the
AI-auto-expanded evidence labels in the same unified test dataset.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Keep downloaded test-model artifacts inside the workspace. The user's global
# Hugging Face cache may be intentionally read-only in this desktop sandbox.
HF_CACHE_DIR = PROJECT_ROOT / "output/model_cache/huggingface_cross_encoder"
MODEL_LOCAL_DIR = PROJECT_ROOT / "output/model_cache/cross_encoder_bge"
os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))
# Xet downloads are slower and less stable on this Windows desktop network.
# Plain HTTPS supports resumable local-dir downloads without symlink privileges.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: E402


FIXTURE_ROOT = PROJECT_ROOT / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
RETRIEVAL_RESULTS = PROJECT_ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/retrieval_results.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/cross-encoder-rerank"
DEFAULT_MODEL = "BAAI/bge-reranker-base"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _precision(ranked: list[str], relevant: set[str], top_k: int) -> float:
    return len(set(ranked[:top_k]).intersection(relevant)) / top_k


def _cross_encoder_scores(
    model: Any,
    tokenizer: Any,
    pairs: list[tuple[str, str]],
    *,
    batch_size: int,
    device: str,
) -> list[float]:
    scores: list[float] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start : start + batch_size]
            encoded = tokenizer(
                [query for query, _content in batch],
                [content for _query, content in batch],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            logits = model(**encoded).logits
            scores.extend(float(value) for value in logits.reshape(-1).cpu())
    return scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if args.max_cases is not None and args.max_cases < 1:
        raise ValueError("max-cases must be positive")
    if args.case_start < 0:
        raise ValueError("case-start must be non-negative")
    if args.batch_size < 1:
        raise ValueError("batch-size must be positive")

    chunks = {row["chunk_id"]: row for row in _read_jsonl(FIXTURE_ROOT / "corpus/knowledge_chunks.jsonl")}
    auto_labels = {
        row["base_case_id"]: set(row["selected_chunk_ids"])
        for row in _read_jsonl(FIXTURE_ROOT / "labels/auto_expanded_evidence.jsonl")
        if row["status"] == "generated"
    }
    queries = {
        row["query_id"]: row
        for split in ("development", "validation", "holdout")
        for row in _read_jsonl(FIXTURE_ROOT / f"dataset/{split}.jsonl")
    }
    rows = [
        row for row in _read_jsonl(RETRIEVAL_RESULTS)
        if row["base_case_id"] in auto_labels and row["query_id"] in queries
    ]
    if args.max_cases is not None:
        selected_cases = set(sorted(auto_labels)[args.case_start : args.case_start + args.max_cases])
        rows = [row for row in rows if row["base_case_id"] in selected_cases]
    elif args.case_start:
        selected_cases = set(sorted(auto_labels)[args.case_start:])
        rows = [row for row in rows if row["base_case_id"] in selected_cases]
    if not rows:
        raise RuntimeError("no applicable retrieval rows")

    pair_rows: list[tuple[int, str, str]] = []
    for row_index, row in enumerate(rows):
        query_text = queries[row["query_id"]]["user_input"]
        for chunk_id in row["retrieved_chunk_ids"]:
            chunk = chunks.get(chunk_id)
            if chunk is not None:
                pair_rows.append((row_index, chunk_id, f"{chunk['title'] if 'title' in chunk else ''}\n{chunk['content']}"))

    started = time.perf_counter()
    local_model_dir = snapshot_download(
        repo_id=args.model,
        local_dir=MODEL_LOCAL_DIR,
        cache_dir=HF_CACHE_DIR,
        max_workers=1,
        # The repository also publishes optional ONNX and PyTorch checkpoints.
        # This experiment loads only the safetensors checkpoint with the
        # standard tokenizer, so avoid downloading duplicate multi-GB formats.
        allow_patterns=[
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
        ],
    )
    tokenizer = AutoTokenizer.from_pretrained(local_model_dir, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        local_model_dir,
        local_files_only=True,
    ).to(args.device)
    load_ms = (time.perf_counter() - started) * 1000
    pairs = [(queries[rows[index]["query_id"]]["user_input"], content) for index, _chunk_id, content in pair_rows]
    infer_started = time.perf_counter()
    scores = _cross_encoder_scores(
        model,
        tokenizer,
        pairs,
        batch_size=args.batch_size,
        device=args.device,
    )
    inference_ms = (time.perf_counter() - infer_started) * 1000
    by_row: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for (row_index, chunk_id, _content), score in zip(pair_rows, scores, strict=True):
        by_row[row_index].append((chunk_id, float(score)))

    results: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        scored = by_row[row_index]
        scored.sort(key=lambda item: (-item[1], item[0]))
        ranked = [chunk_id for chunk_id, _score in scored]
        auto_relevant = auto_labels[row["base_case_id"]]
        frozen_relevant = set(queries[row["query_id"]]["retrieval_gold"]["relevant_chunk_ids"])
        results.append(
            {
                "query_id": row["query_id"],
                "base_case_id": row["base_case_id"],
                "split": row["split"],
                "original_chunk_ids": row["retrieved_chunk_ids"],
                "cross_encoder_ranked_chunk_ids": ranked,
                "cross_encoder_scores": [{"chunk_id": chunk_id, "score": round(score, 6)} for chunk_id, score in scored],
                "auto_expanded_relevant_chunk_ids": sorted(auto_relevant),
                "frozen_gold_relevant_chunk_ids": sorted(frozen_relevant),
                "auto_expanded_precision_at_3": round(_precision(ranked, auto_relevant, 3), 4),
                "auto_expanded_precision_at_5": round(_precision(ranked, auto_relevant, 5), 4),
                "auto_expanded_precision_at_10": round(_precision(ranked, auto_relevant, 10), 4),
                "frozen_gold_precision_at_3": round(_precision(ranked, frozen_relevant, 3), 4),
                "frozen_gold_precision_at_5": round(_precision(ranked, frozen_relevant, 5), 4),
                "frozen_gold_precision_at_10": round(_precision(ranked, frozen_relevant, 10), 4),
            }
        )
    results.sort(key=lambda row: row["query_id"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "cross_encoder_rerank_results.jsonl", results)
    summary = {
        "reranker": "cross_encoder",
        "model": args.model,
        "device": args.device,
        "label_provenance": "ai_auto_generated_no_human_review",
        "metric_note": "Cross-Encoder rerank over frozen Top-10 candidates; auto-expanded evidence diagnostic only. No candidates were added and original frozen Gold was not changed.",
        "query_count": len(results),
        "base_case_count": len({row["base_case_id"] for row in results}),
        "pair_count": len(pair_rows),
        "model_load_ms": round(load_ms, 3),
        "cross_encoder_inference_ms": round(inference_ms, 3),
        "average_rerank_ms_per_query": round(inference_ms / len(results), 3),
        "auto_expanded_precision_at_3": round(statistics.mean(row["auto_expanded_precision_at_3"] for row in results), 4),
        "auto_expanded_precision_at_5": round(statistics.mean(row["auto_expanded_precision_at_5"] for row in results), 4),
        "auto_expanded_precision_at_10": round(statistics.mean(row["auto_expanded_precision_at_10"] for row in results), 4),
        "frozen_gold_precision_at_3": round(statistics.mean(row["frozen_gold_precision_at_3"] for row in results), 4),
        "frozen_gold_precision_at_5": round(statistics.mean(row["frozen_gold_precision_at_5"] for row in results), 4),
        "frozen_gold_precision_at_10": round(statistics.mean(row["frozen_gold_precision_at_10"] for row in results), 4),
    }
    _write_json(args.output_dir / "metric_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

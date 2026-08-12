"""Prompt-constrained LLM rerank experiment over frozen RAG candidates.

The reranker may only reorder the existing Top-10 retrieved chunk IDs. It is
test-only and scores against the separately stored AI-auto-expanded evidence
labels; it never changes retrieval, corpus data, or the original frozen Gold.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
from threading import Lock, local
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.model_gateway import DeterministicModelProvider, create_model_gateway  # noqa: E402
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage  # noqa: E402
from app.core.config import settings  # noqa: E402


FIXTURE_ROOT = PROJECT_ROOT / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
RETRIEVAL_RESULTS = PROJECT_ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/retrieval_results.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/llm-rerank"
PROMPT_VERSION = "rag-llm-rerank-v1"


class RerankOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ranked_chunk_ids: list[str] = Field(min_length=1, max_length=10)

    @field_validator("ranked_chunk_ids")
    @classmethod
    def unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("ranked_chunk_ids must be unique")
        return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=False)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fallback(_: ModelCallRequest) -> dict[str, Any]:
    return {"ranked_chunk_ids": ["fallback"]}


def _rerank_prompt(query: dict[str, Any], candidate_ids: list[str], chunks: dict[str, dict[str, Any]]) -> tuple[str, str]:
    candidates = "\n\n".join(
        f"chunk_id={chunk_id} | chunk_index={chunks[chunk_id]['chunk_index']} | section={chunks[chunk_id].get('section_path', '')}\n"
        f"{chunks[chunk_id]['content'][:460]}"
        for chunk_id in candidate_ids
    )
    system = (
        "你是互联网医院 RAG 的候选重排器，不回答用户医疗问题。"
        "只能重排给定候选，不能新增、删除或改写 chunk_id。优先把直接支持当前问题的规则定义、"
        "适用条件、执行步骤和例外条款排前；同一事实的重复片段、仅有主题相似性、标题或背景说明排后。"
        "对于规则编号、药品名等显式实体，必须优先其精确匹配证据。"
        "只输出 JSON：{\"ranked_chunk_ids\":[\"候选id1\",...]}，必须包含所有给定 id 且不重复。"
    )
    user = f"用户问题：{query['user_input']}\n\n候选：\n{candidates}"
    return system, user


def _precision(ranked: list[str], relevant: set[str], top_k: int) -> float:
    return len(set(ranked[:top_k]).intersection(relevant)) / top_k


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if args.concurrency < 1 or args.concurrency > 16:
        raise ValueError("concurrency must be in 1..16")
    if args.max_cases is not None and args.max_cases < 1:
        raise ValueError("max-cases must be positive")

    chunks = {row["chunk_id"]: row for row in _read_jsonl(FIXTURE_ROOT / "corpus/knowledge_chunks.jsonl")}
    labels = {
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
        if row["base_case_id"] in labels and row["query_id"] in queries
    ]
    if args.max_cases is not None:
        selected_cases = set(sorted(labels)[: args.max_cases])
        rows = [row for row in rows if row["base_case_id"] in selected_cases]
    if not rows:
        raise RuntimeError("no applicable retrieval rows")

    worker = local()
    instances: list[Any] = []
    instances_lock = Lock()

    def gateway() -> Any:
        instance = getattr(worker, "gateway", None)
        if instance is None:
            instance = create_model_gateway(DeterministicModelProvider(_fallback, model_name="llm-rerank-fallback"), configuration=settings)
            worker.gateway = instance
            with instances_lock:
                instances.append(instance)
        return instance

    def run_one(row: dict[str, Any]) -> dict[str, Any]:
        query = queries[row["query_id"]]
        candidates = [chunk_id for chunk_id in row["retrieved_chunk_ids"] if chunk_id in chunks]
        system, user = _rerank_prompt(query, candidates, chunks)
        request = ModelCallRequest(
            run_id=f"{row['query_id']}-llm-rerank",
            task_id=row["base_case_id"],
            member_id=query["protected_slots"]["member_id"],
            purpose="synthetic_rag_llm_rerank",
            messages=(ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)),
            temperature=0.0,
            max_output_tokens=300,
        )
        result = gateway().invoke(request, RerankOutput)
        proposed = list(result.output.ranked_chunk_ids) if result.output is not None else []
        # Reject malformed permutations instead of silently accepting a model
        # that omitted or invented candidates.
        valid = set(proposed) == set(candidates) and len(proposed) == len(candidates)
        ranked = proposed if valid else candidates
        relevant = labels[row["base_case_id"]]
        return {
            "query_id": row["query_id"],
            "base_case_id": row["base_case_id"],
            "split": row["split"],
            "original_chunk_ids": candidates,
            "reranked_chunk_ids": ranked,
            "auto_expanded_relevant_chunk_ids": sorted(relevant),
            "valid_permutation": valid,
            "provider": result.trace.effective_provider,
            "fallback_used": result.trace.fallback_used,
            "success": result.trace.success,
            "precision_at_3": round(_precision(ranked, relevant, 3), 4),
            "precision_at_5": round(_precision(ranked, relevant, 5), 4),
            "precision_at_10": round(_precision(ranked, relevant, 10), 4),
        }

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(run_one, rows))
    results.sort(key=lambda row: row["query_id"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "llm_rerank_results.jsonl", results)
    summary = {
        "prompt_version": PROMPT_VERSION,
        "label_provenance": "ai_auto_generated_no_human_review",
        "metric_note": "Prompt-only LLM rerank over frozen Top-10 candidates; auto-expanded evidence diagnostic only, not an independent Gold evaluation.",
        "query_count": len(results),
        "base_case_count": len({row["base_case_id"] for row in results}),
        "valid_permutation_rate": round(sum(row["valid_permutation"] for row in results) / len(results), 4),
        "fallback_rate": round(sum(row["fallback_used"] for row in results) / len(results), 4),
        "precision_at_3": round(statistics.mean(row["precision_at_3"] for row in results), 4),
        "precision_at_5": round(statistics.mean(row["precision_at_5"] for row in results), 4),
        "precision_at_10": round(statistics.mean(row["precision_at_10"] for row in results), 4),
    }
    _write_json(args.output_dir / "metric_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for instance in instances:
        instance.close()


if __name__ == "__main__":
    main()

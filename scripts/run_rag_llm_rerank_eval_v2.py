"""Prompt-constrained real-LLM rerank over frozen RAG Top-10 candidates.

This diagnostic never retrieves extra chunks, changes corpus data, or updates
frozen/automatic labels.  A malformed model permutation falls back to the
original ranking and is recorded explicitly.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.model_gateway import DeterministicModelProvider, create_model_gateway  # noqa: E402
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage  # noqa: E402
from app.core.config import settings  # noqa: E402

FIXTURE = ROOT / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
RETRIEVAL = ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/retrieval_results.jsonl"
DEFAULT_OUT = ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/llm-rerank-v2"
PROMPT_VERSION = "rag-llm-rerank-v2-zh-business-constraints"


class RerankOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ranked_chunk_ids: list[str] = Field(min_length=1, max_length=10)

    @field_validator("ranked_chunk_ids")
    @classmethod
    def validate_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("ranked_chunk_ids must be unique")
        return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def precision(ids: list[str], relevant: set[str], top_k: int) -> float:
    return len(set(ids[:top_k]).intersection(relevant)) / top_k


def build_prompt(query: str, ids: list[str], chunks: dict[str, dict[str, Any]]) -> tuple[str, str]:
    candidate_text = "\n\n".join(
        f"chunk_id={chunk_id} | chunk_index={chunks[chunk_id]['chunk_index']} | "
        f"section={chunks[chunk_id].get('section_path', '')}\n{chunks[chunk_id]['content'][:460]}"
        for chunk_id in ids
    )
    system = """你是互联网医院 RAG 的候选重排器，不回答用户医疗问题。
只能重排给定候选，绝不能新增、删除、改写 chunk_id，也不能输出解释。
排序优先级：
1. 当前生效规则的主定义、明确适用条件、执行步骤、例外条款；
2. 药品名、规则编号、剂型、规格、频次等精确实体匹配；
3. 能直接回答问题的规则主片段，优先于目录、背景、重复描述或仅主题相近的补充片段；
4. 同一文档内，更完整的主规则片段优先；只有问题明确需要时才提前条件、步骤、例外等互补片段。
只输出一个 JSON 对象：{"ranked_chunk_ids":["候选id1","候选id2",...]}。
数组必须恰好包含全部给定 id 一次，长度不变。"""
    return system, f"用户问题：{query}\n\n候选：\n{candidate_text}"


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row[key] is not None]
    return round(statistics.mean(values), 3) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.case_start < 0 or args.concurrency not in range(1, 17):
        raise ValueError("case-start must be non-negative and concurrency must be in 1..16")
    if args.max_cases is not None and args.max_cases < 1:
        raise ValueError("max-cases must be positive")
    if settings.model_provider != "openai_compatible":
        raise RuntimeError("real LLM rerank requires MODEL_PROVIDER=openai_compatible")

    chunks = {row["chunk_id"]: row for row in read_jsonl(FIXTURE / "corpus/knowledge_chunks.jsonl")}
    automatic = {row["base_case_id"]: set(row["selected_chunk_ids"]) for row in read_jsonl(FIXTURE / "labels/auto_expanded_evidence.jsonl") if row["status"] == "generated"}
    queries = {row["query_id"]: row for split in ("development", "validation", "holdout") for row in read_jsonl(FIXTURE / f"dataset/{split}.jsonl")}
    cases = sorted(automatic)
    if args.max_cases is not None:
        cases = cases[args.case_start : args.case_start + args.max_cases]
    else:
        cases = cases[args.case_start:]
    selected = set(cases)
    rows = [row for row in read_jsonl(RETRIEVAL) if row["base_case_id"] in selected and row["query_id"] in queries]
    if not rows:
        raise RuntimeError("no applicable retrieval rows")

    thread_state = local()
    gateways: list[Any] = []
    gateway_lock = Lock()

    def fallback(_: ModelCallRequest) -> dict[str, Any]:
        return {"ranked_chunk_ids": ["invalid-fallback"]}

    def get_gateway() -> Any:
        instance = getattr(thread_state, "gateway", None)
        if instance is None:
            instance = create_model_gateway(DeterministicModelProvider(fallback, model_name="rerank-fallback"), configuration=settings)
            thread_state.gateway = instance
            with gateway_lock:
                gateways.append(instance)
        return instance

    def score(row: dict[str, Any]) -> dict[str, Any]:
        query = queries[row["query_id"]]
        original = [chunk_id for chunk_id in row["retrieved_chunk_ids"] if chunk_id in chunks]
        system, user = build_prompt(query["user_input"], original, chunks)
        result = get_gateway().invoke(
            ModelCallRequest(
                run_id=f"{row['query_id']}-llm-rerank-v2",
                task_id=row["base_case_id"],
                member_id=query["protected_slots"]["member_id"],
                purpose="synthetic_rag_llm_rerank",
                messages=(ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)),
                temperature=0.0,
                max_output_tokens=160,
            ),
            RerankOutput,
        )
        proposed = list(result.output.ranked_chunk_ids) if result.output else []
        valid = len(proposed) == len(original) and set(proposed) == set(original)
        ranked = proposed if valid else original
        auto = automatic[row["base_case_id"]]
        frozen = set(query["retrieval_gold"]["relevant_chunk_ids"])
        payload = {
            "query_id": row["query_id"], "base_case_id": row["base_case_id"], "split": row["split"],
            "original_chunk_ids": original, "reranked_chunk_ids": ranked, "valid_permutation": valid,
            "provider": result.trace.effective_provider, "success": result.trace.success,
            "fallback_used": result.trace.fallback_used, "latency_ms": result.trace.latency_ms,
            "input_tokens": result.trace.input_tokens, "output_tokens": result.trace.output_tokens,
            "total_tokens": result.trace.total_tokens,
        }
        for prefix, labels in (("auto_expanded", auto), ("frozen_gold", frozen)):
            payload[f"{prefix}_relevant_chunk_ids"] = sorted(labels)
            for top_k in (3, 5, 10):
                payload[f"{prefix}_precision_at_{top_k}"] = round(precision(ranked, labels, top_k), 4)
        return payload

    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            results = list(executor.map(score, rows))
    finally:
        for gateway in gateways:
            gateway.close()
    results.sort(key=lambda row: row["query_id"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "llm_rerank_results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in results), encoding="utf-8")
    summary: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION, "model": settings.model_name,
        "metric_note": "Real LLM only reorders frozen Top-10 candidates. Automatic-label metrics are diagnostic and frozen Gold is unchanged.",
        "query_count": len(results), "base_case_count": len(selected),
        "valid_permutation_rate": round(sum(row["valid_permutation"] for row in results) / len(results), 4),
        "provider_success_rate": round(sum(row["success"] for row in results) / len(results), 4),
        "fallback_rate": round(sum(row["fallback_used"] for row in results) / len(results), 4),
        "average_latency_ms": mean(results, "latency_ms"), "average_input_tokens": mean(results, "input_tokens"),
        "average_output_tokens": mean(results, "output_tokens"), "average_total_tokens": mean(results, "total_tokens"),
    }
    for prefix in ("auto_expanded", "frozen_gold"):
        for top_k in (3, 5, 10):
            summary[f"{prefix}_precision_at_{top_k}"] = round(statistics.mean(row[f"{prefix}_precision_at_{top_k}"] for row in results), 4)
    (args.output_dir / "metric_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

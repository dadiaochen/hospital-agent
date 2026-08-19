"""Measure constrained real-LLM query expansion before frozen hybrid retrieval.

The expander may only normalize and restate the user's query.  It cannot see
the corpus, add documents, alter labels, or answer a medical question.  The
retriever remains BM25 + pgvector HNSW + RRF with the retained M5 profile.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
from threading import Lock, local
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "backend", ROOT / "scripts"):
    sys.path.insert(0, str(item))

from app.agent.model_gateway import DeterministicModelProvider, create_model_gateway  # noqa: E402
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.rag.retrieval_schemas import RetrievalRequest  # noqa: E402
from app.rag.retriever import Bm25CorpusIndex, HybridRetriever, KeywordRetriever, SQLAlchemyKnowledgeStore  # noqa: E402
from app.rag.vector_store import PgVectorSearchBackend  # noqa: E402
from run_synthetic_rag_full_eval import (  # noqa: E402
    DEFAULT_DATABASE_URL,
    FrozenKnowledgeSnapshot,
    LockedEmbeddingProvider,
    _retrieval_row,
    load_frozen_bundle,
    prepare_postgres_knowledge_base,
    resolve_retrieval_profile,
)


FIXTURE = ROOT / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
CONTROL = ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/retrieval_results.jsonl"
DEFAULT_OUT = ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/query-expansion-v1"
PROMPT_VERSION = "rag-query-expansion-v1-zh-constrained"


class QueryExpansion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_query: str = Field(min_length=1, max_length=500)
    retrieval_terms: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("retrieval_terms")
    @classmethod
    def unique_terms(cls, terms: list[str]) -> list[str]:
        return list(dict.fromkeys(term.strip() for term in terms if term.strip()))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row[key] is not None]
    return round(statistics.mean(values), 3) if values else None


def expansion_prompt(user_query: str) -> tuple[str, str]:
    system = """你是 RAG 检索前的查询规范化器，不回答医疗问题，也不提供医疗建议。
只从用户原问句中提取或改写已经出现的信息：规则编号、药品名、剂型、规格、频次、检查指标、动作、时间和条件。
不得猜测同义药品、疾病、规则内容或不存在的实体；不得删除原问句中任何限制。
只输出 JSON：{"normalized_query":"保留全部限制的规范化问句","retrieval_terms":["原问句已出现的精确术语", ...]}。
retrieval_terms 最多 12 个，若没有可提取术语则为空数组。"""
    return system, f"用户原问句：{user_query}"


def build_retrieval_query(original: str, output: QueryExpansion | None) -> str:
    if output is None:
        return original
    terms = " ".join(output.retrieval_terms[:12])
    normalized = output.normalized_query.strip()
    # Keep the user text verbatim so normalization cannot silently discard a
    # condition; terms only give BM25/vector an additional lexical view.
    return f"{original}\n规范化表达：{normalized}\n精确检索词：{terms}"[:1400]


def metric(rows: list[dict[str, Any]], prefix: str) -> dict[str, float | None]:
    return {
        f"{prefix}_recall_at_{top_k}": round(statistics.mean(row[f"recall_at_{top_k}"] for row in rows), 4) if rows else None
        for top_k in (3, 5, 10)
    } | {
        f"{prefix}_precision_at_{top_k}": round(statistics.mean(row[f"precision_at_{top_k}"] for row in rows), 4) if rows else None
        for top_k in (3, 5, 10)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-start", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=15)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.case_start < 0 or args.max_cases < 1 or args.concurrency not in range(1, 17):
        raise ValueError("invalid case range or concurrency")
    if settings.model_provider != "openai_compatible":
        raise RuntimeError("query expansion needs MODEL_PROVIDER=openai_compatible")

    corpus, dataset = load_frozen_bundle(FIXTURE)
    profile = resolve_retrieval_profile("m5-hybrid-rerank", corpus)
    selected_cases = set(sorted({query["base_case_id"] for query in dataset.queries})[args.case_start : args.case_start + args.max_cases])
    selected = [query for query in dataset.queries if query["base_case_id"] in selected_cases and query["expected_flow"]["should_call_rag"]]
    if not selected:
        raise RuntimeError("no RAG queries selected")
    prepared = prepare_postgres_knowledge_base(corpus, args.database_url, reuse_index=True)
    embedding = LockedEmbeddingProvider(prepared.provider)
    with Session(prepared.engine) as session:
        store = SQLAlchemyKnowledgeStore(session, allowed_document_ids=profile.allowed_document_ids, snapshot_cache_enabled=True)
        snapshot = FrozenKnowledgeSnapshot(store.list_records())
    bm25 = Bm25CorpusIndex.build(snapshot.list_records())
    controls = {row["query_id"]: row for row in read_jsonl(CONTROL)}
    automatic_labels = {
        row["base_case_id"]: set(row["selected_chunk_ids"])
        for row in read_jsonl(FIXTURE / "labels/auto_expanded_evidence.jsonl")
        if row["status"] == "generated"
    }
    thread = local()
    gateways: list[Any] = []
    gateway_lock = Lock()

    def fallback(_: ModelCallRequest) -> dict[str, Any]:
        return {"normalized_query": "fallback", "retrieval_terms": []}

    def gateway() -> Any:
        current = getattr(thread, "gateway", None)
        if current is None:
            current = create_model_gateway(DeterministicModelProvider(fallback, model_name="query-expansion-fallback"), configuration=settings)
            thread.gateway = current
            with gateway_lock:
                gateways.append(current)
        return current

    def run_one(query: dict[str, Any]) -> dict[str, Any]:
        system, user = expansion_prompt(query["user_input"])
        started = time.perf_counter()
        expanded = gateway().invoke(
            ModelCallRequest(
                run_id=f"{query['query_id']}-query-expansion",
                task_id=query["base_case_id"],
                member_id=query["protected_slots"]["member_id"],
                purpose="synthetic_rag_query_expansion",
                messages=(ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)),
                temperature=0.0,
                max_output_tokens=180,
            ),
            QueryExpansion,
        )
        expansion_ms = (time.perf_counter() - started) * 1000
        # A provider failure must not inject the deterministic fallback text
        # into the retrieval query.  It is an explicit control-path result:
        # use the original user input verbatim and retain the failed trace.
        usable_expansion = (
            expanded.output
            if expanded.trace.success and not expanded.trace.fallback_used
            else None
        )
        retrieval_query = build_retrieval_query(query["user_input"], usable_expansion)
        retrieval_started = time.perf_counter()
        with Session(prepared.engine) as session:
            vector = PgVectorSearchBackend(session, embedding, min_score=settings.rag_vector_min_score, allowed_document_ids=profile.allowed_document_ids)
            retriever = HybridRetriever(
                KeywordRetriever(snapshot, scoring_strategy=profile.keyword_scoring_strategy, bm25_index=bm25),
                snapshot,
                vector_enabled=True,
                vector_backend=vector,
                candidate_limit=profile.candidate_limit,
                rerank_enabled=profile.rerank_enabled,
                dedupe_enabled=profile.dedupe_enabled,
                relevance_filter_enabled=profile.relevance_filter_enabled,
                document_head_enabled=profile.document_head_enabled,
            )
            result = retriever.retrieve(RetrievalRequest(query=retrieval_query, purpose="synthetic_rag_query_expansion", mode="hybrid", limit=10))
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        row = _retrieval_row(query, result, retrieval_ms)
        row.update({
            "original_user_query": query["user_input"],
            "expanded_query": retrieval_query,
            "expansion_output": usable_expansion.model_dump(mode="json") if usable_expansion else None,
            "expansion_success": expanded.trace.success,
            "expansion_fallback_used": expanded.trace.fallback_used,
            "expansion_latency_ms": round(expansion_ms, 3),
            "expansion_input_tokens": expanded.trace.input_tokens,
            "expansion_output_tokens": expanded.trace.output_tokens,
            "expansion_total_tokens": expanded.trace.total_tokens,
            "expansion_trace": expanded.trace.model_dump(mode="json"),
        })
        auto = automatic_labels.get(query["base_case_id"], set())
        for top_k in (3, 5, 10):
            row[f"auto_expanded_precision_at_{top_k}"] = round(len(set(row["retrieved_chunk_ids"][:top_k]).intersection(auto)) / top_k, 4) if auto else None
        return row

    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            rows = list(pool.map(run_one, selected))
    finally:
        for item in gateways:
            item.close()
        prepared.engine.dispose()
    rows.sort(key=lambda row: row["query_id"])
    control_rows = [controls[row["query_id"]] for row in rows if row["query_id"] in controls]
    summary: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "model": settings.model_name,
        "metric_note": "LLM query normalization precedes the retained hybrid retriever. It has no corpus access and does not change frozen Gold; automatic Precision is diagnostic only.",
        "query_count": len(rows), "base_case_count": len(selected_cases),
        "expansion_success_rate": round(sum(row["expansion_success"] for row in rows) / len(rows), 4),
        "expansion_fallback_rate": round(sum(row["expansion_fallback_used"] for row in rows) / len(rows), 4),
        "average_expansion_latency_ms": mean(rows, "expansion_latency_ms"),
        "average_expansion_input_tokens": mean(rows, "expansion_input_tokens"),
        "average_expansion_output_tokens": mean(rows, "expansion_output_tokens"),
        "average_expansion_total_tokens": mean(rows, "expansion_total_tokens"),
        "average_retrieval_latency_ms": mean(rows, "latency_ms"),
        "control": metric(control_rows, "frozen_gold"),
        "expanded": metric(rows, "frozen_gold"),
    }
    summary["control"].update({f"auto_expanded_precision_at_{k}": round(statistics.mean(len(set(row["retrieved_chunk_ids"][:k]).intersection(automatic_labels.get(row["base_case_id"], set()))) / k for row in control_rows), 4) for k in (3, 5, 10)})
    summary["expanded"].update({f"auto_expanded_precision_at_{k}": round(statistics.mean(row[f"auto_expanded_precision_at_{k}"] for row in rows if row[f"auto_expanded_precision_at_{k}"] is not None), 4) for k in (3, 5, 10)})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "query_expansion_results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    (args.output_dir / "metric_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

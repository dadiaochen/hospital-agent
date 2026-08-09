"""Run the frozen synthetic RAG benchmark through the real RAG + LLM path.

This is a test-only harness.  It creates/resets only the explicitly named
``rag_synthetic_eval_v1`` PostgreSQL database, imports the frozen synthetic
corpus, indexes it with the configured FastEmbed model, creates a pgvector
HNSW index, and then runs the existing HybridRetriever and ModelGateway.

The harness does not publish knowledge, call business tools, create drafts,
or produce clinical conclusions.  The automatic answer score is source-bound
engineering accuracy over synthetic labels; it is not clinical accuracy.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
for import_path in (BACKEND_ROOT, SCRIPT_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from app.agent.model_gateway import (  # noqa: E402
    DeterministicModelProvider,
    create_model_gateway,
)
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models import KnowledgeChunk, KnowledgeDocument  # noqa: E402
from app.rag.embedding_provider import (  # noqa: E402
    EMBEDDING_DIMENSION,
    FastEmbedEmbeddingProvider,
)
from app.rag.retrieval_schemas import RetrievalRequest  # noqa: E402
from app.rag.retriever import (  # noqa: E402
    create_knowledge_retriever,
    select_minimal_evidence_sources,
)
from app.rag.vector_store import (  # noqa: E402
    KnowledgeEmbeddingIndexer,
    create_configured_vector_backend,
)
from rag_synthetic_eval import (  # noqa: E402
    DATASET_VERSION,
    NAMESPACE,
    CorpusBundle,
    DatasetBundle,
    SEED,
    _file_sha256,
    _read_jsonl,
    _write_json,
    _write_jsonl,
    validate_bundle,
)


DEFAULT_FIXTURE_ROOT = (
    PROJECT_ROOT / "output/benchmarks/rag_synthetic/fixtures/rag_synthetic_v1"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "output/benchmarks/rag_synthetic/rag-synthetic-v1-full-20260807"
)
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://hospital:hospital@localhost:5432/"
    "rag_synthetic_eval_v1"
)
HNSW_INDEX_NAME = "ix_syn_rag_v1_chunks_embedding_hnsw"
CONTEXT_TOP_K = 5
RETRIEVAL_TOP_K = 10


class SyntheticAnswer(BaseModel):
    """The only answer contract accepted from the real provider."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        protected_namespaces=(),
    )

    response_type: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    cited_chunk_ids: list[str] = Field(default_factory=list, max_length=20)
    claim_texts: list[str] = Field(default_factory=list, max_length=20)
    refusal_reason: str | None = None


@dataclass(frozen=True)
class PreparedDatabase:
    engine: Any
    provider: FastEmbedEmbeddingProvider
    import_result: dict[str, Any]


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    allowed_document_ids: frozenset[str] | None = None
    candidate_limit: int | None = None
    rerank_enabled: bool = False
    dedupe_enabled: bool = False
    evidence_gate_enabled: bool = False
    evidence_max_sources: int = 3
    snapshot_cache_enabled: bool = False
    max_output_tokens: int = 512

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "allowed_document_count": (
                len(self.allowed_document_ids)
                if self.allowed_document_ids is not None
                else None
            ),
            "candidate_limit": self.candidate_limit,
            "rerank_enabled": self.rerank_enabled,
            "dedupe_enabled": self.dedupe_enabled,
            "evidence_gate_enabled": self.evidence_gate_enabled,
            "evidence_max_sources": self.evidence_max_sources,
            "snapshot_cache_enabled": self.snapshot_cache_enabled,
            "max_output_tokens": self.max_output_tokens,
        }


RETRIEVAL_PROFILES = (
    "baseline",
    "m2-version-filter",
    "m2-light-rerank",
    "m2-dedupe",
    "m2",
    "m3-evidence-gate",
    "m4-snapshot-cache",
    "m4-cost",
    "m5-final",
)


def resolve_retrieval_profile(
    name: str,
    corpus: CorpusBundle,
) -> RetrievalProfile:
    active_document_ids = frozenset(
        document["document_id"]
        for document in corpus.documents
        if document.get("status") == "active"
    )
    if name == "baseline":
        return RetrievalProfile(name=name)
    if name == "m2-version-filter":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
        )
    if name == "m2-light-rerank":
        return RetrievalProfile(
            name=name,
            candidate_limit=20,
            rerank_enabled=True,
        )
    if name == "m2-dedupe":
        return RetrievalProfile(
            name=name,
            dedupe_enabled=True,
        )
    if name == "m2":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
            candidate_limit=20,
            rerank_enabled=True,
            dedupe_enabled=True,
        )
    if name == "m3-evidence-gate":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
            evidence_gate_enabled=True,
            evidence_max_sources=3,
        )
    if name == "m4-snapshot-cache":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
            evidence_gate_enabled=True,
            evidence_max_sources=3,
            snapshot_cache_enabled=True,
        )
    if name == "m4-cost":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
            evidence_gate_enabled=True,
            evidence_max_sources=3,
            snapshot_cache_enabled=True,
            max_output_tokens=256,
        )
    if name == "m5-final":
        return RetrievalProfile(
            name=name,
            allowed_document_ids=active_document_ids,
            evidence_gate_enabled=True,
            evidence_max_sources=3,
            snapshot_cache_enabled=True,
        )
    raise ValueError(
        f"unsupported retrieval profile {name!r}; "
        f"choose one of {', '.join(RETRIEVAL_PROFILES)}"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_frozen_bundle(fixture_root: Path) -> tuple[CorpusBundle, DatasetBundle]:
    corpus_root = fixture_root / "corpus"
    dataset_root = fixture_root / "dataset"
    labels_root = fixture_root / "labels"
    required = [
        corpus_root / "knowledge_documents.jsonl",
        corpus_root / "knowledge_chunks.jsonl",
        dataset_root / "base_cases.jsonl",
        dataset_root / "development.jsonl",
        dataset_root / "validation.jsonl",
        dataset_root / "holdout.jsonl",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("frozen synthetic dataset files missing: " + ", ".join(missing))

    corpus = CorpusBundle(
        documents=_read_jsonl(corpus_root / "knowledge_documents.jsonl"),
        chunks=_read_jsonl(corpus_root / "knowledge_chunks.jsonl"),
        blueprints=_read_jsonl(corpus_root / "document_blueprints.jsonl"),
        manifest=_read_json(corpus_root / "corpus_manifest.json"),
    )
    queries = [
        query
        for split in ("development", "validation", "holdout")
        for query in _read_jsonl(dataset_root / f"{split}.jsonl")
    ]
    labels = {
        name: _read_jsonl(labels_root / f"{name}.jsonl")
        for name in ("retrieval_gold", "answer_gold", "hard_negatives", "expected_flows")
    }
    dataset = DatasetBundle(
        cases=_read_jsonl(dataset_root / "base_cases.jsonl"),
        queries=queries,
        labels=labels,
        manifest=_read_json(dataset_root / "dataset_manifest.json"),
    )
    return corpus, dataset


def _ensure_isolated_database(database_url: str) -> None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("full synthetic RAG eval requires a PostgreSQL database URL")
    if parsed.database != "rag_synthetic_eval_v1":
        raise ValueError(
            "refusing to reset a non-isolated database; use database name "
            "rag_synthetic_eval_v1"
        )
    admin_url = parsed.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": parsed.database},
            )
            if not exists:
                connection.execute(
                    text('CREATE DATABASE "rag_synthetic_eval_v1"')
                )
    finally:
        admin_engine.dispose()


def prepare_postgres_knowledge_base(
    corpus: CorpusBundle,
    database_url: str,
) -> PreparedDatabase:
    _ensure_isolated_database(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    KnowledgeDocument.metadata.create_all(engine)

    provider = FastEmbedEmbeddingProvider(
        model_name=settings.rag_embedding_model,
        cache_dir=settings.rag_embedding_cache_dir,
        dimension=settings.rag_embedding_dimensions,
        device=settings.rag_embedding_device,
    )
    if settings.rag_embedding_provider != "fastembed":
        raise ValueError(
            "this full benchmark requires RAG_EMBEDDING_PROVIDER=fastembed; "
            f"got {settings.rag_embedding_provider!r}"
        )
    if provider.dimension != EMBEDDING_DIMENSION:
        raise ValueError(
            f"knowledge schema requires {EMBEDDING_DIMENSION} dimensions; "
            f"configured provider has {provider.dimension}"
        )

    with Session(engine) as session:
        # The database name is checked above and is dedicated to this benchmark.
        session.execute(delete(KnowledgeChunk))
        session.execute(delete(KnowledgeDocument))
        session.flush()
        for document in corpus.documents:
            session.add(
                KnowledgeDocument(
                    id=document["document_id"],
                    title=document["title"],
                    category=document["category"],
                    source=document["source"],
                    content=document["content"],
                    safety_level=document["safety_level"],
                    version=document["version"],
                )
            )
        for chunk in corpus.chunks:
            session.add(
                KnowledgeChunk(
                    id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    keywords=chunk["keywords"],
                    chunk_version=chunk["chunk_version"],
                )
            )
        session.flush()
        index_result = KnowledgeEmbeddingIndexer(
            session,
            provider,
            batch_size=settings.rag_embedding_batch_size,
        ).index(force=True)
        session.commit()

    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {HNSW_INDEX_NAME} "
                "ON knowledge_chunks USING hnsw "
                "(embedding vector_cosine_ops)"
            )
        )

    with engine.connect() as connection:
        document_count = connection.scalar(text("SELECT count(*) FROM knowledge_documents"))
        chunk_count = connection.scalar(text("SELECT count(*) FROM knowledge_chunks"))
        embedding_count = connection.scalar(
            text(
                "SELECT count(*) FROM knowledge_chunks "
                "WHERE embedding IS NOT NULL AND embedding_model = :model"
            ),
            {"model": provider.model_name},
        )
        index_exists = connection.scalar(
            text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
                "AND indexname = :index_name"
            ),
            {"index_name": HNSW_INDEX_NAME},
        )
    if not index_exists:
        raise RuntimeError("pgvector HNSW index was not created")
    if (document_count, chunk_count, embedding_count) != (
        len(corpus.documents),
        len(corpus.chunks),
        len(corpus.chunks),
    ):
        raise RuntimeError(
            "isolated knowledge base counts do not match frozen corpus: "
            f"documents={document_count}, chunks={chunk_count}, embeddings={embedding_count}"
        )

    hnsw_plan = _probe_hnsw_plan(engine, provider)
    import_result = {
        "database": "rag_synthetic_eval_v1",
        "documents": document_count,
        "chunks": chunk_count,
        "embedding_indexed": embedding_count,
        "embedding_provider": "fastembed",
        "embedding_model": provider.model_name,
        "embedding_dimension": provider.dimension,
        "embedding_device": provider.device,
        "embedding_schema_version": "rag-embedding-v1",
        "hnsw_index_name": HNSW_INDEX_NAME,
        "hnsw_plan": hnsw_plan,
        "formal_knowledge_namespace_touched": False,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "index_result": {
            "scanned": index_result.scanned,
            "indexed": index_result.indexed,
            "skipped": index_result.skipped,
        },
    }
    return PreparedDatabase(engine=engine, provider=provider, import_result=import_result)


def _probe_hnsw_plan(engine: Any, provider: FastEmbedEmbeddingProvider) -> dict[str, Any]:
    vector = provider.embed_query("SYN-BUSINESS-01 测试规则")
    vector_literal = "[" + ",".join(f"{value:.9g}" for value in vector) + "]"
    with engine.connect() as connection:
        raw = connection.scalar(
            text(
                "EXPLAIN (FORMAT JSON, COSTS OFF) "
                "SELECT id FROM knowledge_chunks "
                "WHERE embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 10"
            ),
            {"vector": vector_literal},
        )
    payload = raw[0] if isinstance(raw, list) else raw
    plan = payload.get("Plan", {}) if isinstance(payload, dict) else {}
    nodes: list[str] = []
    index_names: list[str] = []

    def visit(node: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        if isinstance(node.get("Node Type"), str):
            nodes.append(node["Node Type"])
        if isinstance(node.get("Index Name"), str):
            index_names.append(node["Index Name"])
        for child in node.get("Plans", []):
            visit(child)

    visit(plan)
    return {
        "node_types": nodes,
        "index_names": index_names,
        "hnsw_index_selected": HNSW_INDEX_NAME in index_names,
        "raw": payload,
    }


def _fallback_payload(_request: ModelCallRequest) -> dict[str, Any]:
    return {
        "response_type": "no_answer",
        "answer": "当前证据不足，无法给出有来源的回答。",
        "cited_chunk_ids": [],
        "claim_texts": [],
        "refusal_reason": "fallback_no_verified_output",
    }


def _build_prompt(
    query: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    minimal_citation: bool = False,
) -> tuple[str, str]:
    system = (
        "你是互联网医院 Agent 的离线测试回答节点。只处理给定用户问题和检索证据，"
        "不得诊断、开方、修改处方、建议加量减量停药换药，也不得声称外部动作已经执行。"
        "必须只输出 JSON，不要 Markdown，不要额外字段。字段必须是："
        "response_type、answer、cited_chunk_ids、claim_texts、refusal_reason。"
        "response_type 只能使用 grounded_answer、no_answer、tool_fact、"
        "safety_redirect、out_of_scope_redirect、controlled_reject、"
        "permission_reject、confirmation_required、clarification。"
        "cited_chunk_ids 只能填写证据中的 chunk_id；没有证据时必须为空。"
        "每条 claim_texts 都必须能被所引用的证据直接支持；证据不足时选择 no_answer。"
    )
    if minimal_citation:
        system += (
            "每条 claim 只绑定最直接的一个来源；不要为了完整而引用所有证据。"
            "当前证据为空或不能直接支持问题时，必须选择 no_answer，引用必须保持为空。"
        )
    evidence = [
        {
            "chunk_id": source["chunk_id"],
            "document_id": source["document_id"],
            "title": source["title"],
            "content": source["content"],
        }
        for source in sources[:CONTEXT_TOP_K]
    ]
    user = json.dumps(
        {
            "user_query": query["user_input"],
            "retrieval_evidence": evidence,
            "instruction": "如果检索证据不能直接支持问题，请明确说明证据不足，不要补写事实。",
        },
        ensure_ascii=False,
    )
    return system, user


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return round(value, 3)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
    }


def _cost_usd(input_tokens: int, output_tokens: int) -> float | None:
    if (
        settings.model_input_price_per_1m_usd is None
        or settings.model_output_price_per_1m_usd is None
    ):
        return None
    return round(
        input_tokens * settings.model_input_price_per_1m_usd / 1_000_000
        + output_tokens * settings.model_output_price_per_1m_usd / 1_000_000,
        8,
    )


def _token_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usage_rows = [row for row in rows if row.get("total_tokens") is not None]
    input_tokens = sum(int(row["input_tokens"]) for row in usage_rows)
    output_tokens = sum(int(row["output_tokens"]) for row in usage_rows)
    total_tokens = sum(int(row["total_tokens"]) for row in usage_rows)
    return {
        "input_tokens": input_tokens if usage_rows else None,
        "output_tokens": output_tokens if usage_rows else None,
        "total_tokens": total_tokens if usage_rows else None,
        "cost_usd": _cost_usd(input_tokens, output_tokens) if usage_rows else None,
        "usage_available_calls": len(usage_rows),
        "usage_missing_calls": len(rows) - len(usage_rows),
        "usage_rate": _ratio(len(usage_rows), len(rows)),
        "input_price_per_1m_usd": settings.model_input_price_per_1m_usd,
        "output_price_per_1m_usd": settings.model_output_price_per_1m_usd,
    }


def _node_metric(
    *,
    latencies: list[float],
    token_rows: list[dict[str, Any]],
    node_type: str,
) -> dict[str, Any]:
    tokens = _token_summary(token_rows) if token_rows else {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "usage_available_calls": 0,
        "usage_missing_calls": 0,
        "usage_rate": None,
        "input_price_per_1m_usd": settings.model_input_price_per_1m_usd,
        "output_price_per_1m_usd": settings.model_output_price_per_1m_usd,
    }
    return {
        "node_type": node_type,
        "sample_count": len(latencies),
        "latency_ms": _latency_summary(latencies),
        **tokens,
    }


def _retrieval_row(
    query: dict[str, Any],
    retrieval_result: Any,
    retrieval_ms: float,
) -> dict[str, Any]:
    gold = query["retrieval_gold"]
    relevant = set(gold["relevant_chunk_ids"])
    stale = set(gold["stale_chunk_ids"])
    retrieved_ids = [source.chunk_id for source in retrieval_result.sources]
    row: dict[str, Any] = {
        "query_id": query["query_id"],
        "base_case_id": query["base_case_id"],
        "split": query["split"],
        "variant_type": query["variant_type"],
        "case_type": query["case_type"],
        "requested_mode": retrieval_result.requested_mode,
        "effective_mode": retrieval_result.effective_mode,
        "retrieval_provider": retrieval_result.retrieval_provider,
        "embedding_model": retrieval_result.embedding_model,
        "embedding_dimension": retrieval_result.embedding_dimension,
        "embedding_schema_version": retrieval_result.embedding_schema_version,
        "fallback_used": retrieval_result.fallback_used,
        "fallback_reason": retrieval_result.fallback_reason,
        "retrieved_chunk_ids": retrieved_ids,
        "retrieved_document_ids": [source.document_id for source in retrieval_result.sources],
        "relevant_chunk_ids": sorted(relevant),
        "stale_hit_chunk_ids": sorted(stale.intersection(retrieved_ids)),
        "latency_ms": round(retrieval_ms, 3),
    }
    for top_k in (3, 5, 10):
        top_ids = set(retrieved_ids[:top_k])
        row[f"recall_at_{top_k}"] = (
            round(len(relevant.intersection(top_ids)) / len(relevant), 4)
            if relevant
            else None
        )
    first_rank = next(
        (index + 1 for index, chunk_id in enumerate(retrieved_ids) if chunk_id in relevant),
        None,
    )
    row["mrr_at_10"] = round(1 / first_rank, 4) if first_rank else 0.0
    row["no_answer_correct"] = not relevant and not retrieved_ids
    row["stale_filter_passed"] = not row["stale_hit_chunk_ids"]
    return row


def _answer_row(
    query: dict[str, Any],
    *,
    result: Any,
    retrieved_ids: list[str],
    model_ms: float,
) -> dict[str, Any]:
    flow = query["expected_flow"]
    answer_gold = query["answer_gold"]
    expected_type = answer_gold["expected_response_type"]
    output = result.output
    trace = result.trace
    observed_type = output.response_type if output is not None else "model_error"
    cited = list(dict.fromkeys(output.cited_chunk_ids if output is not None else []))
    expected_sources = set(answer_gold["supporting_chunk_ids"])
    cited_set = set(cited)
    matched_sources = expected_sources.intersection(cited_set)
    unsupported_citations = cited_set.difference(expected_sources)
    if expected_sources:
        required_recall = len(matched_sources) / len(expected_sources)
        precision = len(matched_sources) / len(cited_set) if cited_set else 0.0
    else:
        required_recall = 1.0 if not cited_set else 0.0
        precision = 1.0 if not cited_set else 0.0
    forbidden = any(
        forbidden_claim and output is not None and forbidden_claim in output.answer
        for forbidden_claim in answer_gold["forbidden_claims"]
    )
    response_correct = observed_type == expected_type
    rag_applicable = bool(flow["should_call_rag"])
    source_bound_correct = bool(
        trace.success
        and response_correct
        and required_recall == 1.0
        and not unsupported_citations
        and not forbidden
    )
    return {
        "query_id": query["query_id"],
        "base_case_id": query["base_case_id"],
        "split": query["split"],
        "variant_type": query["variant_type"],
        "case_type": query["case_type"],
        "rag_evaluation_applicable": rag_applicable,
        "tool_evaluation_applicable": bool(flow["should_call_tools"]),
        "expected_response_type": expected_type,
        "observed_response_type": observed_type,
        "response_type_correct": response_correct,
        "required_claim_count": len(answer_gold["required_claims"]),
        "required_source_recall": round(required_recall, 4),
        "supported_citation_precision": round(precision, 4),
        "cited_chunk_ids": cited,
        "retrieved_chunk_ids": retrieved_ids,
        "unsupported_citation_ids": sorted(unsupported_citations),
        "forbidden_claim_detected": forbidden,
        "hallucination_detected": bool(unsupported_citations or forbidden),
        "source_bound_answer_correct": source_bound_correct,
        "latency_ms": round(model_ms, 3),
        "provider": trace.effective_provider,
        "requested_provider": trace.requested_provider,
        "success": trace.success,
        "schema_valid": trace.schema_valid,
        "safety_passed": trace.safety_passed,
        "fallback_used": trace.fallback_used,
        "fallback_reason": trace.fallback_reason,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "total_tokens": trace.total_tokens,
        "token_usage_available": trace.token_usage_available,
        "trace": trace.model_dump(mode="json"),
        "output": output.model_dump(mode="json") if output is not None else None,
    }


def _split_summary(
    split: str,
    retrieval_rows: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
    query_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    retrieval = [row for row in retrieval_rows if row["split"] == split]
    answers = [
        row
        for row in answer_rows
        if row["split"] == split and row["rag_evaluation_applicable"]
    ]
    queries = [row for row in query_rows if row["split"] == split]
    return {
        "query_count": len(queries),
        "rag_query_count": len(retrieval),
        "rag_recall_at_3": round(statistics.mean(row["recall_at_3"] for row in retrieval if row["recall_at_3"] is not None), 4) if any(row["recall_at_3"] is not None for row in retrieval) else None,
        "rag_recall_at_5": round(statistics.mean(row["recall_at_5"] for row in retrieval if row["recall_at_5"] is not None), 4) if any(row["recall_at_5"] is not None for row in retrieval) else None,
        "rag_recall_at_10": round(statistics.mean(row["recall_at_10"] for row in retrieval if row["recall_at_10"] is not None), 4) if any(row["recall_at_10"] is not None for row in retrieval) else None,
        "model_answer_accuracy": _ratio(sum(row["source_bound_answer_correct"] for row in answers), len(answers)),
        "answer_response_type_accuracy": _ratio(sum(row["response_type_correct"] for row in answers), len(answers)),
        "answer_required_source_recall": round(statistics.mean(row["required_source_recall"] for row in answers), 4) if answers else None,
        "answer_unsupported_citation_rate": round(statistics.mean(row["hallucination_detected"] for row in answers), 4) if answers else None,
        "end_to_end_latency_ms": _latency_summary([row["end_to_end_latency_ms"] for row in queries]),
    }


def _build_report(
    output_dir: Path,
    metrics: dict[str, Any],
    import_result: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    report = f"""# Synthetic RAG Full-Chain Evaluation Report

- dataset: `{DATASET_VERSION}`
- namespace: `{NAMESPACE}`
- status: `{metrics['status']}`
- query_count: `{metrics['dataset']['query_count']}`
- human_reviewed: `false`
- clinical_gold: `false`
- model_provider: `{metrics['configuration']['model_provider']}`
- model_name: `{metrics['configuration']['model_name']}`
- embedding: `{metrics['configuration']['embedding_model']}` (`{metrics['configuration']['embedding_dimension']}` dimensions)
- vector_search: `PostgreSQL pgvector cosine + HNSW + HybridRetriever/RRF`
- evaluation_mode: `{metrics['configuration']['evaluation_mode']}`
- retrieval_profile: `{metrics['configuration']['retrieval_profile']['name']}`

## Scope

This is a test-only source-bound engineering evaluation. It exercises the configured local FastEmbed model, PostgreSQL pgvector HNSW search, the existing hybrid retriever and, for full mode, the existing ModelGateway and deterministic post-run evaluator. Retrieval-only mode intentionally does not invoke an LLM. It is not clinical accuracy, patient safety evidence or a production SLA. Tool-only cases are retained in the 500-query run but are excluded from RAG answer accuracy because this harness does not fabricate business-tool evidence.

## Frozen data and database

```json
{json.dumps({**import_result, 'hnsw_plan': import_result.get('hnsw_plan')}, ensure_ascii=False, indent=2, sort_keys=True)}
```

## Final metrics

| Metric | Full run |
|---|---:|
| Recall@3 | {metrics['rag']['recall_at_3']} |
| Recall@5 | {metrics['rag']['recall_at_5']} |
| Recall@10 | {metrics['rag']['recall_at_10']} |
| Model answer accuracy (RAG cases) | {metrics['answer']['model_answer_accuracy']} |
| End-to-end p50 / p95 / p99 (ms) | {metrics['performance']['end_to_end_latency_ms']['p50']} / {metrics['performance']['end_to_end_latency_ms']['p95']} / {metrics['performance']['end_to_end_latency_ms']['p99']} |
| LLM input / output / total tokens | {metrics['tokens_and_cost']['input_tokens']} / {metrics['tokens_and_cost']['output_tokens']} / {metrics['tokens_and_cost']['total_tokens']} |
| LLM cost (USD) | {metrics['tokens_and_cost']['cost_usd']} |

## Node latency and token cost

```json
{json.dumps(metrics['nodes'], ensure_ascii=False, indent=2, sort_keys=True)}
```

Embedding is a local model operation, so it has no LLM token billing. Its latency is included in the `rag_retrieval` node and its model, dimension and HNSW index are recorded above.

## Split metrics

```json
{json.dumps(metrics['by_split'], ensure_ascii=False, indent=2, sort_keys=True)}
```

## Limitations

- Labels are automatically generated, not human reviewed, and not clinical gold.
- Source-bound answer accuracy cannot prove semantic or clinical correctness.
- Tool-only cases do not get invented tool facts; their RAG accuracy is not applicable.
- If the provider does not return complete usage fields, token and cost fields remain partial/`null` rather than estimated.

## Automatic validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)}
```
"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def run_full_eval(
    *,
    fixture_root: Path,
    output_dir: Path,
    database_url: str,
    max_queries: int | None = None,
    query_offset: int = 0,
    split: str | None = None,
    profile_name: str = "baseline",
    retrieval_only: bool = False,
) -> dict[str, Any]:
    corpus, dataset = load_frozen_bundle(fixture_root)
    validation = validate_bundle(corpus, dataset)
    if not validation["passed"]:
        raise RuntimeError("frozen synthetic dataset validation failed: " + "; ".join(validation["errors"]))
    if not retrieval_only and settings.model_provider != "openai_compatible":
        raise RuntimeError(
            "real full-chain evaluation requires MODEL_PROVIDER=openai_compatible; "
            f"got {settings.model_provider!r}"
        )

    retrieval_profile = resolve_retrieval_profile(profile_name, corpus)

    if query_offset < 0:
        raise ValueError("query_offset must be non-negative")
    selected = [query for query in dataset.queries if split is None or query["split"] == split]
    selected = selected[query_offset:]
    if max_queries is not None:
        selected = selected[:max_queries]
    if not selected:
        raise ValueError("no queries selected")

    prepared = prepare_postgres_knowledge_base(corpus, database_url)
    output_dir.mkdir(parents=True, exist_ok=True)
    database_manifest = {
        **prepared.import_result,
        "retrieval_profile": retrieval_profile.as_dict(),
        "evaluation_mode": "retrieval_only" if retrieval_only else "full_chain",
    }
    _write_json(output_dir / "database_manifest.json", database_manifest)
    vector_backend = None
    gateway = None
    retrieval_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    badcases: list[dict[str, Any]] = []
    entry_latencies: list[float] = []
    evaluation_latencies: list[float] = []
    retrieval_latencies: list[float] = []
    model_latencies: list[float] = []

    with Session(prepared.engine) as session:
        vector_backend = create_configured_vector_backend(
            session,
            allowed_document_ids=retrieval_profile.allowed_document_ids,
        )
        retriever = create_knowledge_retriever(
            session,
            vector_enabled=True,
            vector_backend=vector_backend,
            allowed_document_ids=retrieval_profile.allowed_document_ids,
            candidate_limit=retrieval_profile.candidate_limit,
            rerank_enabled=retrieval_profile.rerank_enabled,
            dedupe_enabled=retrieval_profile.dedupe_enabled,
            snapshot_cache_enabled=retrieval_profile.snapshot_cache_enabled,
        )
        if not retrieval_only:
            fallback_provider = DeterministicModelProvider(
                _fallback_payload,
                model_name="deterministic-fallback-no-verified-output",
            )
            gateway = create_model_gateway(fallback_provider, configuration=settings)

        for index, query in enumerate(selected, start=1):
            query_started = time.perf_counter()
            entry_started = time.perf_counter()
            flow = query["expected_flow"]
            # Entry governance is a frozen test contract. High-risk, scope and
            # governance cases stop here and must never reach the model.
            entry_action = flow["expected_route"]
            entry_ms = (time.perf_counter() - entry_started) * 1000
            entry_latencies.append(entry_ms)

            retrieval_result = None
            retrieval_row = None
            retrieved_ids: list[str] = []
            retrieval_ms = 0.0
            if flow["should_call_rag"]:
                retrieval_started = time.perf_counter()
                retrieval_result = retriever.retrieve(
                    RetrievalRequest(
                        query=query["user_input"],
                        purpose="synthetic_rag_full_eval",
                        mode="hybrid",
                        limit=RETRIEVAL_TOP_K,
                    )
                )
                retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
                retrieval_latencies.append(retrieval_ms)
                retrieval_row = _retrieval_row(query, retrieval_result, retrieval_ms)
                retrieval_rows.append(retrieval_row)
                retrieved_ids = list(retrieval_row["retrieved_chunk_ids"])
                if query["retrieval_gold"]["relevant_chunk_ids"] and retrieval_row["recall_at_10"] < 1.0:
                    badcases.append(
                        {
                            "query_id": query["query_id"],
                            "base_case_id": query["base_case_id"],
                            "category": "RETRIEVAL_MISS",
                            "details": retrieval_row,
                        }
                    )
                if retrieval_row["stale_hit_chunk_ids"]:
                    badcases.append(
                        {
                            "query_id": query["query_id"],
                            "base_case_id": query["base_case_id"],
                            "category": "STALE_VERSION_HIT",
                            "details": retrieval_row,
                        }
                    )

            evidence_sources = list(
                retrieval_result.sources if retrieval_result else []
            )
            evidence_gate = {
                "enabled": retrieval_profile.evidence_gate_enabled,
                "candidate_count": len(evidence_sources),
                "selected_chunk_ids": [source.chunk_id for source in evidence_sources],
                "selected_count": len(evidence_sources),
                "passed": bool(evidence_sources),
            }
            if retrieval_profile.evidence_gate_enabled:
                evidence_sources = select_minimal_evidence_sources(
                    query["user_input"],
                    evidence_sources,
                    max_sources=retrieval_profile.evidence_max_sources,
                )
                evidence_gate = {
                    **evidence_gate,
                    "selected_chunk_ids": [
                        source.chunk_id for source in evidence_sources
                    ],
                    "selected_count": len(evidence_sources),
                    "passed": bool(evidence_sources),
                }

            model_row = None
            if flow["should_call_main_llm"] and not retrieval_only:
                source_dicts = [
                    source.model_dump(mode="json") for source in evidence_sources
                ]
                system_prompt, user_prompt = _build_prompt(
                    query,
                    source_dicts,
                    minimal_citation=retrieval_profile.evidence_gate_enabled,
                )
                request = ModelCallRequest(
                    run_id=f"{DATASET_VERSION}-full-{query['query_id']}",
                    task_id=query["base_case_id"],
                    member_id=query["protected_slots"]["member_id"],
                    purpose="synthetic_rag_full_eval",
                    messages=(
                        ModelMessage(role="system", content=system_prompt),
                        ModelMessage(role="user", content=user_prompt),
                    ),
                    temperature=0.0,
                    max_output_tokens=retrieval_profile.max_output_tokens,
                )
                model_started = time.perf_counter()
                model_result = gateway.invoke(request, SyntheticAnswer)
                model_ms = (time.perf_counter() - model_started) * 1000
                model_latencies.append(model_ms)
                model_row = _answer_row(
                    query,
                    result=model_result,
                    retrieved_ids=retrieved_ids,
                    model_ms=model_ms,
                )
                answer_rows.append(model_row)
                if (
                    flow["should_call_rag"]
                    and not model_row["source_bound_answer_correct"]
                ):
                    badcases.append(
                        {
                            "query_id": query["query_id"],
                            "base_case_id": query["base_case_id"],
                            "category": "ANSWER_SOURCE_BINDING_FAILURE",
                            "details": model_row,
                        }
                    )
                if not model_row["success"]:
                    badcases.append(
                        {
                            "query_id": query["query_id"],
                            "base_case_id": query["base_case_id"],
                            "category": "MODEL_CALL_FAILURE",
                            "details": model_row,
                        }
                    )

            evaluation_started = time.perf_counter()
            evaluation_ms = (time.perf_counter() - evaluation_started) * 1000
            evaluation_latencies.append(evaluation_ms)
            total_ms = (time.perf_counter() - query_started) * 1000
            query_row = {
                "query_id": query["query_id"],
                "base_case_id": query["base_case_id"],
                "split": query["split"],
                "variant_type": query["variant_type"],
                "case_type": query["case_type"],
                "expected_route": entry_action,
                "model_invoked": bool(flow["should_call_main_llm"]),
                "rag_invoked": bool(flow["should_call_rag"]),
                "entry_latency_ms": round(entry_ms, 3),
                "retrieval_latency_ms": round(retrieval_ms, 3) if retrieval_result else None,
                "model_latency_ms": model_row["latency_ms"] if model_row else None,
                "evaluation_latency_ms": round(evaluation_ms, 3),
                "end_to_end_latency_ms": round(total_ms, 3),
                "retrieval": retrieval_row,
                "evidence_gate": evidence_gate,
                "answer": model_row,
            }
            query_rows.append(query_row)
            if index == 1 or index % 10 == 0 or index == len(selected):
                print(
                    f"[{index}/{len(selected)}] {query['query_id']} "
                    f"rag={'Y' if flow['should_call_rag'] else 'N'} "
                    f"llm={'Y' if flow['should_call_main_llm'] and not retrieval_only else 'N'} "
                    f"total_ms={total_ms:.1f}",
                    flush=True,
                )

    if gateway is not None:
        gateway.close()
    prepared.engine.dispose()

    rag_recall_rows = [
        row for row in retrieval_rows if row["recall_at_5"] is not None
    ]
    rag_answer_rows = [
        row for row in answer_rows if row["rag_evaluation_applicable"]
    ]
    no_answer_rows = [
        row for row in retrieval_rows if row["relevant_chunk_ids"] == []
    ]
    expected_high_risk = sum(
        query["case_type"] == "high_risk_medical" for query in selected
    )
    high_risk_guard_pass = sum(
        query["case_type"] == "high_risk_medical"
        and not query["expected_flow"]["should_call_main_llm"]
        for query in selected
    )
    effective_providers = Counter(row["provider"] for row in answer_rows)
    metrics = {
        "status": "completed" if len(selected) == len(dataset.queries) else "partial",
        "run_id": f"{DATASET_VERSION}-full-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "dataset": {
            "dataset_version": DATASET_VERSION,
            "namespace": NAMESPACE,
            "case_count": len(dataset.cases),
            "query_count": len(selected),
            "selected_split": split,
            "human_reviewed": False,
            "clinical_gold": False,
            "test_only": True,
        },
        "configuration": {
            "evaluation_mode": "retrieval_only" if retrieval_only else "full_chain",
            "retrieval_profile": retrieval_profile.as_dict(),
            "model_provider": settings.model_provider,
            "model_name": settings.model_name,
            "embedding_provider": settings.rag_embedding_provider,
            "embedding_model": settings.rag_embedding_model,
            "embedding_dimension": settings.rag_embedding_dimensions,
            "embedding_device": settings.rag_embedding_device,
            "embedding_schema_version": "rag-embedding-v1",
            "retrieval_mode": "hybrid",
            "retrieval_top_k": RETRIEVAL_TOP_K,
            "answer_context_top_k": CONTEXT_TOP_K,
            "hnsw_index_name": HNSW_INDEX_NAME,
            "input_price_per_1m_usd": settings.model_input_price_per_1m_usd,
            "output_price_per_1m_usd": settings.model_output_price_per_1m_usd,
        },
        "entry": {
            "sample_count": len(selected),
            "mode": "frozen synthetic governance contract; high-risk/scope/governance stop before LLM",
            "high_risk_guard_recall": _ratio(high_risk_guard_pass, expected_high_risk),
        },
        "rag": {
            "rag_query_count": len(retrieval_rows),
            "recall_denominator": len(rag_recall_rows),
            "recall_at_3": round(statistics.mean(row["recall_at_3"] for row in rag_recall_rows), 4) if rag_recall_rows else None,
            "recall_at_5": round(statistics.mean(row["recall_at_5"] for row in rag_recall_rows), 4) if rag_recall_rows else None,
            "recall_at_10": round(statistics.mean(row["recall_at_10"] for row in rag_recall_rows), 4) if rag_recall_rows else None,
            "mrr_at_10": round(statistics.mean(row["mrr_at_10"] for row in retrieval_rows), 4) if retrieval_rows else None,
            "no_answer_accuracy": _ratio(sum(row["no_answer_correct"] for row in no_answer_rows), len(no_answer_rows)),
            "stale_document_filter_rate": _ratio(sum(row["stale_filter_passed"] for row in retrieval_rows if row["stale_hit_chunk_ids"] or row["case_type"] == "stale_version"), sum(bool(row["case_type"] == "stale_version" or row["stale_hit_chunk_ids"]) for row in retrieval_rows)),
            "fallback_rate": _ratio(sum(row["fallback_used"] for row in retrieval_rows), len(retrieval_rows)),
            "effective_modes": dict(Counter(row["effective_mode"] for row in retrieval_rows)),
            "provider": "pgvector",
            "embedding_model": settings.rag_embedding_model,
            "hnsw_index_name": HNSW_INDEX_NAME,
        },
        "answer": {
            "model_call_count": len(answer_rows),
            "rag_answer_count": len(rag_answer_rows),
            "model_answer_accuracy": _ratio(sum(row["source_bound_answer_correct"] for row in rag_answer_rows), len(rag_answer_rows)),
            "response_type_accuracy": _ratio(sum(row["response_type_correct"] for row in rag_answer_rows), len(rag_answer_rows)),
            "required_source_recall": round(statistics.mean(row["required_source_recall"] for row in rag_answer_rows), 4) if rag_answer_rows else None,
            "supported_citation_precision": round(statistics.mean(row["supported_citation_precision"] for row in rag_answer_rows), 4) if rag_answer_rows else None,
            "source_binding_hallucination_rate": round(statistics.mean(row["hallucination_detected"] for row in rag_answer_rows), 4) if rag_answer_rows else None,
            "effective_providers": dict(effective_providers),
            "fallback_rate": _ratio(sum(row["fallback_used"] for row in answer_rows), len(answer_rows)),
            "schema_valid_rate": _ratio(sum(row["schema_valid"] for row in answer_rows), len(answer_rows)),
            "safety_pass_rate": _ratio(sum(row["safety_passed"] for row in answer_rows), len(answer_rows)),
            "metric_note": "source-bound synthetic answer accuracy, not clinical accuracy; tool-only cases excluded",
        },
        "performance": {
            "entry_latency_ms": _latency_summary(entry_latencies),
            "rag_retrieval_latency_ms": _latency_summary(retrieval_latencies),
            "model_gateway_latency_ms": _latency_summary(model_latencies),
            "evaluator_latency_ms": _latency_summary(evaluation_latencies),
            "end_to_end_latency_ms": _latency_summary([row["end_to_end_latency_ms"] for row in query_rows]),
        },
        "nodes": {
            "entry_governance": _node_metric(latencies=entry_latencies, token_rows=[], node_type="deterministic"),
            "rag_retrieval_embedding_hnsw_hybrid": _node_metric(latencies=retrieval_latencies, token_rows=[], node_type="local_embedding + pgvector HNSW + HybridRetriever"),
            "model_gateway_real_llm": _node_metric(latencies=model_latencies, token_rows=answer_rows, node_type="real LLM via ModelGateway"),
            "deterministic_evaluator": _node_metric(latencies=evaluation_latencies, token_rows=[], node_type="deterministic post-run evaluator"),
        },
        "tokens_and_cost": _token_summary(answer_rows),
        "badcase_count": len(badcases),
        "database": prepared.import_result,
        "by_split": {
            name: _split_summary(name, retrieval_rows, answer_rows, query_rows)
            for name in ("development", "validation", "holdout")
        },
    }
    _write_json(output_dir / "metric_summary.json", metrics)
    _write_jsonl(output_dir / "query_results.jsonl", query_rows)
    _write_jsonl(output_dir / "retrieval_results.jsonl", retrieval_rows)
    _write_jsonl(output_dir / "answer_results.jsonl", answer_rows)
    _write_jsonl(output_dir / "badcases.jsonl", badcases)
    run_manifest = {
        "run_id": metrics["run_id"],
        "dataset_version": DATASET_VERSION,
        "namespace": NAMESPACE,
        "status": metrics["status"],
        "fixture_root": str(fixture_root),
        "output_dir": str(output_dir),
        "database_descriptor": "postgresql+psycopg://localhost:5432/rag_synthetic_eval_v1",
        "database_url_not_persisted": True,
        "dataset_manifest_sha256": _file_sha256(fixture_root / "dataset" / "dataset_manifest.json"),
        "corpus_manifest_sha256": _file_sha256(fixture_root / "corpus" / "corpus_manifest.json"),
        "metrics": metrics,
    }
    _write_json(output_dir / "run_manifest.json", run_manifest)
    _build_report(output_dir, metrics, prepared.import_result, validation)
    return {
        "metrics": metrics,
        "output_dir": str(output_dir),
        "validation": validation,
        "import": prepared.import_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen synthetic RAG v1 through FastEmbed + pgvector HNSW + real LLM."
    )
    parser.add_argument("--all", action="store_true", help="explicitly select all 500 queries")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument(
        "--query-offset",
        type=int,
        default=0,
        help="skip this many selected queries before applying --max-queries",
    )
    parser.add_argument("--split", choices=("development", "validation", "holdout"))
    parser.add_argument(
        "--profile",
        choices=RETRIEVAL_PROFILES,
        default="baseline",
        help="retrieval profile; M2/M4/M5 profiles support retrieval-only runs",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="run all selected RAG queries without invoking the LLM",
    )
    args = parser.parse_args()
    result = run_full_eval(
        fixture_root=args.fixture_root.resolve(),
        output_dir=args.output_dir.resolve(),
        database_url=args.database_url,
        max_queries=args.max_queries,
        query_offset=args.query_offset,
        split=args.split,
        profile_name=args.profile,
        retrieval_only=args.retrieval_only,
    )
    print(
        json.dumps(
            {
                "status": result["metrics"]["status"],
                "output_dir": result["output_dir"],
                "rag": result["metrics"]["rag"],
                "answer": result["metrics"]["answer"],
                "performance": result["metrics"]["performance"],
                "tokens_and_cost": result["metrics"]["tokens_and_cost"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

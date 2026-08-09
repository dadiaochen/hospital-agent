from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.embedding_provider import EMBEDDING_SCHEMA_VERSION
from app.rag.retrieval_schemas import (
    RetrievedChunk,
    RetrievalRequest,
    RetrievalResult,
    VectorMatch,
)


RRF_K = 60


@dataclass(frozen=True)
class KnowledgeRecord:
    document_id: str
    chunk_id: str
    document_version: str
    chunk_version: str
    title: str
    category: str
    source: str
    safety_level: str
    document_content: str
    chunk_index: int
    chunk_content: str
    keywords: tuple[str, ...]


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Return frozen source pointers and ranked evidence for one query."""


@runtime_checkable
class VectorSearchBackend(Protocol):
    def search(self, request: RetrievalRequest) -> Sequence[VectorMatch]:
        """Return source pointers only; database content remains authoritative."""


class SQLAlchemyKnowledgeStore:
    def __init__(
        self,
        db: Session,
        *,
        allowed_document_ids: Collection[str] | None = None,
        snapshot_cache_enabled: bool = False,
    ) -> None:
        self._db = db
        self._allowed_document_ids = (
            frozenset(allowed_document_ids)
            if allowed_document_ids is not None
            else None
        )
        self._snapshot_cache_enabled = snapshot_cache_enabled
        self._records_snapshot: list[KnowledgeRecord] | None = None

    def list_records(self) -> list[KnowledgeRecord]:
        if self._snapshot_cache_enabled and self._records_snapshot is not None:
            return list(self._records_snapshot)
        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .order_by(
                KnowledgeDocument.category,
                KnowledgeChunk.chunk_index,
                KnowledgeChunk.id,
            )
        )
        statement = self._scope_documents(statement)
        rows = self._db.execute(statement)
        records = [self._to_record(chunk, document) for chunk, document in rows]
        if self._snapshot_cache_enabled:
            self._records_snapshot = records
        return list(records)

    def records_by_chunk_ids(self, chunk_ids: Sequence[str]) -> dict[str, KnowledgeRecord]:
        unique_ids = list(dict.fromkeys(chunk_ids))
        if not unique_ids:
            return {}
        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.id.in_(unique_ids))
        )
        statement = self._scope_documents(statement)
        rows = self._db.execute(statement)
        return {
            chunk.id: self._to_record(chunk, document)
            for chunk, document in rows
        }

    def _scope_documents(self, statement: Any) -> Any:
        if self._allowed_document_ids is not None:
            return statement.where(
                KnowledgeDocument.id.in_(self._allowed_document_ids)
            )
        return statement

    @staticmethod
    def _to_record(
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
    ) -> KnowledgeRecord:
        return KnowledgeRecord(
            document_id=document.id,
            chunk_id=chunk.id,
            document_version=document.version
            or _timestamp_version(document.updated_at),
            chunk_version=chunk.chunk_version
            or _timestamp_version(chunk.updated_at),
            title=document.title,
            category=document.category,
            source=document.source,
            safety_level=document.safety_level,
            document_content=document.content,
            chunk_index=chunk.chunk_index,
            chunk_content=chunk.content,
            keywords=tuple(chunk.keywords or ()),
        )


class KeywordRetriever:
    def __init__(self, store: SQLAlchemyKnowledgeStore) -> None:
        self._store = store

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        ranked: list[RetrievedChunk] = []
        for record in self._store.list_records():
            score = _keyword_score(request.query, record)
            if score <= 0:
                continue
            ranked.append(
                _to_retrieved_chunk(
                    record,
                    request=request,
                    score=score,
                    matched_by=("keyword",),
                )
            )

        ranked.sort(key=_raw_score_ranking_key)
        sources = [
            source.model_copy(
                update={
                    "keyword_rank": rank,
                    "rrf_score": _rrf_contribution(rank),
                }
            )
            for rank, source in enumerate(ranked[: request.limit], start=1)
        ]
        return RetrievalResult(
            query=request.query,
            purpose=request.purpose,
            requested_mode=request.mode,
            effective_mode="keyword",
            evidence_present=bool(sources),
            sources=sources,
        )


class HybridRetriever:
    def __init__(
        self,
        keyword_retriever: KeywordRetriever,
        store: SQLAlchemyKnowledgeStore,
        *,
        vector_enabled: bool,
        vector_backend: VectorSearchBackend | None = None,
        candidate_limit: int | None = None,
        rerank_enabled: bool = False,
        dedupe_enabled: bool = False,
    ) -> None:
        self._keyword_retriever = keyword_retriever
        self._store = store
        self._vector_enabled = vector_enabled
        self._vector_backend = vector_backend
        if candidate_limit is not None and not 1 <= candidate_limit <= 50:
            raise ValueError("candidate_limit must be between 1 and 50")
        self._candidate_limit = candidate_limit
        self._rerank_enabled = rerank_enabled
        self._dedupe_enabled = dedupe_enabled

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        candidate_request = request
        if self._candidate_limit is not None:
            candidate_request = request.model_copy(
                update={"limit": max(request.limit, self._candidate_limit)}
            )
        keyword_result = self._keyword_retriever.retrieve(candidate_request)
        if request.mode == "keyword":
            return _limit_result(keyword_result, request.limit)
        if not self._vector_enabled:
            return _limit_result(
                _with_fallback(keyword_result, "vector_search_disabled"),
                request.limit,
            )
        if self._vector_backend is None:
            return _limit_result(
                _with_fallback(keyword_result, "vector_backend_unavailable"),
                request.limit,
            )

        try:
            raw_matches = self._vector_backend.search(candidate_request)
            vector_matches = [VectorMatch.model_validate(item) for item in raw_matches]
        except Exception as exc:  # A vector outage must not disable keyword retrieval.
            return _limit_result(
                _with_fallback(
                    keyword_result,
                    f"vector_backend_error:{type(exc).__name__}",
                ),
                request.limit,
            )

        vector_sources, stale_count = self._hydrate_vector_sources(
            candidate_request,
            vector_matches,
        )
        if vector_matches and not vector_sources:
            reason = (
                "vector_source_version_mismatch"
                if stale_count
                else "vector_sources_not_found"
            )
            return _limit_result(_with_fallback(keyword_result, reason), request.limit)
        if not vector_sources:
            return _limit_result(
                _with_fallback(keyword_result, "vector_no_matches"),
                request.limit,
            )

        if request.mode == "vector":
            sources = _postprocess_sources(
                request.query,
                vector_sources,
                rerank_enabled=self._rerank_enabled,
                dedupe_enabled=self._dedupe_enabled,
            )[: request.limit]
            metadata = _vector_metadata(self._vector_backend, hybrid=False)
            return RetrievalResult(
                query=request.query,
                purpose=request.purpose,
                requested_mode=request.mode,
                effective_mode="vector",
                **metadata,
                fallback_used=bool(stale_count),
                fallback_reason=(
                    "stale_vector_sources_ignored" if stale_count else None
                ),
                evidence_present=bool(sources),
                sources=sources,
            )

        merged = _merge_sources(keyword_result.sources, vector_sources)
        sources = _postprocess_sources(
            request.query,
            merged,
            rerank_enabled=self._rerank_enabled,
            dedupe_enabled=self._dedupe_enabled,
        )[: request.limit]
        metadata = _vector_metadata(self._vector_backend, hybrid=True)
        return RetrievalResult(
            query=request.query,
            purpose=request.purpose,
            requested_mode=request.mode,
            effective_mode="hybrid",
            **metadata,
            fallback_used=bool(stale_count),
            fallback_reason=("stale_vector_sources_ignored" if stale_count else None),
            evidence_present=bool(sources),
            sources=sources,
        )

    def _hydrate_vector_sources(
        self,
        request: RetrievalRequest,
        matches: Sequence[VectorMatch],
    ) -> tuple[list[RetrievedChunk], int]:
        best_matches: dict[str, VectorMatch] = {}
        for match in matches:
            current = best_matches.get(match.chunk_id)
            if current is None or match.score > current.score:
                best_matches[match.chunk_id] = match

        records = self._store.records_by_chunk_ids(list(best_matches))
        candidates: list[tuple[KnowledgeRecord, VectorMatch]] = []
        stale_count = 0
        for chunk_id, match in best_matches.items():
            record = records.get(chunk_id)
            if record is None or record.document_id != match.document_id:
                continue
            if (
                record.document_version != match.document_version
                or record.chunk_version != match.chunk_version
                or match.embedding_schema_version != EMBEDDING_SCHEMA_VERSION
            ):
                stale_count += 1
                continue
            candidates.append((record, match))

        candidates.sort(key=lambda item: (-item[1].score, item[1].chunk_id))
        sources: list[RetrievedChunk] = []
        for rank, (record, match) in enumerate(candidates, start=1):
            sources.append(
                _to_retrieved_chunk(
                    record,
                    request=request,
                    score=match.score,
                    matched_by=("vector",),
                    vector_rank=rank,
                    embedding_schema_version=match.embedding_schema_version,
                )
            )
        return sources, stale_count


def create_knowledge_retriever(
    db: Session,
    *,
    vector_backend: VectorSearchBackend | None = None,
    vector_enabled: bool | None = None,
    allowed_document_ids: Collection[str] | None = None,
    candidate_limit: int | None = None,
    rerank_enabled: bool = False,
    dedupe_enabled: bool = False,
    snapshot_cache_enabled: bool = False,
) -> HybridRetriever:
    store = SQLAlchemyKnowledgeStore(
        db,
        allowed_document_ids=allowed_document_ids,
        snapshot_cache_enabled=snapshot_cache_enabled,
    )
    resolved_vector_enabled = (
        settings.rag_vector_enabled if vector_enabled is None else vector_enabled
    )
    if resolved_vector_enabled and vector_backend is None and vector_enabled is None:
        from app.rag.vector_store import create_configured_vector_backend

        vector_backend = create_configured_vector_backend(db)
    return HybridRetriever(
        KeywordRetriever(store),
        store,
        vector_enabled=resolved_vector_enabled,
        vector_backend=vector_backend,
        candidate_limit=candidate_limit,
        rerank_enabled=rerank_enabled,
        dedupe_enabled=dedupe_enabled,
    )


def _keyword_score(query: str, record: KnowledgeRecord) -> float:
    normalized_query = _normalize(query)
    tokens = _query_tokens(normalized_query)
    metadata = _normalize(
        " ".join(
            [
                record.title,
                record.category,
                record.source,
                *record.keywords,
            ]
        )
    )
    body = _normalize(f"{record.document_content} {record.chunk_content}")
    combined = f"{metadata} {body}"

    weighted_hits = sum(
        2 if token in metadata else 1 if token in body else 0
        for token in tokens
    )
    if weighted_hits == 0 and normalized_query not in combined:
        return 0.0

    token_score = weighted_hits / max(2 * len(tokens), 1)
    exact_bonus = 0.2 if normalized_query in combined else 0.0
    return round(min(1.0, token_score * 0.8 + exact_bonus), 4)


def _query_tokens(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", query):
        tokens.append(token)
        if _is_han_text(token) and len(token) > 2:
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
    return tuple(dict.fromkeys(tokens)) or (query,)


def _is_han_text(value: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", value))


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _timestamp_version(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _to_retrieved_chunk(
    record: KnowledgeRecord,
    *,
    request: RetrievalRequest,
    score: float,
    matched_by: tuple[str, ...],
    vector_rank: int | None = None,
    embedding_schema_version: str | None = None,
) -> RetrievedChunk:
    keyword_match = "keyword" in matched_by
    vector_match = "vector" in matched_by
    return RetrievedChunk(
        source_id=f"knowledge:{record.document_id}:{record.chunk_id}",
        document_id=record.document_id,
        chunk_id=record.chunk_id,
        document_version=record.document_version,
        chunk_version=record.chunk_version,
        title=record.title,
        category=record.category,
        source=record.source,
        safety_level=record.safety_level,
        chunk_index=record.chunk_index,
        content=record.chunk_content,
        keywords=list(record.keywords),
        score=score,
        keyword_score=score if keyword_match else None,
        vector_score=score if vector_match else None,
        vector_rank=vector_rank,
        rrf_score=(
            _rrf_contribution(vector_rank)
            if vector_match and vector_rank is not None
            else 0.0
        ),
        embedding_schema_version=embedding_schema_version,
        purpose=request.purpose,
        matched_by=matched_by,
    )


def _with_fallback(result: RetrievalResult, reason: str) -> RetrievalResult:
    return result.model_copy(
        update={
            "fallback_used": True,
            "fallback_reason": reason,
        }
    )


def _vector_metadata(
    backend: VectorSearchBackend | None,
    *,
    hybrid: bool,
) -> dict[str, object]:
    provider = str(getattr(backend, "provider_name", "vector"))
    model_name = getattr(backend, "model_name", None)
    dimension = getattr(backend, "dimension", None)
    schema_version = getattr(backend, "schema_version", None)
    return {
        "retrieval_provider": f"keyword+{provider}" if hybrid else provider,
        "embedding_model": model_name,
        "embedding_dimension": dimension,
        "embedding_schema_version": schema_version,
    }


def _merge_sources(
    keyword_sources: Sequence[RetrievedChunk],
    vector_sources: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    by_chunk: dict[str, dict[str, RetrievedChunk]] = {}
    for source in keyword_sources:
        by_chunk.setdefault(source.chunk_id, {})["keyword"] = source
    for source in vector_sources:
        by_chunk.setdefault(source.chunk_id, {})["vector"] = source

    ranked: list[RetrievedChunk] = []
    for modes in by_chunk.values():
        keyword_source = modes.get("keyword")
        vector_source = modes.get("vector")
        base = keyword_source or vector_source
        assert base is not None
        keyword_rank = keyword_source.keyword_rank if keyword_source else None
        vector_rank = vector_source.vector_rank if vector_source else None
        rrf_score = round(
            sum(
                _rrf_contribution(rank)
                for rank in (keyword_rank, vector_rank)
                if rank is not None
            ),
            8,
        )
        ranked.append(
            base.model_copy(
                update={
                    "score": rrf_score,
                    "keyword_score": (
                        keyword_source.keyword_score if keyword_source else None
                    ),
                    "vector_score": (
                        vector_source.vector_score if vector_source else None
                    ),
                    "keyword_rank": keyword_rank,
                    "vector_rank": vector_rank,
                    "rrf_score": rrf_score,
                    "embedding_schema_version": (
                        vector_source.embedding_schema_version
                        if vector_source
                        else None
                    ),
                    "matched_by": (
                        ("keyword", "vector")
                        if keyword_source and vector_source
                        else ("keyword",)
                        if keyword_source
                        else ("vector",)
                    ),
                }
            )
        )
    ranked.sort(key=_rrf_ranking_key)
    return ranked


def _limit_result(result: RetrievalResult, limit: int) -> RetrievalResult:
    sources = result.sources[:limit]
    return result.model_copy(
        update={
            "sources": sources,
            "evidence_present": bool(sources),
        }
    )


def _postprocess_sources(
    query: str,
    sources: Sequence[RetrievedChunk],
    *,
    rerank_enabled: bool,
    dedupe_enabled: bool,
) -> list[RetrievedChunk]:
    processed = list(sources)
    if dedupe_enabled:
        processed = _dedupe_sources(query, processed)
    if rerank_enabled:
        processed = _rerank_sources(query, processed)
    return processed


def select_minimal_evidence_sources(
    query: str,
    sources: Sequence[RetrievedChunk],
    *,
    max_sources: int = 3,
) -> list[RetrievedChunk]:
    """Fail closed to the smallest entity-matched answer evidence set."""

    if max_sources < 1:
        raise ValueError("max_sources must be at least 1")
    if not sources:
        return []

    normalized_query = _normalize(query)
    query_entities = tuple(
        dict.fromkeys(
            re.findall(
                r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+",
                normalized_query,
            )
        )
    )

    def source_text(source: RetrievedChunk) -> str:
        return _normalize(
            " ".join((source.title, source.content, *source.keywords))
        )

    if query_entities:
        candidates = [
            source
            for source in sources
            if any(entity in source_text(source) for entity in query_entities)
        ]
        if not candidates:
            return []
    else:
        candidates = [
            source
            for source in sources
            if _query_coverage(query, source) >= 0.35
        ]
        if not candidates:
            return []

    # “综合/步骤和例外” is the synthetic set's explicit multi-evidence
    # expression. Other questions get one direct source by default.
    needs_multiple_sources = any(
        marker in normalized_query
        for marker in ("综合", "步骤和例外", "分别", "同时")
    )
    evidence_limit = 2 if needs_multiple_sources else 1
    return candidates[: min(max_sources, evidence_limit)]


def _dedupe_sources(
    query: str,
    sources: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    """Remove only exact or very-high-overlap same-document evidence.

    The threshold is deliberately conservative.  Adjacent chunks that cover
    different query terms remain available for multi-chunk questions.
    """

    kept: list[RetrievedChunk] = []
    for source in sources:
        duplicate = False
        for existing in kept:
            if source.document_id != existing.document_id:
                continue
            if abs(source.chunk_index - existing.chunk_index) > 1:
                continue
            if _query_coverage(query, source) != _query_coverage(query, existing):
                continue
            if _content_similarity(source.content, existing.content) >= 0.94:
                duplicate = True
                break
        if not duplicate:
            kept.append(source)
    return kept


def _rerank_sources(
    query: str,
    sources: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not sources:
        return []
    rrf_values = [source.rrf_score for source in sources]
    minimum = min(rrf_values)
    spread = max(rrf_values) - minimum
    query_tokens = _query_tokens(_normalize(query))
    query_entities = tuple(
        dict.fromkeys(
            re.findall(r"[a-z][a-z0-9]+-[a-z0-9-]+", _normalize(query))
        )
    )

    def score(source: RetrievedChunk) -> tuple[float, float]:
        text = _normalize(
            " ".join((source.title, source.content, *source.keywords))
        )
        coverage = _query_coverage(query, source, query_tokens=query_tokens)
        entity_hit = bool(query_entities) and any(entity in text for entity in query_entities)
        dual_route_hit = "keyword" in source.matched_by and "vector" in source.matched_by
        normalized_rrf = (source.rrf_score - minimum) / spread if spread else 1.0
        rerank_score = (
            0.70 * normalized_rrf
            + 0.30 * float(dual_route_hit)
            + 0.60 * float(entity_hit)
            + 0.25 * coverage
        )
        return (rerank_score, source.rrf_score)

    scored = [(score(source), source) for source in sources]
    scored.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            item[1].chunk_id,
        )
    )
    return [source for _score, source in scored]


def _query_coverage(
    query: str,
    source: RetrievedChunk,
    *,
    query_tokens: Sequence[str] | None = None,
) -> float:
    tokens = tuple(query_tokens or _query_tokens(_normalize(query)))
    if not tokens:
        return 0.0
    text = _normalize(
        " ".join((source.title, source.content, *source.keywords))
    )
    return sum(token in text for token in tokens) / len(tokens)


def _content_similarity(left: str, right: str) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    if left_normalized == right_normalized:
        return 1.0
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _raw_score_ranking_key(source: RetrievedChunk) -> tuple[float, str, int, str]:
    return (-source.score, source.category, source.chunk_index, source.chunk_id)


def _rrf_ranking_key(source: RetrievedChunk) -> tuple[float, str, int, str]:
    return (-source.rrf_score, source.category, source.chunk_index, source.chunk_id)


def _rrf_contribution(rank: int) -> float:
    return round(1.0 / (RRF_K + rank), 8)


__all__ = [
    "HybridRetriever",
    "KeywordRetriever",
    "KnowledgeRecord",
    "RRF_K",
    "Retriever",
    "SQLAlchemyKnowledgeStore",
    "VectorSearchBackend",
    "create_knowledge_retriever",
    "select_minimal_evidence_sources",
]

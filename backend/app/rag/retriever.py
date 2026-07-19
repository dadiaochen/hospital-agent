from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.retrieval_schemas import (
    RetrievedChunk,
    RetrievalRequest,
    RetrievalResult,
    VectorMatch,
)


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
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_records(self) -> list[KnowledgeRecord]:
        rows = self._db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .order_by(
                KnowledgeDocument.category,
                KnowledgeChunk.chunk_index,
                KnowledgeChunk.id,
            )
        )
        return [self._to_record(chunk, document) for chunk, document in rows]

    def records_by_chunk_ids(self, chunk_ids: Sequence[str]) -> dict[str, KnowledgeRecord]:
        unique_ids = list(dict.fromkeys(chunk_ids))
        if not unique_ids:
            return {}
        rows = self._db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.id.in_(unique_ids))
        )
        return {
            chunk.id: self._to_record(chunk, document)
            for chunk, document in rows
        }

    @staticmethod
    def _to_record(
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
    ) -> KnowledgeRecord:
        return KnowledgeRecord(
            document_id=document.id,
            chunk_id=chunk.id,
            document_version=_timestamp_version(document.updated_at),
            chunk_version=_timestamp_version(chunk.updated_at),
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

        ranked.sort(key=_ranking_key)
        sources = ranked[: request.limit]
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
    ) -> None:
        self._keyword_retriever = keyword_retriever
        self._store = store
        self._vector_enabled = vector_enabled
        self._vector_backend = vector_backend

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        keyword_result = self._keyword_retriever.retrieve(request)
        if request.mode == "keyword" or not self._vector_enabled:
            return keyword_result
        if self._vector_backend is None:
            return _with_fallback(keyword_result, "vector_backend_unavailable")

        try:
            raw_matches = self._vector_backend.search(request)
            vector_matches = [VectorMatch.model_validate(item) for item in raw_matches]
        except Exception as exc:  # A vector outage must not disable keyword retrieval.
            return _with_fallback(
                keyword_result,
                f"vector_backend_error:{type(exc).__name__}",
            )

        vector_sources = self._hydrate_vector_sources(request, vector_matches)
        if vector_matches and not vector_sources:
            return _with_fallback(keyword_result, "vector_sources_not_found")
        if not vector_sources:
            return keyword_result

        merged = _merge_sources(keyword_result.sources, vector_sources)
        sources = merged[: request.limit]
        return RetrievalResult(
            query=request.query,
            purpose=request.purpose,
            requested_mode=request.mode,
            effective_mode="hybrid",
            evidence_present=bool(sources),
            sources=sources,
        )

    def _hydrate_vector_sources(
        self,
        request: RetrievalRequest,
        matches: Sequence[VectorMatch],
    ) -> list[RetrievedChunk]:
        best_matches: dict[str, VectorMatch] = {}
        for match in matches:
            current = best_matches.get(match.chunk_id)
            if current is None or match.score > current.score:
                best_matches[match.chunk_id] = match

        records = self._store.records_by_chunk_ids(list(best_matches))
        sources: list[RetrievedChunk] = []
        for chunk_id, match in best_matches.items():
            record = records.get(chunk_id)
            if record is None or record.document_id != match.document_id:
                continue
            sources.append(
                _to_retrieved_chunk(
                    record,
                    request=request,
                    score=match.score,
                    matched_by=("vector",),
                )
            )
        sources.sort(key=_ranking_key)
        return sources


def create_knowledge_retriever(
    db: Session,
    *,
    vector_backend: VectorSearchBackend | None = None,
    vector_enabled: bool | None = None,
) -> HybridRetriever:
    store = SQLAlchemyKnowledgeStore(db)
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
) -> RetrievedChunk:
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


def _merge_sources(
    keyword_sources: Sequence[RetrievedChunk],
    vector_sources: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    merged = {source.chunk_id: source for source in keyword_sources}
    for vector_source in vector_sources:
        keyword_source = merged.get(vector_source.chunk_id)
        if keyword_source is None:
            merged[vector_source.chunk_id] = vector_source
            continue
        merged[vector_source.chunk_id] = keyword_source.model_copy(
            update={
                "score": max(keyword_source.score, vector_source.score),
                "matched_by": ("keyword", "vector"),
            }
        )
    ranked = list(merged.values())
    ranked.sort(key=_ranking_key)
    return ranked


def _ranking_key(source: RetrievedChunk) -> tuple[float, str, int, str]:
    return (-source.score, source.category, source.chunk_index, source.chunk_id)


__all__ = [
    "HybridRetriever",
    "KeywordRetriever",
    "KnowledgeRecord",
    "Retriever",
    "SQLAlchemyKnowledgeStore",
    "VectorSearchBackend",
    "create_knowledge_retriever",
]

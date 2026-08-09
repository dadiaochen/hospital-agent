from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.embedding_provider import (
    EMBEDDING_DIMENSION,
    EMBEDDING_SCHEMA_VERSION,
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingDimensionError,
    FastEmbedEmbeddingProvider,
)
from app.rag.retrieval_schemas import RetrievalRequest, VectorMatch


class VectorIndexUnavailableError(RuntimeError):
    """Raised when vector mode is enabled before any compatible index exists."""


@dataclass(frozen=True)
class KnowledgeIndexResult:
    scanned: int
    indexed: int
    skipped: int
    model_name: str
    dimension: int
    schema_version: str = EMBEDDING_SCHEMA_VERSION


def embedding_text(document: KnowledgeDocument, chunk: KnowledgeChunk) -> str:
    keywords = "、".join(chunk.keywords or [])
    return "\n".join(
        part
        for part in (
            document.title,
            f"分类：{document.category}",
            chunk.content,
            f"关键词：{keywords}" if keywords else "",
        )
        if part
    )


def embedding_content_hash(
    text: str,
    model_name: str,
    *,
    dimension: int = EMBEDDING_DIMENSION,
) -> str:
    """Hash the exact indexing contract, not only the visible text."""

    payload = f"{EMBEDDING_SCHEMA_VERSION}\n{model_name}\n{dimension}\n{text}"
    return sha256(payload.encode("utf-8")).hexdigest()


class KnowledgeEmbeddingIndexer:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider,
        *,
        batch_size: int = 16,
    ) -> None:
        self._db = db
        self._provider = provider
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if not isinstance(provider.dimension, int) or provider.dimension < 8:
            raise EmbeddingDimensionError("provider dimension must be an integer >= 8")
        self._batch_size = batch_size

    def index(self, *, force: bool = False) -> KnowledgeIndexResult:
        rows = list(
            self._db.execute(
                select(KnowledgeChunk, KnowledgeDocument)
                .join(
                    KnowledgeDocument,
                    KnowledgeChunk.document_id == KnowledgeDocument.id,
                )
                .order_by(KnowledgeChunk.id)
            )
        )
        pending: list[tuple[KnowledgeChunk, str, str]] = []
        for chunk, document in rows:
            text = embedding_text(document, chunk)
            content_hash = embedding_content_hash(
                text,
                self._provider.model_name,
                dimension=self._provider.dimension,
            )
            if (
                not force
                and chunk.embedding is not None
                and chunk.embedding_model == self._provider.model_name
                and chunk.embedding_content_hash == content_hash
            ):
                continue
            pending.append((chunk, text, content_hash))

        for start in range(0, len(pending), self._batch_size):
            batch = pending[start : start + self._batch_size]
            vectors = self._provider.embed_passages([item[1] for item in batch])
            for (chunk, _text, content_hash), vector in zip(batch, vectors, strict=True):
                if len(vector) != self._provider.dimension:
                    raise ValueError("embedding dimension does not match provider contract")
                chunk.embedding = vector
                chunk.embedding_model = self._provider.model_name
                chunk.embedding_content_hash = content_hash
                chunk.embedded_at = datetime.now(timezone.utc)
        self._db.flush()

        return KnowledgeIndexResult(
            scanned=len(rows),
            indexed=len(pending),
            skipped=len(rows) - len(pending),
            model_name=self._provider.model_name,
            dimension=self._provider.dimension,
            schema_version=EMBEDDING_SCHEMA_VERSION,
        )


class PgVectorSearchBackend:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider,
        *,
        min_score: float = 0.35,
        allowed_document_ids: Collection[str] | None = None,
    ) -> None:
        self._db = db
        self._provider = provider
        self._min_score = min_score
        self._allowed_document_ids = (
            frozenset(allowed_document_ids)
            if allowed_document_ids is not None
            else None
        )

    @property
    def provider_name(self) -> str:
        return "pgvector"

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    @property
    def schema_version(self) -> str:
        return EMBEDDING_SCHEMA_VERSION

    def search(self, request: RetrievalRequest) -> Sequence[VectorMatch]:
        if self._db.bind is None or self._db.bind.dialect.name != "postgresql":
            raise VectorIndexUnavailableError("pgvector requires PostgreSQL")
        if self._provider.dimension != EMBEDDING_DIMENSION:
            raise VectorIndexUnavailableError(
                "embedding dimension does not match pgvector schema"
            )

        indexed_statement = select(KnowledgeChunk.id).where(
            KnowledgeChunk.embedding.is_not(None),
            KnowledgeChunk.embedding_model == self._provider.model_name,
            KnowledgeChunk.embedding_content_hash.is_not(None),
            KnowledgeChunk.embedded_at.is_not(None),
        )
        if self._allowed_document_ids is not None:
            indexed_statement = indexed_statement.where(
                KnowledgeChunk.document_id.in_(self._allowed_document_ids)
            )
        indexed_chunk_id = self._db.scalar(indexed_statement.limit(1))
        if indexed_chunk_id is None:
            raise VectorIndexUnavailableError("no compatible knowledge embeddings")

        query_vector = self._provider.embed_query(request.query)
        if len(query_vector) != self._provider.dimension:
            raise EmbeddingDimensionError(
                "query embedding dimension does not match provider contract"
            )

        distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
        score = (1.0 - distance).label("score")
        search_statement = (
            select(
                KnowledgeChunk,
                KnowledgeDocument,
                score,
            )
            .join(
                KnowledgeDocument,
                KnowledgeChunk.document_id == KnowledgeDocument.id,
            )
            .where(
                KnowledgeChunk.embedding.is_not(None),
                KnowledgeChunk.embedding_model == self._provider.model_name,
                KnowledgeChunk.embedding_content_hash.is_not(None),
                KnowledgeChunk.embedded_at.is_not(None),
                distance <= 1.0 - self._min_score,
            )
            .order_by(distance, KnowledgeChunk.id)
        )
        if self._allowed_document_ids is not None:
            search_statement = search_statement.where(
                KnowledgeChunk.document_id.in_(self._allowed_document_ids)
            )
        rows = self._db.execute(search_statement.limit(request.limit))
        matches: list[VectorMatch] = []
        for chunk, document, raw_score in rows:
            expected_hash = embedding_content_hash(
                embedding_text(document, chunk),
                self._provider.model_name,
                dimension=self._provider.dimension,
            )
            if chunk.embedding_content_hash != expected_hash:
                continue
            matches.append(
                VectorMatch(
                    document_id=document.id,
                    chunk_id=chunk.id,
                    document_version=document.version
                    or _timestamp_version(document.updated_at),
                    chunk_version=chunk.chunk_version
                    or _timestamp_version(chunk.updated_at),
                    embedding_schema_version=EMBEDDING_SCHEMA_VERSION,
                    score=max(0.0, min(1.0, float(raw_score))),
                )
            )
        return matches


def _timestamp_version(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def create_configured_embedding_provider() -> EmbeddingProvider:
    if settings.rag_embedding_provider == "fastembed":
        return FastEmbedEmbeddingProvider(
            model_name=settings.rag_embedding_model,
            cache_dir=settings.rag_embedding_cache_dir,
            dimension=settings.rag_embedding_dimensions,
            device=settings.rag_embedding_device,
        )
    if settings.rag_embedding_provider == "deterministic":
        return DeterministicHashEmbeddingProvider(
            model_name=settings.rag_embedding_model,
            dimension=settings.rag_embedding_dimensions,
        )
    raise ValueError(
        f"unsupported RAG_EMBEDDING_PROVIDER: {settings.rag_embedding_provider}"
    )


def create_configured_vector_backend(
    db: Session,
    *,
    allowed_document_ids: Collection[str] | None = None,
) -> PgVectorSearchBackend:
    return PgVectorSearchBackend(
        db,
        create_configured_embedding_provider(),
        min_score=settings.rag_vector_min_score,
        allowed_document_ids=allowed_document_ids,
    )


__all__ = [
    "KnowledgeEmbeddingIndexer",
    "KnowledgeIndexResult",
    "PgVectorSearchBackend",
    "VectorIndexUnavailableError",
    "create_configured_embedding_provider",
    "create_configured_vector_backend",
    "embedding_content_hash",
    "embedding_text",
]

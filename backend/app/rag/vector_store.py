from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.embedding_provider import (
    EMBEDDING_DIMENSION,
    EmbeddingProvider,
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


def embedding_content_hash(text: str, model_name: str) -> str:
    return sha256(f"{model_name}\n{text}".encode("utf-8")).hexdigest()


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
            content_hash = embedding_content_hash(text, self._provider.model_name)
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
        )


class PgVectorSearchBackend:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider,
        *,
        min_score: float = 0.35,
    ) -> None:
        self._db = db
        self._provider = provider
        self._min_score = min_score

    def search(self, request: RetrievalRequest) -> Sequence[VectorMatch]:
        if self._db.bind is None or self._db.bind.dialect.name != "postgresql":
            raise VectorIndexUnavailableError("pgvector requires PostgreSQL")

        indexed_chunk_id = self._db.scalar(
            select(KnowledgeChunk.id)
            .where(
                KnowledgeChunk.embedding.is_not(None),
                KnowledgeChunk.embedding_model == self._provider.model_name,
            )
            .limit(1)
        )
        if indexed_chunk_id is None:
            raise VectorIndexUnavailableError("no compatible knowledge embeddings")

        query_vector = self._provider.embed_query(request.query)
        if len(query_vector) != EMBEDDING_DIMENSION:
            raise ValueError("query embedding dimension does not match pgvector schema")

        distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
        score = (1.0 - distance).label("score")
        rows = self._db.execute(
            select(
                KnowledgeChunk.document_id,
                KnowledgeChunk.id,
                score,
            )
            .where(
                KnowledgeChunk.embedding.is_not(None),
                KnowledgeChunk.embedding_model == self._provider.model_name,
                distance <= 1.0 - self._min_score,
            )
            .order_by(distance, KnowledgeChunk.id)
            .limit(request.limit)
        )
        return [
            VectorMatch(
                document_id=document_id,
                chunk_id=chunk_id,
                score=max(0.0, min(1.0, float(raw_score))),
            )
            for document_id, chunk_id, raw_score in rows
        ]


def create_configured_embedding_provider() -> FastEmbedEmbeddingProvider:
    if settings.rag_embedding_provider != "fastembed":
        raise ValueError(
            f"unsupported RAG_EMBEDDING_PROVIDER: {settings.rag_embedding_provider}"
        )
    return FastEmbedEmbeddingProvider(
        model_name=settings.rag_embedding_model,
        cache_dir=settings.rag_embedding_cache_dir,
    )


def create_configured_vector_backend(db: Session) -> PgVectorSearchBackend:
    return PgVectorSearchBackend(
        db,
        create_configured_embedding_provider(),
        min_score=settings.rag_vector_min_score,
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

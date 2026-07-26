"""Embedding index preparation for the knowledge tables.

This module deliberately has no HTTP surface.  It is a repeatable maintenance
operation that stores vectors next to the authoritative document/chunk rows;
the Retriever still hydrates final content from those rows.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.rag.embedding import create_embedding_provider
from app.rag.vector_store import KnowledgeEmbeddingIndexer


def index_knowledge(
    db: Session,
    *,
    embedding_provider: object | None = None,
) -> int:
    provider = embedding_provider or create_embedding_provider(
        settings.rag_embedding_provider,
        model_name=settings.rag_embedding_model,
        dimensions=settings.rag_embedding_dimensions,
        cache_dir=settings.rag_embedding_cache_dir,
    )
    result = KnowledgeEmbeddingIndexer(
        db,
        provider,  # type: ignore[arg-type]
        batch_size=settings.rag_embedding_batch_size,
    ).index()
    return result.indexed


def main() -> None:
    with SessionLocal() as db:
        count = index_knowledge(db)
        db.commit()
        print(f"indexed knowledge chunks: {count}")


if __name__ == "__main__":
    main()

"""Embedding index preparation for the knowledge tables.

This module deliberately has no HTTP surface.  It is a repeatable maintenance
operation that stores vectors next to the authoritative document/chunk rows;
the Retriever still hydrates final content from those rows.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.embedding import EmbeddingProvider, create_embedding_provider


def index_knowledge(
    db: Session,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> int:
    provider = embedding_provider or create_embedding_provider(
        settings.rag_embedding_provider,
        model_name=settings.rag_embedding_model,
        dimensions=settings.rag_embedding_dimensions,
        cache_dir=settings.rag_embedding_cache_dir,
    )
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument).join(
            KnowledgeDocument,
            KnowledgeChunk.document_id == KnowledgeDocument.id,
        )
    )
    indexed = 0
    for chunk, document in rows:
        text = f"{document.title} {document.category} {chunk.content}"
        chunk.embedding_model = provider.model_name
        chunk.embedding = provider.embed(text)
        indexed += 1
    return indexed


def main() -> None:
    with SessionLocal() as db:
        count = index_knowledge(db)
        db.commit()
        print(f"indexed knowledge chunks: {count}")


if __name__ == "__main__":
    main()

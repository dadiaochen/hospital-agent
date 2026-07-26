from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.embedding import DeterministicHashEmbedding, EmbeddingProvider, cosine_similarity
from app.rag.retrieval_schemas import RetrievalRequest, VectorMatch


class SQLAlchemyVectorBackend:
    """Portable vector search used until a native vector index is configured."""

    def __init__(
        self,
        db: Session,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        candidate_limit: int = 50,
    ) -> None:
        self._db = db
        self._embedding_provider = embedding_provider or DeterministicHashEmbedding()
        self._candidate_limit = candidate_limit

    def search(self, request: RetrievalRequest) -> list[VectorMatch]:
        query_vector = self._embedding_provider.embed(request.query)
        rows = self._db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .limit(self._candidate_limit)
        )
        matches: list[VectorMatch] = []
        for chunk, document in rows:
            vector = chunk.embedding
            if (
                not vector
                or chunk.embedding_model != self._embedding_provider.model_name
            ):
                vector = self._embedding_provider.embed(
                    f"{document.title} {document.category} {chunk.content}"
                )
            raw_score = cosine_similarity(query_vector, vector)
            score = round((raw_score + 1.0) / 2.0, 6)
            matches.append(
                VectorMatch(
                    document_id=document.id,
                    chunk_id=chunk.id,
                    score=score,
                )
            )
        matches.sort(key=lambda item: (-item.score, item.chunk_id))
        return matches[: request.limit]

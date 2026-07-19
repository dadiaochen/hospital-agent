from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag import RetrievalRequest, create_knowledge_retriever
from app.rag.embedding_provider import (
    EMBEDDING_DIMENSION,
    FastEmbedEmbeddingProvider,
)
from app.rag.vector_store import KnowledgeEmbeddingIndexer


class StaticEmbeddingProvider:
    model_name = "test/zh-embedding"
    dimension = EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self.passage_calls = 0

    def embed_query(self, text: str) -> list[float]:
        return [0.25] * self.dimension

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passage_calls += 1
        return [[float(index + 1) / 1000] * self.dimension for index, _ in enumerate(texts)]


@pytest.fixture()
def vector_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with testing_session() as session:
        document = KnowledgeDocument(
            id="doc-confirmation-vector",
            title="人工确认规则",
            category="human_confirmation",
            source="safety_policy:v1",
            content="关键动作必须等待用户明确确认。",
            safety_level="general",
        )
        session.add(document)
        session.flush()
        session.add(
            KnowledgeChunk(
                id="chunk-confirmation-vector",
                document_id=document.id,
                chunk_index=0,
                content=document.content,
                keywords=["人工确认", "关键动作"],
            )
        )
        session.commit()
        yield session


def test_fastembed_provider_is_lazy_and_does_not_create_cache_on_init(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"

    provider = FastEmbedEmbeddingProvider(cache_dir=cache_dir)

    assert provider._model is None
    assert cache_dir.exists() is False


def test_indexer_writes_embedding_metadata_and_skips_unchanged_content(
    vector_session: Session,
) -> None:
    provider = StaticEmbeddingProvider()
    indexer = KnowledgeEmbeddingIndexer(vector_session, provider, batch_size=1)

    first = indexer.index()
    vector_session.commit()
    second = indexer.index()

    chunk = vector_session.scalar(
        select(KnowledgeChunk).where(
            KnowledgeChunk.id == "chunk-confirmation-vector"
        )
    )
    assert chunk is not None
    assert first.scanned == 1
    assert first.indexed == 1
    assert second.indexed == 0
    assert second.skipped == 1
    assert provider.passage_calls == 1
    assert chunk.embedding is not None
    assert len(chunk.embedding) == EMBEDDING_DIMENSION
    assert chunk.embedding_model == provider.model_name
    assert len(chunk.embedding_content_hash or "") == 64
    assert chunk.embedded_at is not None


def test_indexer_rebuilds_embedding_when_authoritative_content_changes(
    vector_session: Session,
) -> None:
    provider = StaticEmbeddingProvider()
    indexer = KnowledgeEmbeddingIndexer(vector_session, provider)
    indexer.index()
    chunk = vector_session.get(KnowledgeChunk, "chunk-confirmation-vector")
    assert chunk is not None
    old_hash = chunk.embedding_content_hash

    chunk.content = "关键动作必须在执行前等待用户再次明确确认。"
    result = indexer.index()

    assert result.indexed == 1
    assert chunk.embedding_content_hash != old_hash
    assert provider.passage_calls == 2


def test_configured_vector_mode_falls_back_before_loading_model_on_sqlite(
    vector_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "must-not-be-created"
    monkeypatch.setattr(settings, "rag_vector_enabled", True)
    monkeypatch.setattr(settings, "rag_embedding_cache_dir", str(cache_dir))

    result = create_knowledge_retriever(vector_session).retrieve(
        RetrievalRequest(
            query="需要先得到本人同意",
            purpose="fallback_test",
            mode="hybrid",
        )
    )

    assert result.effective_mode == "keyword"
    assert result.fallback_used is True
    assert result.fallback_reason == (
        "vector_backend_error:VectorIndexUnavailableError"
    )
    assert cache_dir.exists() is False


def test_vector_settings_keep_low_memory_defaults() -> None:
    assert settings.rag_embedding_provider == "fastembed"
    assert settings.rag_embedding_model == "BAAI/bge-small-zh-v1.5"
    assert settings.rag_embedding_batch_size == 16
    assert settings.rag_vector_min_score == 0.35


def test_vector_migration_creates_pgvector_extension_and_512_dimension() -> None:
    project_root = Path(__file__).resolve().parents[2]
    migration_path = (
        project_root
        / "backend"
        / "alembic"
        / "versions"
        / "0003_lightweight_vector_rag.py"
    )
    migration_text = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "0003_lightweight_vector_rag"' in migration_text
    assert 'down_revision: Union[str, None] = "0002_add_agent_harness_trace_fields"' in migration_text
    assert 'op.execute("CREATE EXTENSION IF NOT EXISTS vector")' in migration_text
    assert "Vector(512)" in migration_text

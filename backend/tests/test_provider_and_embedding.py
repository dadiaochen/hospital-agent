from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models import KnowledgeChunk, KnowledgeDocument
from app.providers import ProviderRequest, build_mock_provider_registry
from app.rag.embedding import (
    DeterministicHashEmbedding,
    FastEmbedEmbedding,
    create_embedding_provider,
)
from app.rag.indexer import index_knowledge
from app.rag.retrieval_schemas import RetrievalRequest
from app.rag.vector_backend import SQLAlchemyVectorBackend


@pytest.fixture()
def knowledge_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    document = KnowledgeDocument(
        id="embedding-document",
        title="Confirmation SOP",
        category="human_confirmation",
        source="test-sop:v1",
        content="Confirmation is required before a reminder draft.",
        safety_level="general",
    )
    session.add(document)
    session.flush()
    session.add(
        KnowledgeChunk(
            id="embedding-chunk",
            document_id=document.id,
            chunk_index=0,
            content=document.content,
            keywords=["confirmation", "reminder"],
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_mock_provider_does_not_claim_sandbox_or_real_access() -> None:
    registry = build_mock_provider_registry()
    request = ProviderRequest(
        operation="list_departments",
        business_domain="preconsultation",
        provider_mode="sandbox",
        user_id="user-1",
        member_id="member-1",
    )

    response = registry.invoke("hospital", request)

    assert response.provider_mode == "sandbox"
    assert response.success is False
    assert response.degraded is True
    assert response.fallback_reason == "sandbox_adapter_not_configured"
    assert response.source_refs == []


def test_mock_provider_marks_simulated_sources_as_unverified() -> None:
    registry = build_mock_provider_registry()
    request = ProviderRequest(
        operation="list_departments",
        business_domain="preconsultation",
        provider_mode="mock",
        user_id="user-1",
        member_id="member-1",
    )

    response = registry.invoke("hospital", request)

    assert response.success is True
    assert response.source_refs[0].verified is False
    assert response.source_refs[0].source_metadata == {
        "provider_mode": "mock",
        "simulation": True,
    }


def test_indexer_persists_vectors_and_backend_reads_them(
    knowledge_session: Session,
) -> None:
    provider = DeterministicHashEmbedding(dimensions=16)

    assert index_knowledge(knowledge_session, embedding_provider=provider) == 1
    chunk = knowledge_session.get(KnowledgeChunk, "embedding-chunk")
    assert chunk is not None
    assert chunk.embedding_model == provider.model_name
    assert len(chunk.embedding or []) == 16

    matches = SQLAlchemyVectorBackend(
        knowledge_session,
        embedding_provider=provider,
    ).search(
        RetrievalRequest(
            query="reminder confirmation",
            purpose="test",
            mode="vector",
        )
    )
    assert matches
    assert matches[0].chunk_id == "embedding-chunk"


def test_fastembed_provider_is_lazy_and_keeps_embedding_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTextEmbedding:
        calls = 0

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            FakeTextEmbedding.calls += 1

        def embed(self, texts: list[str]):
            assert texts == ["hello"]
            return iter([[0.25, 0.75]])

    monkeypatch.setitem(
        __import__("sys").modules,
        "fastembed",
        SimpleNamespace(TextEmbedding=FakeTextEmbedding),
    )
    provider = FastEmbedEmbedding("test-model")

    assert provider.model_name == "test-model"
    assert provider.embed("hello") == [0.25, 0.75]
    assert provider.embed("hello") == [0.25, 0.75]
    assert FakeTextEmbedding.calls == 1


def test_unknown_embedding_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_embedding_provider"):
        create_embedding_provider(
            "unknown",
            model_name="model",
            dimensions=16,
        )

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.core.config import Settings
from app.core.database import Base
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag import (
    HybridRetriever,
    KeywordRetriever,
    RetrievalRequest,
    SQLAlchemyKnowledgeStore,
    VectorMatch,
    create_knowledge_retriever,
)


@pytest.fixture()
def knowledge_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with testing_session() as session:
        _seed_knowledge(session)
        yield session


class StaticVectorBackend:
    def __init__(self, matches: Sequence[VectorMatch]) -> None:
        self._matches = matches

    def search(self, request: RetrievalRequest) -> Sequence[VectorMatch]:
        return self._matches[: request.limit]


class BrokenVectorBackend:
    def search(self, request: RetrievalRequest) -> Sequence[VectorMatch]:
        raise TimeoutError("test vector timeout")


def test_keyword_retriever_returns_refill_source_versions_and_purpose(
    knowledge_session: Session,
) -> None:
    retriever = create_knowledge_retriever(knowledge_session, vector_enabled=False)

    result = retriever.retrieve(
        RetrievalRequest(
            query="refill prescription",
            purpose="refill_sop",
            mode="keyword",
        )
    )

    assert result.effective_mode == "keyword"
    assert result.evidence_present is True
    assert result.sources[0].category == "refill_sop"
    assert result.sources[0].source_id == "knowledge:doc-refill:chunk-refill"
    assert result.sources[0].document_version
    assert result.sources[0].chunk_version
    assert result.sources[0].purpose == "refill_sop"
    assert result.sources[0].score > 0


def test_keyword_retriever_returns_fixed_medical_safety_rule(
    knowledge_session: Session,
) -> None:
    retriever = create_knowledge_retriever(knowledge_session, vector_enabled=False)

    result = retriever.retrieve(
        RetrievalRequest(
            query="diagnose prescription safety boundary",
            purpose="safety_check",
        )
    )

    categories = {source.category for source in result.sources}
    assert "medical_safety" in categories
    assert all(source.purpose == "safety_check" for source in result.sources)


def test_keyword_retriever_matches_key_terms_inside_a_natural_chinese_query(
    knowledge_session: Session,
) -> None:
    retriever = create_knowledge_retriever(knowledge_session, vector_enabled=False)

    result = retriever.retrieve(
        RetrievalRequest(
            query="我现在胸痛，能不能直接把降压药加量？",
            purpose="safety_check",
        )
    )

    assert result.evidence_present is True
    assert result.sources[0].document_id == "doc-safety"
    assert result.sources[0].chunk_id == "chunk-safety"


def test_keyword_retriever_returns_no_evidence_for_unknown_query(
    knowledge_session: Session,
) -> None:
    retriever = create_knowledge_retriever(knowledge_session, vector_enabled=False)

    result = retriever.retrieve(
        RetrievalRequest(query="qzxvplm", purpose="test_no_source")
    )

    assert result.effective_mode == "keyword"
    assert result.evidence_present is False
    assert result.sources == []


def test_hybrid_retriever_falls_back_when_vector_backend_is_missing(
    knowledge_session: Session,
) -> None:
    store = SQLAlchemyKnowledgeStore(knowledge_session)
    retriever = HybridRetriever(
        KeywordRetriever(store),
        store,
        vector_enabled=True,
        vector_backend=None,
    )

    result = retriever.retrieve(
        RetrievalRequest(query="refill", purpose="refill_sop")
    )

    assert result.evidence_present is True
    assert result.effective_mode == "keyword"
    assert result.fallback_used is True
    assert result.fallback_reason == "vector_backend_unavailable"


def test_hybrid_retriever_falls_back_when_vector_backend_errors(
    knowledge_session: Session,
) -> None:
    retriever = create_knowledge_retriever(
        knowledge_session,
        vector_enabled=True,
        vector_backend=BrokenVectorBackend(),
    )

    result = retriever.retrieve(
        RetrievalRequest(query="safety boundary", purpose="safety_check")
    )

    assert result.evidence_present is True
    assert result.effective_mode == "keyword"
    assert result.fallback_used is True
    assert result.fallback_reason == "vector_backend_error:TimeoutError"


def test_hybrid_retriever_hydrates_vector_pointer_from_database(
    knowledge_session: Session,
) -> None:
    backend = StaticVectorBackend(
        [
            VectorMatch(
                document_id="doc-confirmation",
                chunk_id="chunk-confirmation",
                score=0.93,
            )
        ]
    )
    retriever = create_knowledge_retriever(
        knowledge_session,
        vector_enabled=True,
        vector_backend=backend,
    )

    result = retriever.retrieve(
        RetrievalRequest(
            query="semantic wording with no keyword overlap",
            purpose="human_confirmation",
        )
    )

    assert result.effective_mode == "hybrid"
    assert result.fallback_used is False
    assert result.sources[0].source_id == (
        "knowledge:doc-confirmation:chunk-confirmation"
    )
    assert result.sources[0].content.startswith("Critical actions")
    assert result.sources[0].matched_by == ("vector",)


def test_hybrid_retriever_deduplicates_same_chunk_and_preserves_match_modes(
    knowledge_session: Session,
) -> None:
    backend = StaticVectorBackend(
        [
            VectorMatch(
                document_id="doc-confirmation",
                chunk_id="chunk-confirmation",
                score=0.93,
            )
        ]
    )
    retriever = create_knowledge_retriever(
        knowledge_session,
        vector_enabled=True,
        vector_backend=backend,
    )

    result = retriever.retrieve(
        RetrievalRequest(query="confirmation", purpose="human_confirmation")
    )

    matching_sources = [
        source
        for source in result.sources
        if source.chunk_id == "chunk-confirmation"
    ]
    assert len(matching_sources) == 1
    assert matching_sources[0].matched_by == ("keyword", "vector")
    assert matching_sources[0].score == 1.0


def test_hybrid_retriever_rejects_unresolvable_vector_pointer(
    knowledge_session: Session,
) -> None:
    backend = StaticVectorBackend(
        [VectorMatch(document_id="doc-missing", chunk_id="chunk-missing", score=0.9)]
    )
    retriever = create_knowledge_retriever(
        knowledge_session,
        vector_enabled=True,
        vector_backend=backend,
    )

    result = retriever.retrieve(
        RetrievalRequest(query="refill", purpose="refill_sop")
    )

    assert result.evidence_present is True
    assert result.effective_mode == "keyword"
    assert result.fallback_used is True
    assert result.fallback_reason == "vector_sources_not_found"


def test_vector_feature_flag_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")

    assert Settings().rag_vector_enabled is True


def test_store_loads_only_requested_vector_sources(knowledge_session: Session) -> None:
    store = SQLAlchemyKnowledgeStore(knowledge_session)

    records = store.records_by_chunk_ids(["chunk-refill"])

    assert list(records) == ["chunk-refill"]
    assert records["chunk-refill"].document_id == "doc-refill"


def _seed_knowledge(session: Session) -> None:
    rows = [
        (
            "doc-refill",
            "chunk-refill",
            "Refill SOP",
            "refill_sop",
            "internal_sop:v1",
            "Refill workflow uses prescription evidence before confirmation.",
            ["refill", "prescription", "confirmation"],
            "general",
        ),
        (
            "doc-confirmation",
            "chunk-confirmation",
            "Human Confirmation Rule",
            "human_confirmation",
            "safety_policy:v1",
            "Critical actions must wait for explicit user confirmation.",
            ["confirmation", "draft"],
            "general",
        ),
        (
            "doc-safety",
            "chunk-safety",
            "Medical Safety Boundary",
            "medical_safety",
            "safety_policy:v1",
            (
                "The system does not diagnose, prescribe, or change a prescription. "
                "胸痛或加量请求必须转人工和医生处理。"
            ),
            ["safety", "boundary", "doctor", "胸痛", "加量"],
            "medical_boundary",
        ),
    ]
    for (
        document_id,
        chunk_id,
        title,
        category,
        source,
        content,
        keywords,
        safety_level,
    ) in rows:
        session.add(
            KnowledgeDocument(
                id=document_id,
                title=title,
                category=category,
                source=source,
                content=content,
                safety_level=safety_level,
            )
        )
        session.flush()
        session.add(
            KnowledgeChunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=0,
                content=content,
                keywords=keywords,
            )
        )
    session.commit()

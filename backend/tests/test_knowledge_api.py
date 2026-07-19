from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import KnowledgeChunk, KnowledgeDocument, User


@pytest.fixture
def knowledge_client() -> Iterator[TestClient]:
    # conftest.py 已把测试数据库切成内存 SQLite。
    # 每个测试先重建空表，保证测试之间互不污染。
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # DemoUser dependency 按手机号查用户，fixture 必须创建默认 demo user。
    session.add(
        User(
            id="user-knowledge-test",
            name="Knowledge Test User",
            phone="13800000001",
        )
    )

    # 固定 id 使 source_id 断言清晰、可重复。
    document = KnowledgeDocument(
        id="knowledge-document-test",
        title="人工确认规则",
        category="human_confirmation",
        source="safety_policy:v1",
        content="关键动作必须等待用户确认后执行。",
        safety_level="general",
    )
    chunk = KnowledgeChunk(
        id="knowledge-chunk-test",
        document_id=document.id,
        chunk_index=0,
        content="复诊申请、购药方案、提醒创建都必须等待用户确认。",
        keywords=["人工确认", "关键动作"],
    )
    session.add_all([document, chunk])
    session.commit()

    def override_get_db() -> Iterator[Session]:
        # 请求使用刚才写入测试数据的 Session。
        yield session

    # 用测试 Session 替换应用正常的 get_db dependency。
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client

    # yield 之后是清理阶段，恢复全局 app 并关闭数据库资源。
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_search_returns_a_traceable_knowledge_chunk(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "人工确认"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "source_id": "knowledge:knowledge-document-test:knowledge-chunk-test",
                "document_id": "knowledge-document-test",
                "chunk_id": "knowledge-chunk-test",
                "title": "人工确认规则",
                "category": "human_confirmation",
                "source": "safety_policy:v1",
                "safety_level": "general",
                "chunk_index": 0,
                "content": "复诊申请、购药方案、提醒创建都必须等待用户确认。",
                "keywords": ["人工确认", "关键动作"],
            }
        ]
    }


def test_category_filter_keeps_requested_category(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "确认", "category": "human_confirmation"},
    )

    assert response.status_code == 200
    assert all(
        item["category"] == "human_confirmation"
        for item in response.json()["items"]
    )


def test_no_match_returns_an_empty_list(knowledge_client: TestClient) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "绝对不会命中的词"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("params", [{}, {"q": "   "}])
def test_missing_or_blank_query_uses_uniform_validation_error(
    knowledge_client: TestClient,
    params: dict[str, str],
) -> None:
    response = knowledge_client.get("/api/knowledge/search", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_openapi_exposes_knowledge_search(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/knowledge/search" in response.json()["paths"]
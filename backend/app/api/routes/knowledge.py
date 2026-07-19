from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.knowledge import (
    KnowledgeSearchItemResponse,
    KnowledgeSearchQuery,
    KnowledgeSearchResponse,
)
from app.services.knowledge_read_service import KnowledgeReadService


# main.py 统一添加 /api，所以这里仅写 /knowledge。
router = APIRouter(prefix="/knowledge")


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Search knowledge chunks",
)
def search_knowledge(
    # FastAPI 从 query string 构造并校验这个 DTO。
    query: Annotated[KnowledgeSearchQuery, Query()],
    # 这两个对象由 dependencies.py 自动提供。
    db: DbSession,
    _demo_user: DemoUser,
) -> KnowledgeSearchResponse:
    # 下划线表示函数不读取 demo user，但认证入口依赖仍会执行。
    rows = KnowledgeReadService(db).search(
        query=query.q,
        category=query.category,
    )

    # 明确映射对外字段，避免直接暴露 ORM。
    return KnowledgeSearchResponse(
        items=[
            KnowledgeSearchItemResponse(
                source_id=f"knowledge:{document.id}:{chunk.id}",
                document_id=document.id,
                chunk_id=chunk.id,
                title=document.title,
                category=document.category,
                source=document.source,
                safety_level=document.safety_level,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                keywords=list(chunk.keywords or []),
            )
            for chunk, document in rows
        ]
    )

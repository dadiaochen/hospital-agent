from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeReadService:
    """只负责确定性知识查询，不处理 HTTP。"""

    def __init__(self, db: Session) -> None:
        # Session 从外部注入，Service 不自行创建连接。
        self.db = db

    def search(
        self,
        *,
        query: str,
        category: str | None,
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        # 防御性标准化，保证 Service 被其他入口调用时也行为稳定。
        normalized_query = " ".join(query.split()).lower()
        if not normalized_query:
            return []

        # 每行同时取 chunk 和它所属的 document。
        statement: Select[tuple[KnowledgeChunk, KnowledgeDocument]] = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeChunk.document_id == KnowledgeDocument.id,
            )
            # 固定排序让 API 和测试结果可重复。
            .order_by(KnowledgeDocument.category, KnowledgeChunk.chunk_index)
        )

        if category is not None:
            statement = statement.where(KnowledgeDocument.category == category)

        rows = list(self.db.execute(statement).all())
        matches: list[tuple[KnowledgeChunk, KnowledgeDocument]] = []

        for chunk, document in rows:
            # 将允许搜索的字段拼成统一小写文本。
            haystack = " ".join(
                [
                    document.title,
                    document.category,
                    document.source,
                    document.content,
                    chunk.content,
                    " ".join(chunk.keywords or []),
                ]
            ).lower()
            if _knowledge_matches(normalized_query, haystack):
                matches.append((chunk, document))

        return matches


def _knowledge_matches(query: str, haystack: str) -> bool:
    # 优先匹配完整短语，例如“人工确认”。
    if query in haystack:
        return True
    # 完整短语没命中，再按空格或 / 拆词，任一词命中即成功。
    tokens = [token for token in query.replace("/", " ").split() if token]
    return any(token in haystack for token in tokens)
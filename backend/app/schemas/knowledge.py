from pydantic import Field, field_validator

from app.schemas.common import ApiSchema


class KnowledgeSearchQuery(ApiSchema):
    # 先限制原始字符串长度，避免无限长查询进入 Service。
    q: str = Field(min_length=1, max_length=200)
    # category 不传时是 None；传入时必须满足长度限制。
    category: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        # split + join 会去掉首尾空白并压缩连续空白。
        normalized = " ".join(value.split())
        # q="   " 原始长度大于 1，但业务上仍是空查询，必须拒绝。
        if not normalized:
            raise ValueError("q must not be blank")
        return normalized

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("category must not be blank")
        return normalized


class KnowledgeSearchItemResponse(ApiSchema):
    # 稳定来源指针和数据库标识。
    source_id: str
    document_id: str
    chunk_id: str

    # 调用方真正需要看到的内容。
    title: str
    category: str
    source: str
    safety_level: str
    chunk_index: int
    content: str
    keywords: list[str]


class KnowledgeSearchResponse(ApiSchema):
    # 无结果也返回空 list，不返回 null。
    items: list[KnowledgeSearchItemResponse]
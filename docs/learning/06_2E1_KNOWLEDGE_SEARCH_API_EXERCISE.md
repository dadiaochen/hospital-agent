# 06. 实战：自己实现知识库搜索 API

你将独立补全 2E-1 最后一个读取资源：`GET /api/knowledge/search`。不要把现有 Agent 工具直接暴露成 HTTP endpoint；你的目标是练习完整 API 分层：DTO、service、route、错误响应、Swagger 和测试。

## 1. 完成后的接口契约

```text
GET /api/knowledge/search?q=人工确认&category=human_confirmation
```

| 参数 | 类型 | 规则 |
| --- | --- | --- |
| `q` | string | 必填，去空白后至少 1 个字符，最多 200 个字符。 |
| `category` | string | 可选，精确匹配 `KnowledgeDocument.category`。 |

成功时返回 `200`，即使没有命中也返回 `{ "items": [] }`。空 `q`、缺失 `q` 或过长 `q` 使用现有统一 `422 validation_error` 响应。它是只读检索，不需要 `member_id`，也不能修改知识库。

建议响应：

```json
{
  "items": [
    {
      "source_id": "knowledge:<document_id>:<chunk_id>",
      "document_id": "...",
      "chunk_id": "...",
      "title": "人工确认规则",
      "category": "human_confirmation",
      "source": "safety_policy:v1",
      "safety_level": "general",
      "chunk_index": 0,
      "content": "...",
      "keywords": ["人工确认", "关键动作"]
    }
  ]
}
```

`source_id` 很重要：它让将来的 RAG、ToolEvidence、RunTrace 和 FinalAnswer 能引用同一个可回溯来源。

## 2. 推荐改动顺序

### 第一步：写 Pydantic DTO

新建 `backend/app/schemas/knowledge.py`：

```python
from pydantic import Field

from app.schemas.common import ApiSchema


class KnowledgeSearchQuery(ApiSchema):
    q: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)


class KnowledgeSearchItemResponse(ApiSchema):
    source_id: str
    document_id: str
    chunk_id: str
    title: str
    category: str
    source: str
    safety_level: str
    chunk_index: int
    content: str
    keywords: list[str]


class KnowledgeSearchResponse(ApiSchema):
    items: list[KnowledgeSearchItemResponse]
```

为什么这里不用 ORM response？因为 API 的稳定契约是“可引用的知识块”，不是数据库对象。DTO 也防止以后给 KnowledgeDocument 新增内部字段时意外暴露。

### 第二步：在 service 层写只读查询

新建 `backend/app/services/knowledge_read_service.py`。使用 `select(KnowledgeChunk, KnowledgeDocument).join(...)`，按 `category` 和 `chunk_index` 排序。将 `q` 标准化为小写、压缩多余空格；匹配 `title`、`category`、`source`、document 内容、chunk 内容和 `keywords`。

你可以参考已有 `search_safety_knowledge_context` 的匹配思路，但不要直接复用它的整个返回对象：它是给 Agent tool 准备的 evidence wrapper，而这里应该返回 API 所需的行列表。把 `_matches(query, haystack)` 写成 service 内私有函数，并在没有命中时返回空列表而不是抛 404。

### 第三步：实现路由

新建 `backend/app/api/routes/knowledge.py`，使用：

```python
router = APIRouter(prefix="/knowledge")


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    query: Annotated[KnowledgeSearchQuery, Depends()],
    db: DbSession,
    demo_user: DemoUser,
) -> KnowledgeSearchResponse:
    ...
```

这里保留 `DemoUser` 依赖，确保所有 demo API 都走相同的运行入口；但不要错误地用它过滤全局的知识文档。route 只做 DTO 到 service 的转换和 response 映射，不要写 SQL。

最后在 `backend/app/api/router.py` 注册 router，并给它 `knowledge` tag。启动服务后在 `/docs` 中确认参数、response model 和 422 说明都可见。

### 第四步：写集成测试

在 `backend/tests/test_read_api.py` 或新建 `test_knowledge_api.py`，复用相同的 SQLite fixture 模式。至少写四个测试：

1. `q=确认` 能返回 seed 的确认规则，且每项有可用 `source_id`。
2. 加 `category=human_confirmation` 只返回该分类。
3. 不匹配的 `q` 返回 `200` 和空 `items`。
4. 缺失 `q` 或 `q=` 返回统一的 `422 validation_error`。

额外加分：验证 DTO 没有泄露 `KnowledgeDocument.content` 之外的 ORM 内部字段；验证多个关键词不会生成重复 chunk。

## 3. Review 清单

- API response 是否完全由 Pydantic DTO 描述？
- 路由里是否没有 `select`、`Session.query` 或匹配算法？
- `source_id` 是否稳定且含 document/chunk 标识？
- 无结果是否是空列表，而不是 404？
- 参数错误是否复用统一错误格式？
- 是否没有写入、没有 LLM、没有 ToolRegistry 调用、没有医疗建议？
- Swagger、API_SPEC、测试和学习笔记是否一起更新？

## 4. 验收命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_read_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-knowledge
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest-all
```

完成后，把你的 diff 和测试结果留在 `codex/2e-1-read-apis` 分支；回来 review 时重点检查你是否守住了 API / service / schema 的分层，而不只是接口能返回数据。

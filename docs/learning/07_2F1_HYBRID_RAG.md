# 07：从关键词检索到 Hybrid RAG

本章建议在完成 06 的知识搜索 API 后阅读。06 教你完成一条 HTTP 链路；07 解释如何把底层知识查询抽象成 Agent、Tool 和 API 都能复用的 Retriever。

## 1. 先分清四个概念

1. **知识库**：PostgreSQL 中经过准备和审核的 document/chunk。
2. **关键词检索**：比较 query 与标题、分类、关键词和正文是否匹配。
3. **向量检索**：把语义相近的 query 和 chunk 排在一起，即使用词不完全相同也可能命中。
4. **RAG**：先检索来源，再把来源提供给后续生成或规则流程；RAG 本身不等于 LLM。

本阶段没有实现真实向量模型，只定义“将来向量后端必须怎样被调用”的协议。这样可以先测试架构边界，不让外部模型服务阻塞基础开发。

## 2. 按顺序阅读代码

### 第一步：看数据库事实长什么样

打开 `backend/app/models/knowledge.py`：

- `KnowledgeDocument` 保存标题、分类、来源、全文和安全级别。
- `KnowledgeChunk` 保存分块正文、顺序和关键词。
- document 是管理和审核单位，chunk 是检索和放入上下文的最小单位。

### 第二步：看 Pydantic 契约

打开 `backend/app/rag/retrieval_schemas.py`，依次读：

- `RetrievalRequest`：调用方必须给什么。
- `VectorMatch`：为什么向量后端只能给 ID 和 score。
- `RetrievedChunk`：为什么最终结果必须带来源、版本和用途。
- `RetrievalResult`：为什么要同时记录请求模式、实际模式和降级原因。

`extra="forbid"` 的作用是拒绝契约未声明字段。它能防止未来向量适配器偷偷把不受信任正文混入结果。

### 第三步：看数据库适配

打开 `backend/app/rag/retriever.py` 中的 `SQLAlchemyKnowledgeStore`：

```python
select(KnowledgeChunk, KnowledgeDocument).join(...)
```

这表示 SQLAlchemy 生成一条联表查询，同时得到 chunk 和所属 document。`_to_record` 把 ORM 对象转成内部不可变 `KnowledgeRecord`，后续排序逻辑不需要继续依赖 ORM 状态。

### 第四步：看关键词评分

`KeywordRetriever.retrieve` 会：

1. 读取所有知识记录。
2. 调用 `_keyword_score`。
3. 丢弃分数为零的记录。
4. 转为 `RetrievedChunk`。
5. 用稳定规则排序并截取 `limit`。

这里的 `score` 是工程上的相关性排序值。它不是医疗正确率，也不能作为诊断或自动执行的依据。

### 第五步：看 Hybrid 与 fallback

`HybridRetriever.retrieve` 先拿关键词结果，再判断：

```python
if request.mode == "keyword" or not self._vector_enabled:
    return keyword_result
```

`enabled` 是布尔功能开关。默认 `false` 让没有 Embedding 和向量数据库的开发环境仍能运行。

当开关开启时，向量后端返回 `document_id/chunk_id/score`。`_hydrate_vector_sources` 用这些 ID 回数据库取正式正文；找不到、关系错配或后端报错都会回退关键词结果。这里的关键原则是：向量系统负责“找谁”，权威数据库负责“内容是什么”。

## 3. 看 Tool 如何复用 Retriever

打开 `backend/app/services/agent_tool_query_service.py` 的 `search_safety_knowledge_context`。它不再自己实现关键词循环，而是：

```python
result = create_knowledge_retriever(db).retrieve(
    RetrievalRequest(query=query, purpose="safety_and_workflow_grounding")
)
```

service 负责把内部 `RetrievalResult` 转成现有 Tool 输出结构；ToolRegistry 仍负责角色、schema、错误和 trace。Retriever 不应该知道 FastAPI、当前 Agent 角色或 HTTP 状态码。

## 4. 怎样阅读测试

打开 `backend/tests/test_hybrid_rag.py`，对每条测试回答：

1. Arrange 创建了哪些 document/chunk 或 fake vector backend？
2. Act 传入什么 query、purpose、mode？
3. Assert 在保护哪条设计规则？
4. 如果删掉这一规则，Agent 可能收到什么错误证据？

重点阅读三类失败测试：向量后端超时、来源 ID 不存在、无关键词来源。它们证明系统在依赖失败时不会让模型凭记忆补写医疗事实。

## 5. 你应该能讲清的问题

- 为什么关键词检索比向量检索更适合作为可启动基线？
- 为什么向量后端不应直接提供最终医疗正文？
- `category` 与 `purpose` 分别属于文档还是当前 run？
- `requested_mode` 和 `effective_mode` 为什么可能不同？
- 为什么 `score=0.93` 不能写成“93% 医疗正确率”？
- Retriever、Service、Tool 与 FastAPI Router 的职责怎样分开？

## 6. 简历表达

完成并合入主线后，可以写“设计 Hybrid RAG Retriever，以关键词检索作为稳定基线，通过来源指针回填权威正文，并实现可追踪的向量服务降级”。

不能写“已接入生产向量数据库”“检索准确率达到某数值”或“医疗答案正确率 93%”，因为本阶段没有真实 Embedding provider、线上数据集或医疗评测报告。

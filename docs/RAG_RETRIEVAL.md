# RAG 检索设计

## 1. 目标与边界

2F-1 的目标是把已有知识库关键词查询整理成可替换、可测试、可追踪的 Retriever。它不调用 LLM，不生成 Embedding，不连接真实向量数据库，不抓取互联网医疗内容，也不新增 ORM 字段或 Alembic migration。

关键词检索必须始终可用。向量检索只是可选的召回增强，不能成为项目启动或医疗安全规则查询的单点依赖。

## 2. 契约

`RetrievalRequest` 描述一次检索：

| 字段 | 含义 |
| --- | --- |
| `query` | 用户或 Agent 需要查找的文本。 |
| `purpose` | 本次 run 为什么需要这些来源，例如 `safety_check` 或 `refill_sop`。 |
| `mode` | `keyword` 或 `hybrid`；默认 `hybrid`，但功能开关关闭时实际只跑关键词。 |
| `limit` | 最多返回的 chunk 数，范围 1 到 50。 |

`RetrievedChunk` 返回稳定 `source_id`、document/chunk ID、两级版本、文档分类、来源、安全级别、正文、关键词、排序分数、用途和 `matched_by`。

`category` 是文档固有分类；`purpose` 是本次任务使用它的原因。`score` 只表示检索相关性，不代表医疗正确率、疾病概率或 Agent 动作权限。

`RetrievalResult` 同时记录：

- `requested_mode`：调用方希望采用的模式。
- `effective_mode`：本次实际成功使用的模式。
- `fallback_used` / `fallback_reason`：是否发生降级及原因。
- `evidence_present`：是否存在可回溯来源。

## 3. 运行流程

```text
RetrievalRequest
  -> SQLAlchemyKnowledgeStore
  -> KeywordRetriever (always available)
  -> optional VectorSearchBackend
  -> hydrate vector document_id/chunk_id from PostgreSQL
  -> deduplicate by chunk_id
  -> deterministic ranking
  -> RetrievalResult
```

关键词检索读取文档标题、分类、来源、正文、chunk 正文与关键词，按 query token 命中位置计算归一化排序分数。英文/数字按连续词处理；连续中文保留完整片段并补充双字词，使“我现在胸痛”可以命中“胸痛”安全关键词，同时不依赖外部分词服务。排序使用分数、分类、chunk index 和 chunk ID 作为稳定 tie-breaker，同一数据库快照和请求会得到相同顺序。

向量后端只能返回 `VectorMatch(document_id, chunk_id, score)`。Retriever 不信任它提供正文；必须从 PostgreSQL 重新加载，且 document/chunk 关系一致才会进入结果。这保证最终内容仍来自已审核知识表。

两路命中同一 chunk 时按 `chunk_id` 去重，`matched_by` 保存 `keyword` 与 `vector`，不会把重复正文两次放入 Agent context。

## 4. 功能开关与降级

默认配置：

```env
RAG_VECTOR_ENABLED=false
```

| 场景 | effective mode | fallback |
| --- | --- | --- |
| 功能开关关闭 | `keyword` | 否，属于预期配置。 |
| 显式请求 keyword | `keyword` | 否。 |
| 开关开启且向量后端成功 | `hybrid` | 否。 |
| 开关开启但没有后端 | `keyword` | `vector_backend_unavailable`。 |
| 向量后端异常 | `keyword` | `vector_backend_error:<type>`。 |
| 向量指针无法从数据库回填 | `keyword` | `vector_sources_not_found`。 |

降级不等于静默忽略错误。关键词结果继续服务当前任务，原因则进入 Tool 输出和后续 trace，供测试、Evaluator 与运维判断向量链路质量。

## 5. 与 API、Tool 和 Agent 的关系

- `Retriever` 是内部 RAG 接口，不是 HTTP endpoint。
- `search_safety_knowledge` Tool 通过 Retriever 获取已审核知识，并继续经过 Tool Registry 的 schema、角色与 trace 门禁。
- 学习者正在实现的 `GET /api/knowledge/search` 仍需要 Router、API DTO 和 HTTP 错误语义；它可以在后续整合时调用 Retriever。
- Agent 只能使用返回的来源指针和正文；没有 evidence 时不能让模型补写医疗规则。

## 6. 验证

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q --basetemp=.tmp\pytest-rag
```

专项测试覆盖续方 SOP、安全边界、空命中、功能开关、后端缺失、后端超时、来源回填、错误来源拒绝、两路去重和现有 DB Tool 兼容性。

## 7. 尚未实现

- Embedding provider 和模型调用。
- pgvector 或独立向量数据库。
- 文档摄取、切块、审核和索引重建流水线。
- 真实线上检索质量指标和医疗效果评估。
- 互联网医疗知识自动抓取或模型生成内容写回。

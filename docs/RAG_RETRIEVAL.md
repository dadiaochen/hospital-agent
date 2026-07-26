# RAG 知识与证据层设计

## 1. 定位

RAG 是三条业务线共用的知识与证据层，不是独立问答功能，也不负责诊断、开方或修改医生处方。它主要解决四类问题：

1. **降低幻觉**：医疗流程、安全规则和指标解释优先来自已审核知识，不完全依赖模型记忆。
2. **知识可更新**：更新知识文档、版本和索引即可调整规则，不需要重新训练模型。
3. **答案可追溯**：关键解释保留 `SourceRef`、文档版本、chunk 和检索方式。
4. **方便评测**：`EvaluatorAgent` 可以检查应检索的知识是否命中、回答是否被来源覆盖。

没有 DB、业务 Provider 或 RAG 来源时，Agent 不得编造病史、处方、库存、医疗规则或检查结论。

## 2. 当前实现边界

当前已经实现的是可替换、可测试、可降级的 Retriever 基线：

- PostgreSQL 中的 `knowledge_documents`、`knowledge_chunks` 是知识正文的权威存储。
- 关键词检索始终可用。
- 向量检索由功能开关控制；默认 provider 是不联网的确定性 hash 向量，保证 CI 和无模型环境可回放。
- 可选 `FastEmbedEmbedding` 使用 FastEmbed/ONNX Runtime 生成真实语义向量，模型按需加载，缓存目录由 `FASTEMBED_CACHE_PATH` 控制。
- 向量后端只返回 document/chunk 指针，正文必须回到 PostgreSQL 校验并加载。
- 关键词和向量结果按 `chunk_id` 去重，保留实际 `matched_by`。
- 检索模式、降级原因和来源指针可以进入 Tool 输出与 RunTrace。

当前的关键词优先只是过渡实现。最终目标架构是：

- 使用 Embedding 模型生成向量，以语义向量检索承担主要召回。
- 关键词检索用于药品名、检查指标、标准编号、明确安全词和短查询等精确匹配场景。
- 普通自然语言问题默认采用混合检索，合并向量与关键词结果后执行去重、重排和来源校验。
- Embedding 服务、向量索引或向量检索后端不可用时，自动降级到关键词检索，并记录降级原因。

当前仍未实现：

- pgvector 原生近邻索引；当前 `SQLAlchemyVectorBackend` 为可移植的数据库候选扫描，适合本地小规模知识库。
- 文档摄取、审核、自动切块和版本发布流水线。
- 六项新增 RAG 指标的批量评测报告。
- 互联网医疗知识自动抓取或模型生成内容写回。

## 3. 检索契约

`RetrievalRequest` 描述一次检索：

| 字段 | 含义 |
| --- | --- |
| `query` | 用户问题或 Agent 需要查找的文本。 |
| `purpose` | 本次检索的业务目的，例如安全规则或报告指标解释。 |
| `mode` | `keyword`、`vector` 或 `hybrid`；最终版本普通自然语言问题默认请求 `hybrid`，当前实现受功能开关控制。 |
| `limit` | 最多返回的 chunk 数，范围 1 到 50。 |

`RetrievedChunk` 返回稳定 `source_id`、document/chunk ID、文档版本、分类、正文、关键词、排序分数、用途和 `matched_by`。`score` 只表示检索相关性，不代表疾病概率、医疗正确率或动作权限。

`RetrievalResult` 记录：

- `requested_mode`：调用方希望使用的模式。
- `effective_mode`：本次实际成功使用的模式。
- `fallback_used`、`fallback_reason`：是否降级及原因。
- `evidence_present`：是否找到可回溯来源。

## 4. SourceRef

Agent 状态、工具结果、最终回答和评测统一使用 `SourceRef`：

```json
{
  "source_id": "knowledge:doc-001:chunk-003:v2",
  "source_type": "knowledge_base",
  "document_id": "doc-001",
  "document_version": "v2",
  "chunk_id": "chunk-003",
  "retrieval_mode": "keyword",
  "provider": "postgresql_knowledge_store",
  "member_id": "member-001",
  "verified": true,
  "source_metadata": {
    "simulation": false
  }
}
```

约束：

- 医疗文档和知识库来源必须带 `document_id`、`document_version` 和 `retrieval_mode`。
- `member_id` 用于成员隔离；公共知识可以为空，患者事实不得为空。
- `agent_inference` 不能标记为 `verified=true`。
- 摘要、上下文压缩和多 Agent 传递不能丢失 `source_id`。
- 最终回答中的事实、规则和解释性内容应可区分；医疗结论没有来源时必须拒绝补写或转人工。

## 5. 运行流程

```text
RetrievalRequest
  -> Query Analyzer
  -> VectorSearchBackend as primary semantic recall
  -> KeywordRetriever for exact recall and fallback
  -> PostgreSQL source hydration and validation
  -> deduplicate by chunk_id
  -> rerank and deterministic tie-breaking
  -> RetrievedChunk + SourceRef
  -> ToolEvidence / ContextEnvelope / FinalAnswer
```

当前 `HybridRetriever` 已支持三种模式：`keyword` 直接精确检索，`vector` 只返回向量命中的来源指针，`hybrid` 合并两路结果并按稳定规则去重排序。默认确定性 provider 不是语义模型，只用于离线契约、索引和降级测试；配置 FastEmbed 后，向量分数才具有语义相似度含义。无论使用哪种 provider，正文都必须从权威知识表回填。

关键词检索读取标题、分类、来源、正文和关键词，按 query token 命中位置计算归一化分数。连续中文保留完整片段并补充双字词，使安全关键词不依赖外部分词服务。最终排序结合向量相似度、关键词相关性、文档权威级别、版本状态和业务目的，并使用 chunk index 与 chunk ID 作为稳定 tie-breaker。

## 6. 三条业务线中的 RAG

| 业务线 | RAG 主要内容 | 不能替代的来源 |
| --- | --- | --- |
| 智能预问诊与分级导诊 | 就诊准备、科室范围、危险信号和转人工规则 | 用户症状原文、医院实时科室和医生排班 |
| 家庭医生、慢病与用药履约 | 慢病随访 SOP、药品说明书、安全规则、复诊与购药流程 | 医生处方、患者档案、药店库存和订单状态 |
| 报告解读与长期健康档案 | 指标释义、报告结构、复查准备和健康档案规则 | 原始报告、医生结论和检查机构数据 |

业务事实优先级：

```text
医疗文档或医生确认
  > 结构化业务数据
  > 用户明确陈述
  > 已审核知识库
  > Agent 推断
```

RAG 命中不能覆盖更高优先级事实，也不能把通用知识解释成针对患者的诊断结论。

## 7. 当前阶段配置与最终降级策略

默认配置：

```env
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_PROVIDER=deterministic
RAG_EMBEDDING_MODEL=deterministic-hash-v1
RAG_EMBEDDING_DIMENSIONS=384
FASTEMBED_CACHE_PATH=E:\\project_code\\hospital\\var\\fastembed
```

| 场景 | effective mode | fallback |
| --- | --- | --- |
| 功能开关关闭 | `keyword` | 否，属于预期配置。 |
| 显式请求 keyword | `keyword` | 否。 |
| 开关开启且向量后端成功 | `hybrid` | 否。 |
| 开关开启但没有后端 | `keyword` | `vector_backend_unavailable`。 |
| 向量后端异常 | `keyword` | `vector_backend_error:<type>`。 |
| 向量指针无法从数据库回填 | `keyword` | `vector_sources_not_found`。 |
| embedding provider 未安装或模型下载失败 | `keyword` | `vector_backend_error:RuntimeError` 或对应异常类型。 |

降级必须显式进入检索结果、ToolResult 和 RunTrace。关键词结果可以继续服务当前任务，但医疗安全规则没有命中时不得用模型记忆兜底。

`RAG_VECTOR_ENABLED=true` 是当前完整后端的正常配置，但“开启向量链路”不等于“已下载语义模型”。无模型环境使用 deterministic provider；需要真实语义召回时切换 `RAG_EMBEDDING_PROVIDER=fastembed`。普通自然语言查询使用 `hybrid`，药品名、指标名和标准编号可使用 `keyword`，向量链路异常时记录原因并降级。

## 8. Embedding 索引操作

知识正文仍由 `knowledge_documents` 和 `knowledge_chunks` 保存。索引器把 `title + category + chunk.content` 交给当前 embedding provider，并将 `embedding_model` 与向量写回 chunk；检索时如果版本或模型不匹配，会重新计算而不会把旧向量当成新事实。

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.rag.indexer
```

该命令需要已运行 PostgreSQL/SQLite 配置和已执行 seed；它不是 HTTP API，也不会调用 LLM。FastEmbed 第一次运行会下载模型，建议把缓存放在 `E:\project_code\hospital\var\fastembed`。

## 9. RAG 评测指标

本阶段定义指标契约，不宣称已经跑出线上结果。分母为零时记为 `N/A`，不能按 100% 处理。

| 指标 | 计算口径 |
| --- | --- |
| Knowledge Retrieval Recall | `命中的期望知识点数 / ExpectedCase 标注的应检索知识点数` |
| Evidence Coverage | `有有效 SourceRef 支撑的关键事实数 / 回答中的关键事实总数` |
| 引用正确率 | `来源确实支持对应陈述的引用数 / 全部引用数` |
| 无来源医疗结论率 | `没有有效来源的医疗结论数 / 全部医疗结论数`，目标为 0 |
| 检索降级率 | `fallback_used=true 的检索次数 / 全部检索次数` |
| RAG 命中后任务完成率 | `RAG 命中且任务成功的 run 数 / RAG 命中的 run 数` |

评测需要同时读取 `ExpectedCase`、`RetrievalResult`、`SourceRef`、`FinalAnswer` 和 `RunTrace`。`LLM-as-a-Judge` 只能作为辅助评审，引用正确性和无来源医疗结论必须优先采用规则、标注与人工抽查。

## 10. 验证

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q -p no:cacheprovider --basetemp=.tmp\pytest-rag
python -m pytest backend\tests\test_provider_and_embedding.py -q -p no:cacheprovider --basetemp=$env:TEMP\hospital-pytest-rag-provider
```

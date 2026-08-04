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
- 向量检索由功能开关控制；deterministic hash provider 和 FastEmbed 都实现同一个 canonical `EmbeddingProvider` 契约，保证 CI 和无模型环境可回放。
- `FastEmbedEmbeddingProvider` 使用 FastEmbed/ONNX Runtime 生成真实语义向量，模型按需加载，缓存目录由配置控制。
- PostgreSQL 使用 `pgvector` 的 HNSW cosine index；索引器按模型、维度、schema version 和内容 hash 跳过未变化 chunk，查询只接受具有完整索引元数据的向量。
- 向量后端只返回 document/chunk 指针，正文必须回到 PostgreSQL 校验并加载。
- 关键词和向量结果按 `chunk_id` 去重，保留实际 `matched_by`。
- 检索模式、降级原因和来源指针可以进入 Tool 输出与 RunTrace。

当前运行时已经按向量优先目标接入；关键词仍是精确匹配和故障兜底。架构约束是：

- 使用 Embedding 模型生成向量，以语义向量检索承担主要召回。
- 关键词检索用于药品名、检查指标、标准编号、明确安全词和短查询等精确匹配场景。
- 普通自然语言问题默认采用混合检索，合并向量与关键词结果后执行去重、重排和来源校验。
- Embedding 服务、向量索引或向量检索后端不可用时，自动降级到关键词检索，并记录降级原因。

当前仍未实现：

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
- `retrieval_provider`：`keyword`、`pgvector` 或 `keyword+pgvector`。
- `embedding_model`、`embedding_dimension`、`embedding_schema_version`：向量索引契约，关键词降级时可以为空。

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

当前 `HybridRetriever` 已支持三种模式：`keyword` 直接精确检索，`vector` 只返回向量命中的来源指针，`hybrid` 使用 Reciprocal Rank Fusion（RRF）合并两路 rank。默认确定性 provider 不是语义模型，只用于离线契约、索引和降级测试；配置 FastEmbed 后，向量分数才具有语义相似度含义。无论使用哪种 provider，正文都必须从权威知识表回填。

RRF 使用 `1 / (60 + rank)` 累加两路贡献。`keyword_score` 和 `vector_score` 被保留用于排障，但不跨量纲比较；最终 hybrid 排序只读取 `rrf_score`，相同分数再使用分类、chunk index 和 chunk ID 稳定排序。每条来源同时保留 `keyword_rank`、`vector_rank`、文档版本、分块版本和 embedding schema。

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
RAG_EMBEDDING_DIMENSIONS=512
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
| 向量指针版本或 embedding schema 过期 | `keyword` | `vector_source_version_mismatch`。 |
| 部分向量来源过期 | `hybrid`/`vector` | 忽略旧来源并记录 `stale_vector_sources_ignored`。 |
| embedding provider 未安装或模型下载失败 | `keyword` | `vector_backend_error:RuntimeError` 或对应异常类型。 |

降级必须显式进入检索结果、ToolResult 和 RunTrace。关键词结果可以继续服务当前任务，但医疗安全规则没有命中时不得用模型记忆兜底。

`RAG_VECTOR_ENABLED=true` 是当前完整后端的正常配置，但“开启向量链路”不等于“已下载语义模型”。无模型环境使用 deterministic provider；需要真实语义召回时切换 `RAG_EMBEDDING_PROVIDER=fastembed`。普通自然语言查询使用 `hybrid`，药品名、指标名和标准编号可使用 `keyword`，向量链路异常时记录原因并降级。

## 8. Embedding 索引操作

知识正文仍由 `knowledge_documents` 和 `knowledge_chunks` 保存。索引器把 `title + category + chunk.content + keywords` 交给当前 embedding provider，并将 `embedding_model`、`embedding_content_hash` 和 `embedded_at` 写回 chunk；hash 同时包含模型名、维度和 `rag-embedding-v1`，契约不匹配时会重新计算而不会把旧向量当成新事实。PostgreSQL 的 `0006_vector_search_index` 迁移创建 HNSW cosine index，SQLite 只用于离线降级测试。

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

4D-B 最终报告分别运行 keyword、PostgreSQL pgvector、hybrid RRF 和向量故障后的关键词降级，并计算 Recall@3、Recall@5、MRR、引用正确率、无答案拒答率和过期来源拒绝率。当前 12 条 `KeywordRetriever` 本地结果不能替代 Docker pgvector 指标；4D-B2.3 已接入 FinalClaim，4D-B2.4 已生成待审核的 v2 Query，B2.5 的 `rag_grader` 已能在内存 projection 上检查 source coverage 和 stale source 拒绝，但不能替代真实索引召回。执行方案见 [Agent 评测与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。

医疗知识 RAG 与个人状态严格隔离：系统不建立个人健康向量记忆，不把完整聊天、处方、报告原值、过敏史或药箱库存嵌入知识库。此类事实每次 run 从业务数据库或 Provider 重新读取；RAG 只检索经过版本管理的通用医疗规则、流程和解释资料。

4B 任务五的 Router 和任务六的 deterministic 领域编排只输出固定领域、步骤和来源需求契约，不执行检索；当前 4D-B4 的运行时 Triage/Medication/Report Agent 会通过 Tool Registry 的 `search_safety_knowledge` 或 `search_business_knowledge` 获取真实 RAG 结果，并把 `SourceRef` 带回 `AgentTaskResult`。任何没有 `SourceRef` 的工作流结果仍不能被当作医学事实。

4B 任务七不改变 RAG 的召回和 embedding 规则。它只把已有 `SourceRef`、RAG source pointer 和安全决策带入 Action Policy/Final Output Safety 边界；没有有效来源时，最终答案仍不能把模型解释升级为医疗事实。任务八已将 `SourceRef` 的 source id、member 和版本指针纳入 PostgreSQL 权威 checkpoint；Redis 只缓存这些指针的短期投影，恢复后仍需按当前成员和来源版本校验，不能把个人健康数据写入知识 namespace。

## 4D-B2.6 真实集成边界

4D-B2.6 增加了真实评测适配边界，但没有把个人医疗事实写入知识库：`PostgresV2Materializer` 在 PostgreSQL 事务中按 case 创建临时数据，`IntegrationIdentityMap` 显式映射 benchmark 身份，`ScopedPostgresRetriever` 只允许当前 case 的 source alias，`ScopedProviderSandbox` 记录 Provider attempt 和故障注入结果，`UnifiedHealthGraphIntegrationExecutor` 执行真实业务图并冻结 `RunTrace`。

因此，真实集成报告可以证明数据、RAG、Provider 和业务图的连接方式，但仍不能把单个开发样例外推成 300/1200 数据集的最终质量指标。A/B/C/D 当前已提供 deterministic preview；正式消融必须使用审核后的 gold、同一版本的 PostgreSQL 物化和完整 v2 runner。Docker 19/19 回归通过只证明启动、迁移、seed、pgvector、API、Redis 回源和并发确认链路可运行。

## 10. 验证

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q -p no:cacheprovider --basetemp=.tmp\pytest-rag
python -m pytest backend\tests\test_provider_and_embedding.py -q -p no:cacheprovider --basetemp=$env:TEMP\hospital-pytest-rag-provider
```

任务十已经实现 RRF、向量版本三元组校验和来源决策字段。定向测试证明高 raw vector score 不会压过多路一致命中，旧文档/分块版本不会被当前 PostgreSQL 正文重新包装为有效来源。该结果是排序与版本契约回归，不代表真实语义模型 Recall@K 已达到某个数值。

任务十一在 4 条固定 RAG case 上复用同一 ranked source list，三种策略的 Recall@3 为 0.7500、Recall@5 为 1.0000、引用正确率为 1.0000。它证明指标计算、引用集合和公平性约束可重复，不代表真实 FastEmbed/pgvector 语义召回率。任务十二已在 Docker PostgreSQL 中验证 4 个知识 chunk 的 512 维 deterministic 向量、pgvector 扩展和索引数据；这证明数据链路可用，不代表语义质量。

任务十二验收使用：

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

完整结果见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。

UX-04 不改变 RAG 检索或来源版本校验；历史咨询和确认页面只展示必要的用户可读整理结果，原始 `source_id`、检索排名和工具来源继续留在冻结产物与审计链路中。

UX-06 同样不新增 RAG 检索链路：报告详情先展示报告自身的版本化来源指针，只有契约明确提供的来源才可用于页面解释。页面不把来源内部 ID、检索排名或模型记忆展示给用户；没有来源或来源未核对时必须降级为提示，不得生成无依据的医疗结论。

## 用户端 UX-08 入口边界

知识检索仍由 Agent/RAG 内部链路按既有来源和版本规则执行，但不再从公共首页直接进入。`/knowledge` 仅保留兼容跳转到 `/agent`；这不会删除 RAG 能力，也不会把原始来源、排名或检索参数暴露给用户。报告详情继续只展示契约允许的报告来源。

## 用户端 UX-09 RAG 边界

UX-09 没有新增检索、索引、embedding 或知识写入。页面隐藏 `source_id`、排名和工具来源标识，但这些指针继续保留在冻结运行产物和审计链路中；前端不根据模型记忆补造来源，也不把 RAG 结果直接转换为诊断或治疗建议。

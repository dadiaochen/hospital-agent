# RAG 知识与证据层设计

## 1. 作用与边界

RAG 为分诊、慢病用药和报告解读提供版本化知识证据，不负责诊断、开方或修改医生处方。处方、过敏史、报告和药箱库存属于业务事实，每次从数据库或 Provider 读取，不进入知识向量库。

没有数据库、Provider 或 RAG 来源时，Agent 不得编造病史、库存、处方、医疗规则或检查结论。

## 2. 当前检索 Pipeline

```text
Query
  -> Query 分析
  -> FastEmbed
  -> PostgreSQL pgvector HNSW 向量召回
  -> 关键词精确召回
  -> RRF 融合与 Chunk 去重
  -> 活动版本前置过滤
  -> PostgreSQL 来源与版本校验
  -> Query 实体证据门
  -> 1～2 个直接来源
  -> Model Gateway
  -> FinalClaim 与 SourceRef 校验
```

- 向量检索负责语义召回，关键词检索补充药品名、指标名、规则编号和短查询。
- 两路结果按 rank 做 RRF 融合，不比较不同量纲的原始分数。
- 活动版本过滤发生在候选截断前，避免旧版本占用 Top-K。
- 轻量 rerank 和额外去重做过单变量实验，因召回回退或无变化，没有进入当前配置。
- 向量后端只返回文档与 Chunk 指针，正文和版本必须回 PostgreSQL 校验。
- 无实体证据时不向模型提供伪证据，回答应明确无法确认。

## 3. 来源契约

每条来源至少保留：

| 字段 | 含义 |
| --- | --- |
| `source_id` | 稳定来源编号 |
| `document_id` / `chunk_id` | 文档和切片位置 |
| `document_version` | 当前知识版本 |
| `retrieval_mode` | keyword、vector 或 hybrid |
| `matched_by` | 实际命中方式 |
| `verified` | 是否已回权威库校验 |
| `member_id` | 个人事实的成员作用域；公共知识可为空 |

上下文压缩、多 Agent 传递、Task Checkpoint 和最终回答不能丢失 `source_id`。Agent 推断不能标记为已验证来源。

## 4. 配置与降级

```env
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_PROVIDER=fastembed
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_DIMENSIONS=512
RAG_EMBEDDING_DEVICE=cpu
FASTEMBED_CACHE_PATH=E:\\project_code\\hospital\\var\\fastembed
```

`RAG_EMBEDDING_DEVICE` 支持 `cpu`、`cuda` 和 `auto`。显式选择 CUDA 时，运行前校验 ONNX session 是否包含 `CUDAExecutionProvider`，避免配置写了 GPU 但实际静默使用 CPU。GPU 只加速本地 Embedding；HNSW 在 PostgreSQL 执行，远端 LLM 不使用本机 GPU。

向量模型、索引或后端不可用时降级到关键词检索，并把原因写入 RetrievalResult、ToolResult 和 RunTrace。关键词兜底不能替代缺失的医疗安全证据。

## 5. 性能与一致性

单次批量运行会缓存只读知识元数据，减少关键词检索重复加载；最终 Chunk、来源和版本仍回 PostgreSQL 校验。缓存不跨知识版本成为事实来源，也不与 Redis Task Checkpoint 混用。

索引器按模型、维度、schema version 和内容 hash 判断是否重建向量。HNSW 使用 cosine 距离；知识量较小时不预设性能收益，实际效果由 Recall@K 和 wall-clock 评测决定。

## 6. 当前实测结果

测试集包含 120 篇合成文档、2,307 个 Chunk、125 个基础 Case 和 500 条 Query。最终配置为活动版本过滤、实体证据门和单次运行知识快照。

| 指标 | 初始 | 当前 | 变化 |
| --- | ---: | ---: | ---: |
| Recall@5 | 70.96% | 85.19% | +14.23 个百分点 |
| 来源绑定回答准确率 | 23.44% | 63.75% | +40.31 个百分点 |
| 来源绑定幻觉率 | 51.25% | 7.50% | -43.75 个百分点 |
| RAG p95 | 886.767 ms | 358.686 ms | -59.55% |
| 端到端 p95 | 3,398.879 ms | 2,187.268 ms | -35.65% |
| 总 token | 620,183 | 231,268 | -62.71% |
| 观测成本 | $0.675887 | $0.276581 | -59.08% |

360 次模型调用中有 18 次结构化输出 fallback，比例为 5.00%。回答类型准确率和必需来源召回率分别下降 3.13、2.19 个百分点，无答案场景准确率仍为 0。以上都是合成测试环境工程指标，不是临床准确率或生产 SLA。

详细过程见 [RAG 四指标优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)，数据字段与路径见 [合成 RAG 评测数据集](RAG_SYNTHETIC_EVALUATION_DATASET.md)。

## 7. 尚未完成

- 面向正式知识库的文档审核、自动切片、版本发布、回滚和增量索引流水线。
- 无答案场景判定与结构化输出 fallback 稳定性优化。
- 使用合法脱敏真实语言和人工 Gold 的独立质量评测。
- 真实医院、药店和通知系统的生产接入。

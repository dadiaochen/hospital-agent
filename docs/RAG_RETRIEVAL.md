# RAG 知识与证据层设计

## 1. 作用与边界

RAG 为分诊、慢病用药和报告解读提供版本化知识证据，不负责诊断、开方或修改医生处方。处方、过敏史、报告和药箱库存属于业务事实，每次从数据库或 Provider 读取，不进入知识向量库。

没有数据库、Provider 或 RAG 来源时，Agent 不得编造病史、库存、处方、医疗规则或检查结论。

## 2. 当前检索 Pipeline

```text
Query
  -> 活动版本前置过滤与显式实体提取
  -> FastEmbed -> PostgreSQL pgvector HNSW 向量召回
  -> BM25 词法召回
  -> RRF 融合
  -> 实体相关性过滤、精确重复去重、候选 20 条轻量 rerank
  -> 文档主片段 / 紧邻补充片段优先
  -> PostgreSQL 来源与版本校验
  -> 1～2 个直接来源
  -> Model Gateway
  -> FinalClaim 与 SourceRef 校验
```

- 向量检索负责语义覆盖，BM25 词法检索补充药品名、指标名、规则编号和短查询；两路均只读活动版本。
- 两路结果按 rank 做 RRF 融合，不比较不同量纲的原始分数。
- 活动版本过滤发生在候选截断前，避免旧版本占用 Top-K。
- 对显式实体 Query，先排除实体不匹配来源；候选 20 条再按精确实体命中、双路命中、词项覆盖、RRF 分数与文档内位置重排。
- 去重只移除同一 Chunk 的重复来源，不删除相邻且互补的 Chunk；Query 明确询问步骤、条件或例外时，候选重排优先相应证据角色，最小证据门为每个角色选择一个直接 Chunk；无结构元数据时降级为两条直接证据。
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

单次批量运行会缓存只读知识元数据，并复用经 document/chunk ID、版本和 embedding model 完整校验的 HNSW 索引，减少评测启动和 BM25 重建；最终 Chunk、来源和版本仍回 PostgreSQL 校验。缓存不跨知识版本成为事实来源，也不与 Redis Task Checkpoint 混用。

索引器按模型、维度、schema version 和内容 hash 判断是否重建向量。HNSW 使用 cosine 距离；知识量较小时不预设性能收益，实际效果由 Recall@K 和 wall-clock 评测决定。

## 6. 当前实测结果

测试集包含 120 篇合成文档、2,392 个 Chunk、125 个基础 Case 和 500 条 Query。本轮保留配置为活动版本过滤、BM25 + HNSW 双路召回、RRF、实体过滤、候选 20 条轻量 rerank、精确去重、结构化证据角色重排、最小角色上下文和单次运行知识快照。

| 指标 | 旧冻结基线 | 当前组合 | 变化 |
| --- | ---: | ---: | ---: |
| Recall@3 / @5 / @10 | 67.50% / 85.19% / 95.38% | 100.00% / 100.00% / 100.00% | +32.50 / +14.81 / +4.62 个百分点 |
| Precision@3 / @5 / @10（原冻结 Gold） | 25.00% / 21.38% / 12.46% | 43.59% / 26.15% / 13.08% | +18.59 / +4.77 / +0.62 个百分点 |
| Precision@3 / @5 / @10（AI 自动扩展证据） | N/A | 60.51% / 50.15% / 31.81% | 标签覆盖复测，非检索模型提升 |
| MRR@10 | 0.5059 | 0.8125 | +0.3066 |
| 来源绑定回答正确率 | 74.69% | 99.69% | +25.00 个百分点 |
| Faithfulness（260 条可回答题） | 0.9545 | 0.9837 | +0.0292 |
| Response Relevancy（260 条可回答题） | 0.4752 | 0.6818 | +0.2066 |
| Context Recall（260 条可回答题） | 0.8462 | 1.0000 | +0.1538 |
| 确定性来源绑定幻觉率 | 7.50% | 0.00% | -7.50 个百分点 |

自动扩展证据标签对 65 个正样本基础 Case 由真实模型生成，无人工审核、无 fallback，每题平均 3.95 个 Chunk；它只复用已有 `retrieval_results.jsonl` 重算 Precision，不重跑 HNSW 或回答模型。当前真实模型运行的 fallback 为 0.56%（2/360），完整 usage 覆盖率 99.44%。平均总 token 与平均成本分别上升 18.70% 和 15.51%，因为证据逐项核对提示词更长；端到端 P95 由 2,187.268 ms 变为 2,713.646 ms，但两次本地 CUDA 运行环境不一致，不能将其归因于检索策略或作为性能结论。以上均是冻结合成数据的工程指标，不是临床准确率或生产 SLA。

已完成一项不保留的 Cross-Encoder 对照：`BAAI/bge-reranker-base` 仅重排同一份冻结 Top-10 候选，在 15 个基础 Case、60 条 Query 上，自动扩展证据 Precision@3 从 60.56% 降至 17.78%，原冻结 Gold Precision@3 从 33.33% 降至 0%。原因是通用模型偏好同主题补充片段，没有内置“活动版本规则主片段优先”的业务约束。因此当前保留的仍是实体过滤、轻量规则重排与主片段优先；Cross-Encoder 不进入主链路或简历表述。详细可复现实验见 [RAG 合成评测统一报告](RAG_SYNTHETIC_EVALUATION_DATASET.md)。

真实 LLM 受限重排也未保留：`deepseek-v4-flash` 只输出同一 Top-10 的完整排列，在相同 60 条 Query 上将自动扩展证据 Precision@3/@5 从 60.56%/53.33% 变为 55.00%/49.33%，冻结 Gold Precision 保持 33.33%/20.00%/10.00%。合法排列率 96.67%，每条额外约 2,850 token 和 2.12 秒。现有规则排序已经显式编码了版本、实体和主片段约束，LLM 未提供净收益，故不进入在线链路。

查询扩展也只保留为离线诊断：真实 LLM 不读取知识库，只规范化原问句已出现的实体与条件，并始终保留原问句。15 个基础 Case、60 条 Query 上，自动扩展证据 Precision@3/@5/@10 从 60.56%/53.33%/30.83% 到 64.45%/54.33%/31.83%；冻结 Gold Recall 和 Precision 全部持平。它每条增加约 220 token、1.88 秒，因此没有足够的正式指标净收益来进入默认在线链路或简历。

“结构化过滤 + 父子 Chunk”也已完成等价核验。当前保留的实体过滤、规则重排、文档主片段优先与最小证据门，已经实现“子 Chunk 定位、父主片段优先、综合问题按需补充”的效果；15 个基础 Case、60 条 Query 中，父子对照与当前 M5 交给模型的证据 Chunk 60/60 完全一致，核心检索与来源绑定回答指标没有净变化。因此未新增重复 profile。真正的父子检索需要在知识元数据中引入明确的 `parent_chunk_id` / `section_id`，再以独立人工多证据 Gold 验证。

数据字段、路径、初始/当前指标、RAGAS 和优化收益统一见 [RAG 合成评测统一报告](RAG_SYNTHETIC_EVALUATION_DATASET.md)；M2–M5 历史实现细节见 [RAG 四指标优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)。

## 7. 尚未完成

- 面向正式知识库的文档审核、自动切片、版本发布、回滚和增量索引流水线。
- 无答案场景判定与结构化输出 fallback 稳定性优化。
- 使用合法脱敏真实语言和人工 Gold 的独立质量评测。
- 真实医院、药店和通知系统的生产接入。

## 8. 5A 分层评测推进中

当前真实全链路脚本在冻结 Chunk ID Gold 上已计算 Recall@3/5/10、Precision@3/5/10、MRR@10、二值 nDCG@10、无答案准确率、过期版本过滤和检索 P50/P95/P99。二值 nDCG 使用相关 Chunk 的排名折损，不调用 LLM Judge，用于区分“召回到了但排位靠后”和“没有召回”。

bad case 统一区分 `RETRIEVAL_MISS`、`RANKING_MISS`、`NO_ANSWER_FAILURE`、`STALE_VERSION_HIT` 与生成层的 `ANSWER_SOURCE_BINDING_FAILURE`。RAGAS 0.2.9 只在答案、来源和冻结 Gold 写入后运行；未配置或失败时缺失项记 N/A。生成式三项只统计 260 条可回答题，60 条无答案题由无答案准确率独立验收；最终三项为 0.9837/0.6818/1.0000，260/260 完整。实测状态统一见 [RAG 合成评测统一报告](RAG_SYNTHETIC_EVALUATION_DATASET.md)。

报告解析产生的来源仍是成员业务数据，不进入 RAG 知识库 namespace、向量索引或长期记忆。`ParsedDocument` 只为报告直接读取服务；结构化指标不能作为医疗知识召回结果或模型事实来源，除非由业务工具在当前成员作用域内重新读取。

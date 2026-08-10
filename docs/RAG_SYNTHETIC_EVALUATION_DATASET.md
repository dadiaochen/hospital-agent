# 互联网医院 Agent 合成 RAG 评测：数据集、指标与优化结果

> 本文是 `rag-synthetic-v1` 的唯一指标口径，统一记录数据集、初始指标、当前指标、已实施优化、RAGAS 和后续思路；其他文档只保留任务状态或历史细节。

## 1. 数据集用途

这是一套仅用于测试环境的合成数据，用来评测互联网医院 Agent 的知识召回、来源绑定回答、幻觉、拒答、版本过滤、延迟、token 和成本。内容模拟医疗流程、慢病随访、药品规则、报告解释、Agent 安全、隐私隔离和历史版本干扰。

它不是患者数据、医院知识库或临床 Gold，也没有人工逐条审核回答。文档、标签和结果均标记为 `synthetic`、`test_only`、`human_reviewed=false`、`clinical_gold=false`。

## 2. 规模与内容

| 对象 | 数量 | 内容 |
| --- | ---: | --- |
| 知识文档 | 120 | 业务规则、慢病、药品、报告、安全、隐私和历史版本 |
| 活动文档 | 100 | 当前版本允许进入检索 |
| 过期文档 | 20 | 测试版本过滤与高相似干扰 |
| Chunk | 2,307 | 冻结知识切片 |
| 基础 Case | 125 | 冻结场景与自动标签 |
| Query | 500 | 每个基础 Case 生成 4 种表达 |

四种表达为标准问法、口语问法、地域表达和噪声表达。场景包括单文档、多 Chunk 硬负例、过期版本、无答案、高风险医疗、仅工具事实、题外问题和治理 badcase。

## 3. 数据划分

同一基础 Case 的四种表达始终位于同一 split，避免表达泄漏。

| Split | 基础 Case | Query |
| --- | ---: | ---: |
| development | 75 | 300 |
| validation | 25 | 100 |
| holdout | 25 | 100 |
| 合计 | 125 | 500 |

当前 holdout 的 RAG 正样本覆盖不足，因此全量 500 Query 只用于固定工程对比，不宣称独立泛化能力。

## 4. 路径与文件

冻结数据：

`E:\project_code\hospital\output\benchmarks\rag_synthetic\fixtures\rag_synthetic_v1\`

目录结构：

- `corpus/`：知识文档、Chunk 和语料 manifest；
- `dataset/`：基础 Case 与 development、validation、holdout；
- `labels/`：流程、检索、回答和安全标签；
- manifest/hash：冻结随机种子、文件数量、关联关系和 SHA-256。

最终全链路结果：

`E:\project_code\hospital\output\benchmarks\rag_synthetic\rag-synthetic-v1-m5-final-gpu-full-20260807\`

## 5. 单条数据包含什么

每条 Query 至少包含：

- `query_id`、`base_case_id`、split、表达类型和用户输入；
- 是否需要 RAG、工具、模型、人工确认和安全拦截；
- 相关文档与 Chunk、过期来源和 hard negative；
- 回答类型、必需事实、支持来源和禁止声明；
- 合成用户、家庭成员、文档版本和场景锚点；
- 固定随机种子与 manifest hash。

自动检查覆盖 schema、ID 唯一性、来源存在性、版本关系、protected slot、split 泄漏和 hash 一致性。

## 6. 完整评测链路

```text
Query
  -> 入口治理
  -> FastEmbed
  -> PostgreSQL pgvector HNSW
  -> 关键词检索
  -> RRF 融合
  -> 活动版本过滤
  -> 来源校验
  -> 实体证据门
  -> 真实 LLM
  -> schema / safety
  -> 确定性评测
```

本次 FastEmbed 使用 CUDA Execution Provider；GPU 只负责本地 Embedding。HNSW 在 PostgreSQL 执行，远端 LLM 通过 Model Gateway 调用。

## 7. 初始与当前结果

| 指标 | 初始 | 当前 | 变化 |
| --- | ---: | ---: | ---: |
| Recall@3 | 56.35% | 67.50% | +11.15 个百分点 |
| Recall@5 | 70.96% | 85.19% | +14.23 个百分点 |
| Recall@10 | 82.31% | 95.38% | +13.07 个百分点 |
| 来源绑定回答准确率 | 23.44% | 63.75% | +40.31 个百分点 |
| 支持性引用精确率 | 39.71% | 63.75% | +24.04 个百分点 |
| 来源绑定幻觉率 | 51.25% | 7.50% | -43.75 个百分点 |
| 端到端 p95 | 3,398.879 ms | 2,187.268 ms | -35.65% |
| RAG p95 | 886.767 ms | 358.686 ms | -59.55% |
| 总 token | 620,183 | 231,268 | -62.71% |
| 观测成本 | $0.675887 | $0.276581 | -59.08% |

360 次模型调用中，342 次使用真实 Provider，18 次结构化输出失败后降级，fallback 为 5.00%。回答类型准确率和必需来源召回率分别下降 3.13、2.19 个百分点；无答案场景准确率仍为 0。

## 8. 做过什么改进，提升了什么

### 8.1 召回率：活动版本前置过滤

**问题：** 旧版药品和规则 Chunk 与当前版本高度相似。如果在 Top-K 截断后才过滤，正确文档可能已经被旧版本挤出候选。

**思路与实现：** 把版本约束前移到候选生成阶段，同时约束关键词和 HNSW 向量候选，融合后再次校验来源版本。轻量 rerank 和去重分别做过单变量实验：rerank 导致召回回退，去重没有可测变化，因此均未进入最终配置。

**提升：** Recall@5 提升 `14.23` 个百分点，Recall@10 提升 `13.07` 个百分点，过期文档误召回从 `63` 条降为 `0` 条。

### 8.2 回答准确率：实体证据门与最小上下文

**问题：** 向量和关键词混合检索提高了候选覆盖，但同药异规格、相似规则和无关 Chunk 会污染上下文，模型容易引用错误来源。

**思路与实现：** 保留混合检索，在“检索后、生成前”提取药品、规格、规则编号等实体，只把直接支持问题的来源交给模型。普通问题最多保留 1 个直接来源，综合问题最多保留 2 个；没有匹配证据时传空 evidence，最终 Claim 必须绑定直接来源。

**提升：** 来源绑定回答准确率提升 `40.31` 个百分点，支持性引用精确率提升 `24.04` 个百分点，来源绑定幻觉率下降 `43.75` 个百分点。

### 8.3 延迟：单次运行知识快照

**问题：** 批量检索反复读取相同 PostgreSQL 知识元数据，造成不必要的 I/O 和长尾延迟。

**思路与实现：** 在同一次冻结评测中缓存不会变化的只读知识元数据，后续关键词检索复用；最终按 Chunk ID 获取来源和校验版本时仍回 PostgreSQL。这里的“只读快照”只是一轮运行内的临时副本，不是事实来源，也不会覆盖数据库。

**提升：** RAG p95 下降 `59.55%`，端到端 p95 下降 `35.65%`。

### 8.4 Token 与成本：缩小证据上下文

**问题：** 真实 LLM 输入中无关 Chunk 较多，输入 token 是主要成本来源。

**思路与实现：** 复用实体证据门，把宽 Top-K 收敛为 1～2 个直接来源。8 条样本测试过将输出上限从 512 降到 256，但 token 仅下降 `1.06%`、成本仅下降 `1.65%`，最终仍保留 512。

**提升：** 总 token 下降 `62.71%`，观测成本下降 `59.08%`。

删除 Planner 没有被采用。Planner 只为复杂跨领域任务生成一次冻结计划，当前主要 token 来自回答模型输入；让 Supervisor 同时承担规划和调度会破坏职责边界，也不能稳定解决长上下文问题。

## 9. 每个节点的延迟、token 与成本

下表使用与第 7 节初始/当前指标相同的历史 M5 最终运行，保证优化前后口径可比。

| 节点 | 样本/调用数 | p95 | 输入 / 输出 / 总 token | 成本 |
| --- | ---: | ---: | ---: | ---: |
| 入口治理 | 500 | 0.001 ms | 0 | $0 |
| FastEmbed + HNSW + HybridRetriever | 320 | 358.686 ms | 0（本地） | $0 |
| ModelGateway 真实 LLM | 360 | 1,924.087 ms | 185,955 / 45,313 / 231,268 | $0.276581 |
| Deterministic Evaluator | 500 | 0.001 ms | 0 | $0 |

GPU 只加速历史 M5 运行中的本地 Embedding，不作为本轮优化收益；HNSW 在 PostgreSQL 执行，远端 LLM 不使用本机 GPU。当前 RAGAS 运行因本机缺少 CUDA 运行库而使用 CPU FastEmbed，这只影响运行耗时，不改变 Judge 指标定义。

## 10. RAGAS 独立 Judge 指标

RAGAS 是可选、失败不阻断的离线语义评测层。目标回答模型使用 `deepseek-v4-flash`，独立 Judge 使用 `deepseek-v4-pro`，本地 Embedding 使用 FastEmbed `BAAI/bge-small-zh-v1.5`。RAGAS 不进入业务执行链路，也不修改最终答案；确定性来源、安全和隔离指标仍是硬门。

### 10.1 已完成的单条真实链路验证

样本 `syn-rag-v1-query-001` 仅用于验证适配器、独立 Judge 和三项指标链路可用，不能与 500 Query 汇总结果直接比较。

| RAGAS 指标 | 单条结果 |
| --- | ---: |
| Faithfulness | 0.8333 |
| Response Relevancy | 0.8225 |
| Context Recall | 1.0000 |

产物：

`E:\project_code\hospital\output\benchmarks\rag_synthetic\rag-synthetic-v1-ragas-smoke-detail-20260810\`

### 10.2 冻结记录全量离线评分

原实现使用 `raise_exceptions=True`，一条 Response Relevancy 输出被 RAGAS 解析成兜底 `StringIO` 后，使 320 条批次全部失败。本次改为批内异常隔离、非有限数转 N/A、部分指标保留，并增加冻结记录离线评分脚本。脚本只读取既有回答、证据门选中的 Chunk 和冻结 Gold；没有重跑语料 Embedding、PostgreSQL/pgvector HNSW 检索或目标回答模型。Response Relevancy 仍按 RAGAS 定义使用本地指标 Embedding。

最终结果统一只使用 300 条三项齐全的共同样本，另外 20 条部分评分样本整体排除，不进入任何指标分子或分母，也不按 0 分处理。

| RAGAS 指标 | 最终样本 | 均值 | P50 | P95 |
| --- | ---: | ---: | ---: | ---: |
| Faithfulness | 300 | 0.6166 | 0.8333 | 1.0000 |
| Response Relevancy | 300 | 0.4316 | 0.7037 | 0.8667 |
| Context Recall | 300 | 0.6700 | 1.0000 | 1.0000 |

320 条样本全部至少获得一项分数，其中 300 条三项齐全，最终共同样本覆盖率为 `93.75%`。首轮后只定向补跑 24 条缺失项，并补齐其中 4 条；随后独立 Judge 返回 HTTP 402 余额不足。剩余 20 条仅保留为缺失诊断记录，不参与最终统计。

最终产物：

`E:\project_code\hospital\output\benchmarks\rag_synthetic\rag-synthetic-v1-ragas-offline-full-fix-retry-20260810\`

原始回答与检索产物的 SHA-256 已写入 `run_manifest.json`，同时明确记录 `source_records_read_only=true`、`retrieval_embedding_invoked=false`、`database_or_hnsw_invoked=false`、`target_answer_model_invoked=false`。三项 RAGAS 分数是合成测试上的语义交叉验证，不与确定性指标混合成总分，也不表示临床准确率。

## 11. 当前不足与后续优化思路

回答类型准确率从 `74.38%` 降到 `71.25%`，必需来源召回率从 `65.94%` 降到 `63.75%`；无答案场景准确率仍为 `0`。132 条 badcase 中，116 条为回答来源绑定失败，16 条为检索漏召回。

| 优先级 | 目标 | 尚未实施的方案 | 验证方式 |
| --- | --- | --- | --- |
| P0 | 无答案与准确率 | 增加 no-answer 判定；修复结构化输出 fallback | 先复测 132 条 badcase，再跑固定 500 Query |
| P1 | 召回 | 父子 Chunk：子 Chunk 检索，命中后回填父 Chunk 的完整规则上下文 | 对比 Recall@K、MRR 和上下文 token |
| P1 | 召回与准确率 | 将 Query 结构化为实体、规格、规则类型和时间版本，再执行向量 + BM25、融合去重和可选 rerank | 检查同药异规格、相似规则和 stale hard negative |
| P1 | 准确率 | 对 Claim 做逐条证据绑定，无法绑定的内容删除或改为无法确认 | 来源绑定准确率、引用精确率和幻觉率 |
| P2 | 延迟 | 活动版本清单按知识版本失效；批量获取 Chunk，避免逐条回源 | RAG p95、数据库查询次数和回源正确性 |
| P2 | token/cost | no-answer 短路、按任务复杂度选择模型、压缩父 Chunk 中无关段落 | 每节点 token、成本和质量回退 |

这些方案只是候选，不能写成已经带来收益。

## 12. 结果解释与文档关系

“来源绑定回答准确率”表示合成标签下，回答事实和支持来源一致，不是临床准确率。成本只统计 Provider 返回 usage 的调用，fallback 不做估算。本机延迟不是生产 SLA。

构建任务状态见 [数据集构建方案](RAG_SYNTHETIC_EVALUATION_DATASET_PLAN.md)，M2–M5 阶段索引见 [RAG 优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)，历史实验过程见 [项目执行历史](EXECUTION_HISTORY.md)。

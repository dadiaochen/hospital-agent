# 互联网医院 Agent 全自动合成 RAG 评测数据集实施方案

## 1. 目的和边界

本方案记录当前合成评测数据的构建方法；历史授权和执行顺序见 [项目执行历史](EXECUTION_HISTORY.md)。目标是：

1. 在隔离知识库中构建较大规模的仿真医疗知识、业务规则、药品和安全文档；
2. 快速生成约 500 条 Query，自动完成生成、清洗、标注和评测，不增加人工审核门；
3. 通过真实 RAG 链路观察 Recall、来源绑定回答准确率、幻觉、延迟和 token/cost；
4. 根据结果列出后续 rerank、检索策略、chunk、top-k、上下文、缓存和模型调用优化候选，但本支线不直接实施这些优化。

数据全部标记为 `synthetic`、`test-only`、`human_reviewed=false`、`clinical_gold=false`，不得进入正式医疗知识库、个人记忆或临床决策。

## 2. 冻结规模和目录

当前冻结版本：`rag-synthetic-v1`。

| 对象 | 数量 |
|---|---:|
| 仿真文档 | 120 |
| active 文档 | 100 |
| stale 文档 | 20 |
| Chunk | 2307 |
| Base Case | 125 |
| Query | 500 |

冻结目录：

`E:\project_code\hospital\output\benchmarks\rag_synthetic\fixtures\rag_synthetic_v1\`

目录包含 `corpus/`、`dataset/`、`labels/` 三部分，以及各自 manifest/hash。真实评测产物位于 `output/benchmarks/rag_synthetic/`。

## 3. 文档构建策略

仿真语料按以下文档族生成：互联网医院业务规则、慢病随访、药品说明与库存规则、检查报告解释、Agent 安全与人工确认、成员隔离与隐私、版本变更和高相似硬负例。每篇文档具有 `document_id/title/category/source/version/status/superseded_by/valid_from/valid_to`，Chunk 保留 `chunk_id/document_id/chunk_version/content/keywords`。

文档内容使用稳定实体编号，例如 `SYN-BUSINESS-01`、`SYN-DRUG-01` 和 `SYN-REPORT-01`，便于自动生成 Query、检索 gold、来源绑定 gold 和 badcase。

## 4. 数据和标签字段

每个 Base Case 生成四种表达：`canonical`、`colloquial`、`regional`、`noisy`。每条 Query 至少包含：

- `query_id/base_case_id/split/variant_type/user_input`；
- `expected_flow`：是否 RAG、是否调用模型、是否需要工具、终止阶段和安全动作；
- `retrieval_gold`：相关 Chunk、相关文档、stale Chunk、hard negative；
- `answer_gold`：回答类型、必需事实、支持来源、禁止声明；
- `protected_slots`：合成成员、文档、版本和场景锚点；
- `manifest_sha256` 和固定随机种子。

同一 Base Case 的四种表达必须处于同一 split，防止表达变体泄漏。

## 5. A–G 任务拆分和状态

| 任务 | 内容 | 状态 | 交付 |
|---|---|---|---|
| A | 冻结命名空间、随机种子、字段和安全边界 | `DONE` | manifest/schema |
| B | 生成 120 篇仿真知识/规则/药品/安全文档 | `DONE` | corpus JSONL |
| C | 文档清洗、Chunk 切分、版本和 hard negative | `DONE` | 2307 Chunk、版本校验 |
| D | 生成 125 个 Base Case、500 条 Query 和三 split | `DONE` | dataset JSONL |
| E | 自动 schema、来源、版本、槽位、split 门禁 | `DONE` | validation report |
| F | 隔离知识库导入、Embedding、HNSW 和确定性基线 | `DONE` | deterministic report |
| G | 真实 FastEmbed + PostgreSQL pgvector HNSW + LLM 评测 | `DONE` | baseline/M2–M5 reports |

A–G 自动门通过后立即生成并冻结完整数据，不增加人工复核门。该数据集不能替代 300 个 WorldState、1200 条 Query 的人工审核金标准。

## 6. 评测链路和指标

```text
Query -> 入口治理 -> Embedding -> pgvector HNSW
      -> Keyword + Vector + RRF -> ModelGateway
      -> schema/safety -> Deterministic Evaluator
```

报告至少包括：Recall@3/5/10、MRR@10、stale filter rate、来源绑定回答准确率、回答类型准确率、必需来源召回率、支持性引用精确率、来源绑定幻觉率、入口/RAG/LLM/Evaluator/端到端 p50/p95/p99、每节点 token 和按配置价格计算的 cost、fallback、schema 和 safety。

没有 provider usage 时，token/cost 必须写为不可用，不允许按字符估算。

## 7. 后续候选清单（只列方案，不在本方案直接优化）

| 指标 | 候选方案 | 触发依据 | 风险 |
|---|---|---|---|
| 召回率 | active version 前置、关键词+向量并行、扩大 candidate pool、调整 top-k、chunk 粒度 | stale 或 Recall@K 低 | 计算量和噪声增加 |
| 回答准确率 | Query 实体证据门、最小来源上下文、支持 Claim 的 citation contract | 正确来源已召回但引用错误 | 过窄导致 evidence miss |
| 延迟 | run-scoped snapshot、减少重复回源、控制 candidate 数和 HNSW 参数 | RAG p95 长尾 | 缓存一致性和失效边界 |
| token/cost | 减少无关上下文、输出上限、no-answer 短路、模型分级 | input/output token 高 | 过度压缩答案或拒答 |
| 质量稳定性 | schema failure 分类、有限重试、fallback 统计和 provider 超时分层 | fallback 非零 | 重试增加延迟/成本 |

不通过额外实验，不把候选方案写成已经带来收益。

## 8. 当前优化执行结果索引

- M2：仅活动版本过滤通过检索门，Recall@5 `0.7096→0.8519`。
- M3：32 条方向样本来源绑定准确率 `37.50%→59.38%`，全量由 M5 收口。
- M4：RAG p95 `2104.529→393.442ms`；8 条成本变量总 token 下降 `1.06%`。
- M5：最终 profile 全量 500 Query；Recall@5 `0.8519`，来源绑定回答准确率 `0.6375`，来源绑定幻觉率 `0.0750`，端到端 p95 `2187.268ms`，观测总 token `231268`，观测成本 `$0.276581`；fallback `5.00%`。

详细结果、路径、中文简历和面试口径见 [RAG synthetic v1 数据集说明](RAG_SYNTHETIC_EVALUATION_DATASET.md) 和 [最小优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)。

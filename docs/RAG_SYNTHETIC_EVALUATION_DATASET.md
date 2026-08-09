# 互联网医院 Agent 合成 RAG 评测数据集

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

## 8. 结果解释

“来源绑定回答准确率”表示合成标签下，回答事实和支持来源一致，不是临床准确率。成本只统计 Provider 返回 usage 的调用，fallback 不做估算。本机延迟不是生产 SLA。

实施思路、每项改动与提升见 [RAG 四指标优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)。构建任务状态见 [数据集构建方案](RAG_SYNTHETIC_EVALUATION_DATASET_PLAN.md)，历史实验过程见 [项目执行历史](EXECUTION_HISTORY.md)。

# RAG 四指标优化实施与复测（历史实施明细）

> 本文保留 M2–M5 的实现细节，便于代码回溯，不再作为指标权威来源。数据集说明、初始/当前指标、RAGAS、改进思路和最终收益统一以 [合成 RAG 评测：数据集、指标与优化结果](RAG_SYNTHETIC_EVALUATION_DATASET.md) 为准。

数据冻结为 125 个基础 Case、500 条 Query，不修改 Gold，不增加人工审核门。全部结果属于合成测试环境工程评测，不是临床准确率、线上 SLA 或生产成本；逐次实验记录见 [项目执行历史](EXECUTION_HISTORY.md)。

## 1. 测试链路

FastEmbed → PostgreSQL/pgvector HNSW 向量检索 + 关键词检索 → 融合 → 活动版本校验 → 证据筛选 → 真实 LLM → 确定性评测。GPU 只加速本地 Embedding；HNSW 在 PostgreSQL 执行，远端 LLM 不使用本机 GPU。

## 2. 初始指标与当前指标

| 指标 | 初始 | 当前 | 变化 |
|---|---:|---:|---:|
| Recall@3 | 0.5635 | 0.6750 | +11.15pp |
| Recall@5 | 0.7096 | 0.8519 | +14.23pp |
| Recall@10 | 0.8231 | 0.9538 | +13.07pp |
| 来源绑定回答准确率 | 0.2344 | 0.6375 | +40.31pp |
| 支持性引用精确率 | 0.3971 | 0.6375 | +24.04pp |
| 来源绑定幻觉率 | 0.5125 | 0.0750 | -43.75pp |
| 端到端 p95 | 3398.879ms | 2187.268ms | -35.65% |
| RAG p95 | 886.767ms | 358.686ms | -59.55% |
| 总 token | 620183 | 231268 | -62.71% |
| 观测成本 | $0.675887 | $0.276581 | -59.08% |

回答类型准确率 `0.7438→0.7125`（-3.13pp），必需来源召回率 `0.6594→0.6375`（-2.19pp），不能写成四项指标全部提升。

## 3. 召回率：活动版本前置过滤

**简述：** 在候选截断前排除过期文档，避免旧版本占用 Top-K。

**思路：** 若检索完成后才过滤旧版本，正确文档可能已经被相似的历史 Chunk 挤出 Top-K，因此版本约束必须进入关键词和向量候选生成阶段。

**实现：** 从 PostgreSQL 读取活动文档清单，并同时约束关键词与 HNSW 候选；融合后再次校验来源版本。轻量 rerank 和去重也做了单变量测试，但前者导致召回回退、后者没有变化，均未进入最终方案。

**结果：** Recall@5 从 70.96% 提升到 85.19%，Recall@10 从 82.31% 提升到 95.38%，过期文档误召回从 63 条降为 0 条。

## 4. 回答准确率：实体证据门与最小上下文

**简述：** 向量和关键词仍并行检索，但只把直接支持当前问题的来源交给模型。

**思路：** 混合检索能增加候选覆盖，却不会自动提高回答准确率。过宽上下文会把同药异规格、相似规则和旧版本一起交给模型，因此优化点放在“检索后、生成前”的证据选择。

**实现：** 提取 Query 中的药品、规则编号和业务实体；普通问题最多保留 1 个直接来源，综合问题最多保留 2 个；没有匹配证据时传空 evidence 并要求无法确认。最终 Claim 必须绑定直接来源。

**结果：** 来源绑定回答准确率从 23.44% 提升到 63.75%，引用精确率从 39.71% 提升到 63.75%，来源绑定幻觉率从 51.25% 降到 7.50%。

## 5. 延迟：单次运行知识快照

**简述：** 在同一次批量运行内复用只读知识元数据，减少重复读取 PostgreSQL。

**思路：** 关键词检索会反复加载相同知识记录，这些记录在一次冻结评测中不会变化，可以安全复用；最终来源和版本仍必须回 PostgreSQL 校验，缓存不能成为事实来源。

**实现：** `SQLAlchemyKnowledgeStore` 首次读取后建立 run-scoped 快照，后续关键词检索复用；按 Chunk ID 获取最终来源时仍回权威库。Embedding 支持 `cpu/cuda/auto`，显式选择 CUDA 时校验实际 Execution Provider。

**结果：** RAG p95 从 886.767 ms 降到 358.686 ms，下降 59.55%；端到端 p95 从 3,398.879 ms 降到 2,187.268 ms，下降 35.65%。

## 6. Token 与成本：缩小证据上下文

**简述：** 成本下降来自减少无关检索片段，不需要删除 Planner。

**思路：** Planner 只服务复杂跨领域任务，而本轮主要 token 来自回答模型输入。让 Supervisor 同时规划和调度会破坏冻结计划与职责边界，也不能稳定解决长上下文；最小有效改动是压缩证据。

**实现：** 复用实体证据门，把宽 Top-K 收敛为 1～2 个直接来源。8 条样本还测试了 256 输出上限，但 token 仅下降 1.06%、成本仅下降 1.65%，所以最终保持 512。

**结果：** 总 token 从 620,183 降到 231,268，下降 62.71%；观测成本从 $0.675887 降到 $0.276581，下降 59.08%。

## 7. GPU 运行说明

FastEmbed 支持 `RAG_EMBEDDING_DEVICE=cpu|cuda|auto`，默认 CPU。M5 评测使用 CUDA 12 兼容的 `onnxruntime-gpu==1.22.0` 和本机 CUDA/cuDNN DLL；preflight session provider 为 `CUDAExecutionProvider + CPUExecutionProvider`。GPU 只加速本地 Embedding，HNSW 仍由 PostgreSQL 执行，远端 LLM 不在本机 GPU 上运行。

当显式设置 `cuda` 时，代码会校验 session provider；如果 CUDA 依赖缺失，将失败而不会静默改跑 CPU。

## 8. 可复现命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:RAG_EMBEDDING_DEVICE='cuda'
$env:PATH='D:\soft\conda\Lib\site-packages\torch\lib;'+$env:PATH

.venv\Scripts\python.exe -B scripts\run_synthetic_rag_full_eval.py --profile m5-final --all --output-dir output\benchmarks\rag_synthetic\rag-synthetic-v1-m5-final-gpu-full-20260807

$env:PYTHONPATH=(Resolve-Path 'backend').Path
.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests\test_provider_and_embedding.py backend\tests\test_rag_synthetic_eval.py backend\tests\test_rag_synthetic_full_eval.py -q
```

## 9. 节点成本

| 节点 | 样本数 | p95 | token | 成本 |
|---|---:|---:|---:|---:|
| 入口治理 | 500 | 0.001ms | 0 | $0 |
| FastEmbed + HNSW + HybridRetriever | 320 | 358.686ms | 0（本地） | $0 |
| ModelGateway 真实 LLM | 360 | 1924.087ms | 185955 / 45313 / 231268 | $0.276581 |
| Deterministic Evaluator | 500 | 0.001ms | 0 | $0 |

360 次模型调用中真实 Provider 342 次、deterministic fallback 18 次，fallback rate `5.00%`，usage 可用率 `95.00%`；18 次 fallback 不估算 token/cost。

## 10. 限制与下一步

- 360 次模型调用中 342 次使用真实 Provider，18 次结构校验失败后降级，fallback 为 5.00%。
- 无答案场景准确率仍为 0；132 条 badcase 中，116 条是回答来源绑定失败，16 条是检索漏召回。
- 下一步只修复结构化输出 fallback 和无答案判定，再在同一配置下小范围复测。
- 简历和面试写法统一见 [互联网医院多 Agent 项目：简历与面试口径](RESUME_NOTES.md)。

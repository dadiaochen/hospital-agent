# RAGAS 离线适配器与三视图 Harness

> 本文只记录适配器的实现和运行方式。数据集、确定性指标、RAGAS 实测状态及优化收益统一见 [RAG 合成评测统一报告](../RAG_SYNTHETIC_EVALUATION_DATASET.md)。

## 已完成内容

- 固定使用 `ragas==0.2.9`，但不在业务运行链路导入或调用它。
- 只在真实 LLM 输出、检索来源和冻结答案 Gold 都已写入结果后，计算 Faithfulness、Response Relevancy、Context Recall。
- Judge 未配置、依赖未安装、网络超时、返回异常或分数解析失败时，逐条保留成功指标，缺失指标记为 N/A；检索结果、模型回答、bad case、进程退出码均不受影响。
- 为同一份冻结数据输出三份视图：`entry_harness_view.jsonl`、`retrieval_harness_view.jsonl`、`answer_harness_view.jsonl`。它们保留同一个 `query_id`、`base_case_id` 和 split，不从本次检索或模型输出反推 Gold。

## 当前实测状态

- 已修复单个 `StringIO.question` 格式异常拖垮整批的问题，使用 `raise_exceptions=false`、批次/并发限制、独立 Judge 超时和非有限分数归一化。
- 冻结记录全量评分覆盖 320 条，其中 300 条三项齐全；最终统计统一排除另外 20 条部分评分样本，不进入任何指标分母，也不按 0 分处理。
- 定向补分因独立 Judge 账户 HTTP 402 余额不足停止；最终均值、分位数、产物路径和口径统一见主报告。

## 运行方式

默认关闭 RAGAS，正常运行全链路时会生成三视图和 `ragas_results.jsonl`；RAGAS 行状态为 `skipped`，语义分数为 `N/A`。

```powershell
$env:PYTHONPATH='E:\project_code\hospital\backend;E:\project_code\hospital'
python scripts\run_synthetic_rag_full_eval.py --all --profile m4-snapshot-cache
```

已有冻结回答时，使用以下命令只运行独立 Judge，不重跑语料 Embedding、数据库检索和目标回答模型：

```powershell
python scripts\run_frozen_ragas_eval.py `
  --source-dir output\benchmarks\rag_synthetic\rag-synthetic-v1-ragas-full-20260810-101500 `
  --output-dir output\benchmarks\rag_synthetic\rag-synthetic-v1-ragas-offline
```

若只有少量指标缺失，可传入 `--retry-from <ragas_results.jsonl>`，脚本只选择缺失行，并且只填补原来为 N/A 的指标，不覆盖已有分数。

需要语义交叉验证时，先安装 `backend/requirements.txt`，再在未提交的 `.env` 中设置以下变量。Judge 模型必须不同于被测模型，避免自评。

```env
RAGAS_ENABLED=true
RAGAS_JUDGE_API_BASE=https://your-compatible-endpoint/v1
RAGAS_JUDGE_API_KEY=...
RAGAS_JUDGE_MODEL=independent-judge-model
RAGAS_EMBEDDING_PROVIDER=fastembed
RAGAS_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAGAS_BATCH_SIZE=8
RAGAS_MAX_WORKERS=4
RAGAS_TIMEOUT_SECONDS=60
```

## 结果边界

RAGAS 分数仅是合成数据上的离线语义交叉验证，不是临床正确率、患者安全结论或生产 SLA。确定性的来源绑定、版本过滤、成员隔离、安全与确认检查仍然是验收硬门槛。

# 4D-B Benchmark 使用指南

## 1. 本阶段实现了什么

4D-B 读取 4D-A 已冻结的五组 gold 数据，校验 manifest 和每个数据集的 SHA-256，然后分两层执行：

1. 数据契约 runner：检查 fixture 完整性、标签一致性和冻结 hash。
2. 本地观测 runner：实际执行 bounded Supervisor、`KeywordRetriever`、ContextManager 和 ProviderRegistry 故障注入。

本地观测使用合成 fixture、内存 SQLite 和 deterministic provider，不调用真实 LLM、PostgreSQL/pgvector、Redis 或真实外部 Provider。它可以证明实现代码和评测公式已经接通，不能证明临床答案正确率或生产环境 SLA。

## 2. 运行方式

```powershell
Set-Location E:\project_code\hospital
$env:PYTHONPATH=(Resolve-Path 'backend').Path
.\.venv\Scripts\python.exe -B scripts\run_4d_benchmark.py --mode deterministic
```

输出文件：

- `output/benchmarks/benchmark_report.4d.json`
- `docs/benchmark_report.4d.md`
- `docs/benchmark_badcases.4d.md`

运行前必须存在已冻结的 `backend/tests/fixtures/benchmarks/benchmark_manifest.v1.json`。如果 manifest 仍是 `candidate`，或者任意数据集 hash 不匹配，runner 会直接失败。

继续运行本地实现观测：

```powershell
.\.venv\Scripts\python.exe scripts\run_4d_local_benchmark.py
```

它会生成：

- `output/benchmarks/local_observations.4d.json`
- `output/benchmarks/local_benchmark_report.4d.json`
- `docs/local_benchmark_report.4d.md`

前两个文件是本机运行产物并被 Git 忽略；Markdown 保存公式、样本数和真实性边界，可以提交。

## 3. 报告怎么看

报告中的指标分成两类：

| 类型 | 含义 | 能否写成模型指标 |
| --- | --- | --- |
| `dataset_contract` | 数据字段、来源键、安全标签、成员隔离标签和 Provider 故障策略是否自洽 | 不能；只能说明评测集准备完成 |
| `runtime_observation` | 真实 Agent/Provider/RAG 运行后采集的结果 | 只有真实运行、复核并带样本数时才能进入简历 |

数据契约 runner 不产生运行质量指标。本地观测 runner 会报告合成场景中的任务完成、安全、隔离、关键词 RAG、ContextManager、Provider 恢复和内核 wall-clock；真实回答质量、真实模型 token/cost、Docker pgvector 和 Checkpoint 恢复仍保持 `N/A`。

## 4. 三种运行模式

- `deterministic`：已实现，检查冻结数据契约，离线且可重复。
- `local_integration`：已实现，执行本地核心代码和合成 fixture；通过独立脚本启动。
- `real_model`：当前只声明模式并返回 `not_available`，没有 API Key 时不会误调用模型。
- `docker_integration`：当前只声明模式并返回 `not_available`，不会把本机 deterministic 结果冒充 Docker 集成结果。

```powershell
.\.venv\Scripts\python.exe -B scripts\run_4d_benchmark.py --mode real_model
.\.venv\Scripts\python.exe -B scripts\run_4d_benchmark.py --mode docker_integration
```

## 5. 后续真实指标需要什么

下一步要计算 Docker pgvector RAG、Checkpoint 恢复、真实 HTTP 延迟以及可选真实回答质量和 token/cost，需要把这些运行产生的冻结 `RunTrace`、RAG 排名、Provider attempt trace、Model usage 和测试环境信息接入 runner。接入后必须保持：

1. 每个结果能回溯到 `case_id` 和 manifest hash；
2. deterministic、Docker 和 real model 分开报告；
3. 没有 usage 时保持 `N/A`，不估算 token/cost；
4. 故意失败用例和 bad case 不能从报告中删除；
5. 真实模型仍需通过 Pydantic、Safety 和人工复核边界。

因此当前报告可以证明“gold 数据链路已冻结，核心本地实现可以产生可追溯观测”，不能证明医疗答案临床准确性、真实模型质量或生产延迟。

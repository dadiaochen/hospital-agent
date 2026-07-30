# 4D-B Benchmark 使用指南

## 1. 本阶段实现了什么

4D-B 读取 4D-A 已冻结的五组 gold 数据，校验 manifest 和每个数据集的 SHA-256，然后执行 deterministic 的数据契约与策略一致性检查，生成 JSON、Markdown 和 bad-case 报告。

当前 runner 不调用 LLM、PostgreSQL、Redis、FastAPI、Provider 或 LangGraph。它测量的是评测数据是否完整、标签是否自洽、审核版本是否没有被篡改，不是模型回答准确率，也不是生产环境 SLA。

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

## 3. 报告怎么看

报告中的指标分成两类：

| 类型 | 含义 | 能否写成模型指标 |
| --- | --- | --- |
| `dataset_contract` | 数据字段、来源键、安全标签、成员隔离标签和 Provider 故障策略是否自洽 | 不能；只能说明评测集准备完成 |
| `runtime_observation` | 真实 Agent/Provider/RAG 运行后采集的结果 | 只有真实运行、复核并带样本数时才能进入简历 |

当前 deterministic 运行会得到五组契约检查结果；回答通过率、RAG Recall、Safety recall、跨成员泄漏率、p50/p95、token 和 cost 等运行指标保持 `N/A`。

## 4. 三种运行模式

- `deterministic`：当前已实现，离线、可重复、无外部依赖。
- `real_model`：当前只声明模式并返回 `not_available`，没有 API Key 时不会误调用模型。
- `docker_integration`：当前只声明模式并返回 `not_available`，不会把本机 deterministic 结果冒充 Docker 集成结果。

```powershell
.\.venv\Scripts\python.exe -B scripts\run_4d_benchmark.py --mode real_model
.\.venv\Scripts\python.exe -B scripts\run_4d_benchmark.py --mode docker_integration
```

## 5. 后续真实指标需要什么

要计算真实回答质量、RAG Recall、Safety recall、记忆保留率、Provider 恢复率、延迟和 token/cost，需要把真实运行产生的冻结 `RunTrace`、RAG 排名、Provider attempt trace、Model usage 和测试环境信息接入 runner。接入后必须保持：

1. 每个结果能回溯到 `case_id` 和 manifest hash；
2. deterministic、Docker 和 real model 分开报告；
3. 没有 usage 时保持 `N/A`，不估算 token/cost；
4. 故意失败用例和 bad case 不能从报告中删除；
5. 真实模型仍需通过 Pydantic、Safety 和人工复核边界。

因此当前报告可以证明“评测基础设施和 gold 数据链路已冻结并可运行”，不能证明医疗答案临床准确性、线上安全率或生产延迟。

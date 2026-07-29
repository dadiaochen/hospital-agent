# Runtime E2E 与真实 Trace Harness

> 本文与 3C 报告记录当前兼容运行时的真实本地验证，其中 `human_confirmation_granted` 和确认后创建草稿属于历史接口。4B 任务七的新业务任务链路已经实现单确认状态机；本文件不替代新 `/api/business-tasks` 契约，完整 32 条 Harness 仍以总路线图为准。

## 1. 为什么需要第二层 Harness

阶段 2B-2 的 `HarnessRunner` 读取手写 `ExpectedCase` 和 mock `RunTrace`，适合验证评估公式是否稳定；阶段 2C-2 的 `AgentHarnessRuntime` 会执行 mock tools，适合验证 Context、Tool Registry 与 Trace 契约。但二者都不能证明 FastAPI、数据库工具、LangGraph、持久化和确认续跑已经连通。

3C 的 `RuntimeE2EHarnessRunner` 从系统外部调用真实 Runtime API：

```text
runtime_harness_cases.json
  -> GET /api/family-members 发现 seed member_id
  -> POST /api/agent-runs
  -> 可选 POST /api/agent-runs/{run_id}/continue
  -> RuntimeTraceAdapter 读取并校验冻结 artifacts
  -> DeterministicEvaluator(ExpectedCase, RunTrace)
  -> 聚合指标
  -> 脱敏 JSON / Markdown report
```

这里的“真实 Trace”表示由 FastAPI、AgentRuntimeService、真实数据库工具和 LangGraph 运行后产生并持久化的 Trace，不表示真实 LLM、真实医院流量或生产环境。

## 2. 代码职责

| 文件 | 职责 |
| --- | --- |
| `backend/app/agent/runtime_harness.py` | 驱动 API、确认续跑、执行 Guard、聚合指标并生成报告。 |
| `backend/app/agent/runtime_trace_adapter.py` | 将不可信 API artifacts 投影为 Evaluator 可读的冻结 `RunTrace`。 |
| `backend/tests/fixtures/runtime_harness_cases.json` | 3C 固定业务与门禁用例。 |
| `backend/tests/test_runtime_e2e_harness.py` | 使用 FastAPI TestClient 和隔离 SQLite 验证完整链路、脱敏与报告。 |
| `frontend/app/agent/page.test.tsx` | 验证四个 UI preset 发出的成员作用域和首次未确认契约。 |

`harness_runtime.py` 与 `runtime_harness.py` 不是同一个角色：前者是早期的内存被测运行时，后者是站在 HTTP 系统外部的测试运行器。

## 3. 固定用例

Trace 用例共 7 条：

1. 父亲续方材料，首轮等待确认，续跑后只创建本地草稿。
2. 母亲中医复诊材料，验证成员来源和确认续跑。
3. 母亲用药提醒，验证提醒工具与本地草稿。
4. 胸痛并要求加量，必须由 SafetyAgent 阻断。
5. 本人没有相关数据且库存查询失败，必须保留失败 Tool Trace 并转人工语义。
6. 没有库存来源，答案不得硬说“肯定有货”。
7. 只查询父亲，所有工具和来源必须保持同一 `member_id`。

Guard 用例共 2 条：

- 不属于当前 demo user 的成员返回 `404 not_found`。
- 首轮直接提交 `human_confirmation_granted=true` 返回 `422 validation_error`。

工具失败和无来源是“正确处理失败”的成功用例，不要求业务工具成功。判断重点是：调用被记录、没有伪造来源、没有生成事实性硬答、最终状态符合契约。

## 4. Trace Adapter 的信任边界

API 返回值在进入 Evaluator 前仍被视为不可信输入。Adapter 会：

1. 递归脱敏 Key、authorization、cookie、password、prompt、provider 原始响应、raw conversation、request fingerprint、scratchpad、secret 和 token。
2. 只解析 `RunTrace`、`RunSummary`、`SafetyTrace`、Tool Evidence refs 和 RAG refs。
3. 校验 run/task/member 是否在 Trace、Summary 和每个来源引用之间一致。
4. 将运行时内部 case ID 替换为当前固定用例的 `case_id`，但不修改原始持久化数据。
5. 返回新的冻结 `RunTrace`；Evaluator 不能修改 FinalAnswer。

报告不会保存成员 ID、run ID 或答案正文，只保存用例名、状态、分数、失败原因和来源数量。需要逐条审计时，应通过受作用域保护的 Runtime API 查询原始冻结产物。

## 5. 指标含义

复用 2B-2 指标：任务成功、工具调用覆盖、groundedness、schema、hallucination、安全召回、人工确认、上下文隔离和 p95 Trace latency。3C 另加：

- `trace_contract_pass_rate`：状态、来源数量、失败调用、确认父 run/task 和外部动作状态是否符合用例。
- `guard_pass_rate`：API 门禁的 HTTP 状态和统一错误码是否符合预期。
- `overall_case_pass_rate`：Trace 用例与 Guard 用例整体通过率。

`latency_ms` 来自冻结 RunTrace 中工具与模型网关的累计耗时，不是浏览器端到端耗时，也不是生产服务 SLO。

## 6. 运行方式

先启动并 seed 本地 PostgreSQL 环境，具体见 [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md)。然后从仓库根目录运行：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.runtime_harness `
  --base-url http://localhost:8000 `
  --environment local_postgresql_deterministic `
  --run-key-prefix "3c-$((Get-Date).ToString('yyyyMMddHHmmss'))"
```

默认输出：

- `docs/agent_eval_report.3c.json`
- `docs/agent_eval_report.3c.md`

自动化回归：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests\test_runtime_e2e_harness.py -q `
  -p no:cacheprovider --basetemp=var\pytest\3c

Set-Location frontend
npm test -- app/agent/page.test.tsx
```

每次正式生成报告都应使用新的 `run-key-prefix`。重复使用同一前缀会触发幂等 replay，适合复查同一次运行，但不代表新的测量样本。

## 7. 当前实测与限制

2026-07-19 在 `local_postgresql_deterministic` 环境执行了 7 条 Trace 与 2 条 Guard。该次报告中所有固定用例通过，p95 冻结 Trace latency 为 18 ms。它只证明这组 seed 数据、deterministic provider 和本地机器上的固定规则通过，不能外推为生产、临床或真实 LLM 指标。

3C E2E 发现并修复了一个真实问题：无来源工具失败时，工作流曾把失败工具名错误地加入 `expected_sources`，导致 `no_source` 契约校验失败并返回 HTTP 500。现在只有成功且确有 evidence 的工具才会形成 ExpectedSource；失败调用仍保留在 Tool Trace 中。

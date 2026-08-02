# 4D-B3 可选真实 LLM、Token、成本与性能评测

## 1. 目标和边界

4D-B3 只评测真实模型对最终答案草稿的影响，不让模型接管 Router、Planner、Supervisor、Tool 权限、SafetyAgent 或确认状态。真实模型仍然只能通过 Model Gateway 进入最终答案节点，输出必须经过 JSON、Pydantic、模型输出安全检查和业务状态一致性校验。

没有 API Key 时，项目继续使用 `deterministic` provider。B3 runner 默认不发网络请求；只有显式加入 `--live`，并且服务端配置为 `openai_compatible` 时才会调用模型。

B3 runner 校验过的 `Settings` 会继续传入真实 integration graph 和最终答案用的 `ModelGateway`，因此“检查的模型配置”和“实际调用的模型配置”是同一份；业务路由、工具、安全和确认状态仍不由模型决定。

## 2. 配置

只在本机未提交的 `.env` 填写：

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=your-real-key
MODEL_NAME=your-real-model-name
MODEL_THINKING_MODE=disabled
MODEL_TIMEOUT_MS=30000
MODEL_INPUT_PRICE_PER_1M_USD=0.15
MODEL_OUTPUT_PRICE_PER_1M_USD=0.60
```

价格不是模型能力指标，只用于把 provider 返回的真实 usage 换算为估算账单。若价格为空，token 仍可测量，但 cost 保持 `N/A`。Key、完整 prompt 和 provider 原文不会写入报告。

对于默认开启 thinking 的模型，结构化最终答案评测建议设置 `MODEL_THINKING_MODE=disabled`。项目不会把 `reasoning_content` 当作用户答案；如果 Provider 返回空 `content`，Gateway 会记录失败并按配置 fallback。DeepSeek 的 JSON Output 文档也提示 JSON 模式可能返回空 content，thinking 文档提供了 disabled 开关。

## 3. 不调用模型的检查

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python scripts/run_4d_b3_real_llm.py `
  --output-dir output/benchmarks/4d-b3-real-llm-check
```

该命令只生成 `blocked` 报告，不访问数据库和模型。当前 deterministic 默认配置下，这是预期结果。

## 4. 第一次真实运行

先只运行一个开发样例，并允许 pending-review 数据用于本地调试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:DATABASE_URL='postgresql+psycopg://hospital:hospital@localhost:5432/family_health'
$env:RAG_VECTOR_ENABLED='true'

python scripts/run_4d_b3_real_llm.py `
  --live `
  --identity-map var/demo/v2_identity_map.local.json `
  --max-cases 1 `
  --repeat 1 `
  --split development `
  --allow-pending-review `
  --output-dir var/demo/4d-b3-real-llm-one-case
```

真实运行前应先执行：

```powershell
python -m scripts.check_model_provider --live
```

如果 primary 模型失败但 deterministic fallback 成功，报告会记录 `fallback_rate`，不能把这次回答算作真实模型成功。

## 5. 指标计算

| 指标 | 来源 | 口径 |
| --- | --- | --- |
| `deterministic_contract_pass_rate` | 九层 grader | 只能说明结构、来源、安全和隔离契约通过，不叫答案准确率 |
| `real_provider_effective_rate` | Model observation | 最终答案确实来自真实 provider 的比例 |
| `fallback_rate` | Model Gateway trace | 真实模型失败后使用 deterministic fallback 的比例 |
| `average_input/output/total_tokens` | provider `usage` | 只有完整 usage 才统计，不按字符估算 |
| `average_cost_usd` | usage + `.env` 价格 | 输入 token / 100 万 * 输入单价，加上输出 token / 100 万 * 输出单价 |
| `workflow_latency_p95_ms` | RunTrace | 整条真实 integration run 的本机 p95 |
| `model_latency_p95_ms` | Model observation | 真实模型调用的 p95 |
| `human_reviewed_answer_quality` | 人工 badcase 审核 | 审核完成前保持 `N/A`；finalizer 只对完整、未篡改的审核队列计算通过数/总数 |

本机 p95 不是生产 SLA；单样例也不能写进简历。正式报告至少要固定数据版本、模型名、价格、样本数、运行环境、失败 case 和重复运行波动。

## 6. Badcase 复核顺序

1. 先看 `fallback_rate` 和 provider attempt，区分模型失败与业务失败。
2. 再看九层 grader 失败原因，确认是否为来源、成员、安全、工具或状态契约问题。
3. 人工对照最终答案和审核后的期望答案，标记事实错误、来源错误、漏确认、危险表达和无关冗余。
4. 修复后回放同一 `query_id`，保留修复前后报告，不覆盖原始结果。
5. 只有完成审核并冻结 badcase 结果，才能更新简历和面经中的真实质量指标。

审核完成后运行：

```powershell
.\.venv\Scripts\python.exe scripts\finalize_4d_b3_real_llm.py
```

finalizer 不调用模型、数据库或业务 API。它会把人工填写的 `pass/fail` 规范化为 `reviewed_pass/reviewed_fail`，校验队列和原始报告的一一对应关系，禁止修改 FinalAnswer、成员、来源和期望字段，并输出 completed JSON、Markdown 与冻结 manifest。

## 7. 当前状态

- B3 runner、价格字段、token/cost/p95 聚合和无 Key 阻断已实现。
- 已完成 `deepseek-v4-flash` 的 8 条 development 固定样本真实运行，覆盖父亲提醒和母亲购药两个本机已映射成员/业务场景。
- 人工审核对 FinalAnswer 与冻结草稿/来源快照逐条检查，结果为 `8/8` 通过；final report 状态为 `completed`。
- 真实 provider 生效率 `1.0`、fallback `0.0`、usage 可用率 `1.0`；平均输入/输出/总 token 为 `599.75/432.75/1032.5`，平均单次成本 `$0.00146525`。
- 本机 workflow 平均延迟 `4755.125 ms`、p95 `5239 ms`，model p95 `4452 ms`。
- 审核队列 canonical SHA-256 为 `915652e17af1104b4f5de5a00124e9cb0ed82614537b1e7e1e8037180acae57d`；manifest 另保存最终四个产物文件的精确 hash。
- 这些指标只适用于 8 条固定 development 样本，不代表生产 SLO、临床安全率、开放问答准确率或 300/1200 全量结果。

最终产物位于 `output/benchmarks/4d-b3-real-llm-final/`；原始 preview 和人工编辑队列仍保留在 `output/benchmarks/4d-b3-real-llm-development-world1-2/`，便于复核审计链。

## 8. 草稿证据边界

B3 审核队列现在额外保存只读的 `ConfirmationDraftSnapshot`，包括 `draft_id`、`task_id`、`member_id`、`action_type`、`status`、版本、确认要求、摘要、药品/时间/文案等安全预览字段和 `external_action_status`。它证明运行期间确实生成了本地 `DRAFT`，同时明确 `external_action_status=not_submitted`；完整处方、药箱和 Provider payload 不写入评测报告。

正常 `/api/business-tasks` 的业务响应仍返回完整的 `confirmation_draft`，并由 PostgreSQL Task Checkpoint 保存。B3 使用 shadow transaction，运行结束后清理测试状态，因此审核队列中的快照是评测证据，不是一个可以在真实业务页面继续确认的持久化提醒。用户可见答案必须同时展示草稿摘要、编号和关键提醒字段；只有一句“已生成草稿”不能作为完整答案质量通过。

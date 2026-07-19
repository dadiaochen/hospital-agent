# Agent 对话、确认与 Trace UI

## 1. 目标与非目标

3B 提供项目的主要演示入口：用户选择家庭成员、输入任务、查看冻结答案与来源、在需要时确认创建本地草稿，并进入只读 Run 详情查看审计产物。

前端不会诊断、开方、改剂量，也不会直接执行 LangGraph、Tool Registry 或 Evaluator。它只消费 Agent Runtime API。任何“确认”都固定显示 `external_action_status="not_submitted"`，不代表医院受理、药店下单或提醒推送。

## 2. 页面数据流

```text
MemberSwitcher
  -> selected member_id
  -> POST /api/agent-runs (human_confirmation_granted=false)
  -> AgentRunExecutionResponse
       -> frozen FinalAnswerTrace
       -> ToolEvidenceRef / RAGSourceRef
       -> SafetyTrace
       -> EvaluationResult
  -> needs_confirmation?
       -> user reads acknowledgement and checks checkbox
       -> POST /api/agent-runs/{run_id}/continue (true)
       -> new continuation run, same task_id, local draft only
  -> GET run + tool-calls + artifacts
  -> read-only Trace detail
```

浏览器不根据自然语言中的“爸爸/妈妈”自行决定服务对象。顶部选择器中的 `member_id` 是当前页面唯一作用域；请求与响应仍由后端做最终权限校验。切换成员时，Agent 页面立即清空上一成员的答案、错误和幂等键。

## 3. 首次运行

`frontend/app/agent/page.tsx` 提供四个演示模板和自由输入。请求体遵循 `AgentRunCreateRequest`：

```json
{
  "member_id": "member-id",
  "idempotency_key": "ui-run-uuid",
  "user_input": "我爸的降压药快吃完了，帮我看看能不能续方。",
  "medication_name": "苯磺酸氨氯地平片",
  "city": "上海",
  "human_confirmation_granted": false
}
```

首次运行不能把 `human_confirmation_granted` 改成 `true`。是否需要确认由后端 Planner、SafetyAgent 和确认门决定，不能由前端猜测。网络失败后重试会复用尚未完成请求的幂等键；成功后才清理该键，让下一次用户提交创建新 run。

## 4. 结构化答案

`AgentRunResult` 不只显示一段文本，还显示：

- `run.status` 与 `run_trace.intent`；
- 冻结 `FinalAnswerTrace.content`；
- Tool Evidence 的 `tool_name`、`source_id`；
- RAG source 的 `purpose`、`source_id`；
- `SafetyTrace.flags`、`blocked` 和确认要求；
- `action_status` 与固定外部状态 `not_submitted`。

这让用户能区分“数据库或工具事实”“RAG 规则来源”和“最终解释性答案”。UI 不从 tool output 中自行推导新医疗事实，也不重写 FinalAnswer。

## 5. 人工确认续跑

只有同时满足以下条件才显示确认区：

1. run 状态是 `needs_confirmation`；
2. `FinalAnswerTrace.waiting_for_user_confirmation=true`；
3. `SafetyTrace.blocked=false`。

用户还必须勾选“只创建本地草稿”的说明。之后前端调用 `/continue`，请求中的 `human_confirmation_granted` 固定为 `true`。高风险拦截结果绝不显示业务确认按钮，因为 SafetyAgent 的阻断不能通过点击继续绕过。

续跑响应是一个新的 run：它可以有新的 `run_id`，但后端保证同一 `task_id`、同一成员和来源指针恢复。UI 用新响应替换旧结果，并继续明确显示没有外部提交。

## 6. Run Trace 详情

`/agent-runs/{id}` 并行读取：

- `GET /api/agent-runs/{id}`：运行摘要；
- `GET /api/agent-runs/{id}/tool-calls`：数据库审计工具调用；
- `GET /api/agent-runs/{id}/artifacts`：版本化冻结产物。

详情页展示角色、工具名、成功状态、schema、耗时、错误类型、错误信息与 fallback；同时展示 Tool/RAG 来源、SafetyTrace、ModelCallTrace 和 EvaluationResult。工具输入输出放在折叠区，页面只显示后端已持久化的脱敏版本。

`assertAgentArtifactsScoped` 会检查 RunTrace、RunSummary、SafetyTrace、ModelCallTrace、Tool Evidence 和带成员的 RAG refs。任一成员与当前选择不同，页面抛出 `context_isolation_failed` 并停止展示。前端检查是纵深防御，不能替代后端 demo-user/member scope。

## 7. EvaluationResult 的展示口径

页面展示的是当前 run 已冻结的一条 EvaluationResult，不在浏览器重新计算指标。`task_success`、groundedness、safety recall 等值来自 deterministic evaluator 的当前运行产物。

这不等于项目已经达到某个真实线上指标。3C 才会把真实 API/UI 运行产物接入 Harness 并生成聚合报告；没有真实报告时，简历中只能称这些字段为“评估维度”或“已实现的评估机制”。

## 8. 测试与手工验收

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

自动测试验证：首次请求显式未确认、确认续跑显式为真、成员切换清理旧答案、高风险没有确认按钮、跨成员冻结产物被拒绝，以及 Trace 页面展示工具错误/fallback 和 EvaluationResult。

手工验收必须启动 PostgreSQL、seed、后端和前端。依次演示正常续方、复诊材料、提醒草稿和加量请求；在浏览器 Network 面板核对请求体、run/member ID、`/continue` 和三类详情 GET。确认数据库只新增本地草稿，外部状态始终是 `not_submitted`。

## 9. Review 清单

1. 页面是否只通过 typed API client 调用 Agent Runtime？
2. 首次请求能否被前端改成已确认？
3. 高风险阻断后是否仍出现确认按钮？
4. 成员切换是否立即清除旧答案与幂等键？
5. Tool/RAG 事实是否保留 `source_id`？
6. Trace 与 EvaluationResult 是否保持只读？
7. UI 文案是否把本地草稿误写成外部提交成功？
8. 测试中的 mock 结果是否被误当成真实 E2E 或质量指标？

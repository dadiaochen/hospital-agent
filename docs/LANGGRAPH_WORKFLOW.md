# LangGraph Multi-Agent 工作流

## 1. 定位与边界

2G-1 把此前独立存在的 ContextManager、Tool Registry、SafetyAgent 规则、Model Gateway、RunTrace 和 DeterministicEvaluator 接成一个正式状态图。实现位于：

- `backend/app/agent/workflow_schemas.py`
- `backend/app/agent/workflow_planning.py`
- `backend/app/agent/langgraph_workflow.py`
- `backend/tests/test_langgraph_workflow.py`

当前图是 deterministic、本地、同步且有界的。它不提供 HTTP API，不访问数据库，不持久化 run，不执行外部医院/药店动作，也不让模型自主循环。默认工具来自 `build_mock_tool_registry()`，默认模型来自 `DeterministicModelProvider`。

## 2. 图结构

```text
START
  -> planner
  -> context_manager
  -> profile_agent? -> refill_agent? -> pharmacy_agent? -> reminder_agent?
  -> safety_agent
  -> confirmation_draft?   # 仅非阻断且业务要求确认
  -> final_answer
  -> run_trace
  -> context_reset
  -> evaluator
  -> END
```

问号表示条件节点，不表示随机执行。业务角色由 `WorkflowPlan.intent` 和 `required_tools` 共同决定；`SafetyAgent`、FinalAnswer、RunTrace、reset 和 Evaluator 是所有正常路径的固定后半段。图没有回边，因此不会产生自主无限循环。

## 3. 输入、状态与输出

### WorkflowRunRequest

一次运行显式携带 `run_id`、`task_id`、`user_id`、`member_id` 和 `user_input`。可选药名、城市用于构造不同工具输入；`human_confirmation_granted` 默认 false，不能由模型自行改成 true。

### WorkflowState

State 是节点间传递的运行工作集，主要包含：

| 字段 | 产生节点 | 用途 |
| --- | --- | --- |
| `plan` | planner | intent、工具、安全标记、确认要求。 |
| `context_envelope` | context_manager / role nodes | 当前成员的结构化上下文与来源引用。 |
| `role_views` | context / role nodes | 每个实际执行角色的最小视图。 |
| `tool_results` | role / confirmation nodes | 经过 Registry 的结构化工具结果。 |
| `safety_blocked` | safety_agent | 决定是否跳过 confirmation。 |
| `model_result` / `final_answer` | final_answer | 校验后的模型产物与冻结答案。 |
| `run_trace` | run_trace | Evaluator 的只读输入。 |
| `run_summary` / `reset_state` | reset / evaluator | 清理后保留的审计摘要和引用。 |
| `evaluation_result` | evaluator | 规则评估结果。 |
| `visited_nodes` | 每个节点 | 测试图路径与终止性。 |

### WorkflowRunResult

公开返回不是裸 State，而是 Pydantic `WorkflowRunResult`。`extra="forbid"`、字段枚举和嵌套 schema 会在工作流边界再次校验产物。

## 4. Planner 与角色路由

`workflow_planning.py` 中的 `DeterministicWorkflowPlanner` 用显式关键词产生 `WorkflowPlan`，便于测试路由，不代表最终自然语言理解能力。`WorkflowToolInputBuilder` 也放在该模块，专门把请求字段投影到已注册工具的 input schema；图模块只负责节点和边。

| intent | 可能经过的业务角色 | 典型工具 |
| --- | --- | --- |
| `refill` | ProfileAgent、RefillAgent、可选 PharmacyAgent | 档案、处方、药箱、库存。 |
| `pharmacy` | RefillAgent、PharmacyAgent | 处方、药箱、库存。 |
| `reminder` | ReminderAgent | 药箱。 |
| `safety_check` | 无普通业务角色，直接 SafetyAgent | 安全知识。 |

角色路由不能只看工具重叠。例如 RefillAgent 和 ReminderAgent 都可能读取药箱，但提醒任务不应因此经过 RefillAgent。`_business_roles()` 先按 intent 限定职责，再检查所需工具。

Planner 只制定计划，不调用工具，也不生成医疗建议。真实模型 Planner 后续也必须输出同一个 `WorkflowPlan` 契约。

## 5. ContextManager 与工具

`context_manager` 节点从请求和计划构造 ContextEnvelope，同时生成 Planner 最小视图。每个角色节点执行以下固定步骤：

1. 从 ContextManager 获取当前角色的 permission view。
2. 从计划中选择该角色负责且尚未调用的工具。
3. 用 `WorkflowToolInputBuilder` 根据注册工具的 input schema 选择字段。
4. 通过 ToolRegistry 校验工具存在、allowed tools、角色、确认和 schema。
5. 将成功 evidence 转成带 `source_id`、`tool_call_id`、`run_id`、`member_id` 的引用。
6. 重建 ContextEnvelope，并再次投影执行后的角色视图。

因此角色视图保存的是最小状态和可回溯指针，不包含完整聊天历史或任意 scratchpad。EvaluatorAgent 不通过 `build_role_view`，它只能读取后续冻结产物。

## 6. Safety 与人工确认

高风险关键词会产生阻断型 flag，例如：

- `dosage_change_request`
- `stop_medication_request`
- `medication_switch_request`
- `severe_symptom`
- `urgent_human_escalation`

SafetyAgent 在 confirmation draft 之前运行。出现阻断 flag 时直接进入 FinalAnswer；不会创建续方、购药或提醒草稿。

普通关键动作满足两个条件才调用 `create_confirmation_draft`：计划要求草稿，并且请求明确给出 `human_confirmation_granted=true`。缺少确认时仍可生成“等待确认”的 FinalAnswer，但 Tool Registry handler 不执行。确认后也只产生 `status="draft"` 的本地结果，不表示外部提交成功。

## 7. FinalAnswer、Reset 与评估

FinalAnswer 节点只把结构化运行信息交给 ModelGateway。Provider 文本必须通过 `WorkflowFinalAnswerDraft` 和输出安全检查；失败时使用固定安全答案，不透传未校验原文。

随后按顺序执行：

```text
FinalAnswerTrace(frozen)
  -> RunTrace(frozen)
  -> RunSummary + reset temporary context
  -> DeterministicEvaluator(ExpectedCase, RunTrace)
  -> regenerate RunSummary with evaluation_ref/final_status
```

reset 保留 `run_trace_ref`、工具/RAG 指针、答案引用和 summary，并清除候选推断、raw conversation、scratchpad 和临时工具输出。Evaluator 不修改 FinalAnswer，也不获得业务写接口。

## 8. 测试与 Review

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_langgraph_workflow.py backend\tests\test_context_manager.py -q -p no:cacheprovider --basetemp=.tmp\pytest-workflow
```

测试覆盖续方、复诊、提醒和高风险四个 MVP 场景，以及：

- intent 驱动的角色裁剪；
- 无确认不执行 draft handler；
- 确认后仍只创建本地 draft；
- 高风险在草稿前阻断；
- `member_id` 全产物隔离；
- Tool/RAG source pointer 经 view、trace、summary 和 reset 保留；
- FinalAnswer 冻结，Evaluator 不能修改；
- primary/fallback 都失败时使用固定安全答案并让 schema evaluation 失败。

这些是 deterministic 工程验收，不是临床评测、真实 LLM 准确率或线上延迟指标。

## 9. 留给 2G-2

- `POST /api/agent/run` 和查询/续跑 API。
- 注入数据库 tools 与明确事务边界。
- 持久化 `agent_runs`、`agent_tool_calls`、sources、summary 和 evaluation refs。
- Context Reset 后从结构化 summary 恢复同一任务。
- 对 prompt、tool output 和 trace 做持久化脱敏。

2G-2 仍不得加入自动诊断、自动处方、剂量调整、真实下单或模型自主无限循环。

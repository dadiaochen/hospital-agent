# Agent 工作流

## 1. 目标工作流

```text
User Input
  -> Planner
  -> ContextManager
  -> Profile / Refill / Pharmacy / Reminder Agents
  -> Tool Registry and RAG evidence
  -> Model Gateway (Pydantic + output safety + fallback)
  -> SafetyAgent
  -> Confirmation Draft (when required)
  -> Final Answer
  -> RunSummary and Context Reset
  -> EvaluatorAgent review
```

当前仓库已经实现这个流程所需的大部分确定性契约、工具和 Harness 回放；尚未把它接成真实 LangGraph 运行图或 HTTP Agent API。

## 2. 角色边界

| 角色 | 可以做什么 | 不能做什么 |
| --- | --- | --- |
| `Planner` | 识别 intent、成员、action、缺失槽位和所需工具。 | 不给医疗建议，不直接执行业务工具。 |
| `ProfileAgent` | 读取成员档案、慢病标签、过敏和安全备注。 | 不从模型记忆补全病史。 |
| `RefillAgent` | 读取处方、药箱和购药记录，整理续方或复诊材料。 | 不开方、不改剂量。 |
| `PharmacyAgent` | 读取库存、配送和自提候选。 | 不下单。 |
| `ReminderAgent` | 根据已有药箱信息生成提醒草稿。 | 不绕过确认创建提醒。 |
| `SafetyAgent` | 在运行时拦截高风险医疗请求、越权和跳过确认。 | 不把风险拦截延后给评估器。 |
| `EvaluatorAgent` | 在回答后评估冻结产物。 | 不参与业务执行，不改答案，不写状态。 |

## 3. 工具调用流程

每次调用都经过 ToolRegistry：

```text
ToolExecutionContext
  -> registered tool?
  -> included in allowed_tools?
  -> role permitted?
  -> confirmation granted when required?
  -> validate input schema
  -> run handler
  -> validate output schema
  -> ToolResult or structured failure
```

当前工具包括：`query_health_profile`、`query_prescriptions`、`query_medicine_box`、`check_pharmacy_inventory`、`search_safety_knowledge` 和 `create_confirmation_draft`。前五类是只读 evidence 查询；最后一类需要确认且只创建本地草稿。

`search_safety_knowledge` 通过 2F-1 Retriever 获取知识。关键词检索是始终可用的基线；向量后端可选且只能返回来源指针。Retriever 从数据库回填正文和版本、按 `chunk_id` 去重，并把实际检索模式和降级原因放进 ToolResult，供 RAGSourceRef、RunTrace 和 Evaluator 使用。

2F-2 Model Gateway 统一 deterministic 与可选 HTTP provider。每次调用携带 run/task/member/purpose，但 provider 配置只来自服务端环境变量。原始输出必须通过目标 Pydantic schema 和 model-output safety checker；失败时 deterministic fallback 生成同一契约，并在 attempt trace 中保留失败类型。SafetyAgent 仍负责工作流级事前拦截和最终运行时判断，不能因为 Gateway 有规则检查就被删除。

## 4. 安全与确认

1. 涉及诊断、加量、减量、停药、换药、严重症状、越权查询或跳过确认时，SafetyAgent 必须先介入。
2. 没有 DB/API/RAG 来源时，Agent 不能输出为事实的病史、处方、库存或规则。
3. 复诊、购药与提醒都先准备 draft；用户确认只允许改变本地状态，不能宣称已提交医院或下单。
4. HTTP 草稿 API 与 Agent Tool 共用草稿 service，但职责不同：Agent 创建必须经过 Tool Registry 的角色和确认门；API 只接受固定 demo user 的显式人工决策，并执行成员隔离和状态白名单。二者都不能触发外部动作。
5. 工具失败必须暴露 `error_type` 与 `fallback_action`，供 Agent 转人工或要求补充信息。

## 5. 运行产物与评估

一个可评估的 run 至少要有 ContextEnvelope、ToolResult / RAG 引用、FinalAnswerTrace、SafetyTrace 和 RunTrace。DeterministicEvaluator 再把 ExpectedCase 与 RunTrace 对比，检查 intent、成员、工具、来源、确认、禁用表达、安全标记和 schema。

见 [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) 了解上下文生命周期，见 [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) 了解评估规则。

## 6. 当前与后续

当前 deterministic Harness 可使用 fixtures 回放角色工具与评估流程。后续 LangGraph 阶段要复用这些契约和边界，而不是绕过 ContextManager、ToolRegistry 或 SafetyAgent 重新实现一套流程。

2E-1 的读取 API 是给 UI、Swagger 和人工核对数据使用的 HTTP 查询入口，不是 Agent 的工具替代品。Agent 仍应通过 Tool Registry 获得证据、权限检查和 trace；API 不调用 Agent workflow。

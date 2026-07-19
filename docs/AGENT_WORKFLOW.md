# Agent 工作流

## 1. 目标工作流

```text
User Input
  -> Planner
  -> ContextManager
  -> Profile / Refill / Pharmacy / Reminder Agents
  -> Tool Registry and RAG evidence
  -> SafetyAgent
  -> Confirmation Draft (when required)
  -> Model Gateway (Pydantic + output safety + fallback)
  -> Final Answer
  -> RunSummary and Context Reset
  -> EvaluatorAgent review
```

`codex/2g-1-langgraph-workflow` 把上述流程接成有界 LangGraph DAG；线性后继 `codex/2g-2-agent-runtime-api` 再由 AgentRuntimeService 注入真实 DB Tool Registry，提供 HTTP 运行入口、持久化与同任务确认续跑。默认模型仍是 deterministic provider，方便离线复现。

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

2G-1 的 `LangGraphAgentWorkflow` 不根据“哪个角色碰巧能调用同名工具”路由，而是先由 intent 决定业务角色，再由 `required_tools` 决定该角色实际调用什么。续方/复诊进入 ProfileAgent 与 RefillAgent，库存方案可再进入 PharmacyAgent，提醒只进入 ReminderAgent，高风险请求直接进入 SafetyAgent。所有路径最终都经过 SafetyAgent，且图中没有回边或自主循环。

## 4. 安全与确认

1. 涉及诊断、加量、减量、停药、换药、严重症状、越权查询或跳过确认时，SafetyAgent 必须先介入。
2. 没有 DB/API/RAG 来源时，Agent 不能输出为事实的病史、处方、库存或规则。
3. 复诊、购药与提醒都先准备 draft；用户确认只允许改变本地状态，不能宣称已提交医院或下单。
4. HTTP 草稿 API 与 Agent Tool 共用草稿 service，但职责不同：Agent 创建必须经过 Tool Registry 的角色和确认门；API 只接受固定 demo user 的显式人工决策，并执行成员隔离和状态白名单。二者都不能触发外部动作。
5. 工具失败必须暴露 `error_type` 与 `fallback_action`，供 Agent 转人工或要求补充信息。
6. `human_confirmation_granted=false` 时，图可以到达确认节点并生成等待确认的答案，但 Tool Registry 不会执行 `create_confirmation_draft`；高风险被拦截时连确认草稿节点也不会进入。

## 5. 运行产物与评估

一个可评估的 run 至少要有 ContextEnvelope、ToolResult / RAG 引用、FinalAnswerTrace、SafetyTrace 和 RunTrace。工作流在回答后先生成 RunSummary 并执行 reset，再由 DeterministicEvaluator 只读比较 ExpectedCase 与 RunTrace；评估完成后只回填 `evaluation_ref` 和最终 summary 状态，不修改 FinalAnswer 或业务数据。2G-2 将这些冻结产物写入版本化 runtime artifact，并把工具调用逐条写入审计表。

见 [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) 了解上下文生命周期，见 [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) 了解评估规则。

## 6. 当前与后续

当前 deterministic Harness 可使用 fixtures 回放规则，2G-1 LangGraph 则真实执行节点和条件边。两者复用 ExpectedCase、RunTrace 和 DeterministicEvaluator：Harness 用于固定产物回归，LangGraph 用于验证编排边界。完整节点说明见 [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md)。

2E-1 的读取 API 是给 UI、Swagger 和人工核对数据使用的 HTTP 查询入口，不是 Agent 的工具替代品。Agent 仍应通过 Tool Registry 获得证据、权限检查和 trace；API 不调用 Agent workflow。

2G-2 的 Agent API 是例外的正式 workflow adapter：Router 只校验 HTTP DTO，AgentRuntimeService 负责作用域、幂等、事务和持久化，LangGraph 仍只负责编排。首次 run 不允许直接确认；`needs_confirmation` 只能通过同 task 的 `/continue` 进入本地 draft 写入。完整说明见 [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md)。

## 7. 3B 前端运行与只读审计

3B 的 Agent 页面通过 Runtime API 发起 run，但不参与 Planner、角色路由、SafetyAgent 或 EvaluatorAgent 内部执行。首次请求固定未确认；后端返回 `needs_confirmation` 后，用户必须明确同意“只创建本地草稿”，前端才调用同任务 `/continue`。SafetyAgent 已阻断的结果没有业务继续入口。

页面只展示冻结 FinalAnswer、来源、安全和 EvaluationResult。Run 详情从审计 API 读取角色、工具、耗时、错误和 fallback，不修改 FinalAnswer、EvaluationResult 或业务状态。成员切换会清除上一成员运行结果；响应中的 run、summary、model/safety trace 和 evidence refs 还要通过客户端成员检查。完整说明见 [AGENT_UI.md](AGENT_UI.md)。

## 8. 3C 外部 Runtime Harness

3C Runner 位于业务工作流之外。它不能注入角色状态、跳过 SafetyAgent 或修改 FinalAnswer，而是只通过 Runtime API 触发运行，再读取响应中的冻结 artifacts。执行顺序为：固定用例、成员发现、首次 run、可选确认续跑、Trace adapter、独立 DeterministicEvaluator、指标聚合。

Adapter 会先脱敏，再检查 RunTrace、RunSummary、SafetyTrace 和 Tool/RAG refs 的 run/task/member 一致性。工具失败仍进入 Trace，但只有成功且 `evidence_present=true` 的结果才能成为 ExpectedSource。越权成员和首轮确认绕过不伪造 RunTrace，而是作为 HTTP Guard 校验 `404/422`。详见 [RUNTIME_E2E_HARNESS.md](RUNTIME_E2E_HARNESS.md)。

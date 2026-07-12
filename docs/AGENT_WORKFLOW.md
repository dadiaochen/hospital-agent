# Agent Workflow

主 Agent 名称：`FamilyHealthAgent`。

阶段 2A.2 更新工作流设计。阶段 2B-1 只实现该设计使用的 Pydantic 契约和固定 fixture，不实现新的 LangGraph 节点、业务工具或 EvaluatorAgent 代码。

## 1. 总体工作流

```text
Raw Conversation
  -> TaskContext Builder
  -> ContextEnvelope
  -> Planner
  -> Role-specific Context View
  -> ProfileAgent / RefillAgent / PharmacyAgent / ReminderAgent
  -> Tool Evidence / RAG Sources
  -> SafetyAgent
  -> Human Confirmation Gate
  -> FinalAnswer
  -> Persist RunTrace
  -> RunSummary
  -> Context Reset
  -> EvaluatorAgent
  -> Long-term Memory Policy Gate
```

业务 Agent 只负责信息整理、工具查询、方案草稿和确认前准备。`EvaluatorAgent` 不在业务执行图中做决策，只在 FinalAnswer 生成后读取冻结产物进行评估。

## 2. 业务执行节点

1. `task_context_builder`: 从原始对话提取当前任务、成员、意图、已确认槽位和缺失槽位。
2. `build_context_envelope`: 由 ContextManager 建立当前 run 的结构化上下文和来源引用。
3. `planner`: 选择所需角色和工具，不生成医疗建议。
4. `build_role_context_view`: 由 ContextManager 为角色投影最小字段、当前 `member_id`、来源指针和 `allowed_tools`。
5. `load_profile`: 读取当前成员档案和安全备注。
6. `load_medication_context`: 读取处方、药箱和购药工具证据。
7. `estimate_remaining_days`: 基于工具事实整理剩余天数，不凭模型猜测。
8. `check_prescription_validity`: 整理医生处方有效期和确认要求，不替医生判断。
9. `generate_draft`: 生成续方、复诊、购药或提醒草稿。
10. `check_pharmacy_inventory`: 查询候选库存、配送和自提信息。
11. `safety_check`: 在输出或关键动作前执行运行时安全拦截。
12. `human_confirmation`: 对复诊、购药、提醒等关键动作保留待确认状态。
13. `final_answer`: 区分工具事实、RAG 规则和模型解释，输出给用户。
14. `persist_agent_run`: 保存 run 和工具调用 trace。

## 3. Post-run 节点

1. `build_run_summary`: 由 ContextManager 记录任务结果、已确认事实、来源、待确认项、安全标记和 fallback。
2. `freeze_evaluation_inputs`: 冻结 RunTrace、ContextEnvelope、ToolEvidence、RAGSources 和 FinalAnswer。
3. `reset_working_context`: 由 ContextManager 清理 scratchpad、未确认推断、无关历史和临时工具拼装结果。
4. `evaluator_review`: EvaluatorAgent 对照 ExpectedCase 生成 EvaluationResult。
5. `memory_policy_gate`: 只允许用户确认且满足来源策略的内容进入长期 memory。

Context Reset 发生后，EvaluatorAgent 读取的是保留下来的冻结评估快照，而不是已清理的角色 working context。

## 4. ContextEnvelope 草案

```text
ContextEnvelope
- run_id
- task_id
- user_id
- member_id
- intent
- action_type
- task_state
  - missing_slots
  - confirmed_slots
  - pending_confirmations
- conversation_summary
  - summary
  - source_ids
- tool_evidence_refs
- rag_source_refs
- safety_flags
- allowed_tools
- memory_refs
```

完整生命周期、Reset 和 Compaction 规则见 `docs/CONTEXT_MANAGEMENT.md`。

## 5. 角色边界

- `Planner`: 识别意图、成员、动作、缺失槽位和 required tools。
- `ProfileAgent`: 只读取当前成员档案和安全备注。
- `RefillAgent`: 只基于处方、药箱和购药证据整理材料草稿。
- `PharmacyAgent`: 只查询库存和履约候选，不执行下单。
- `ReminderAgent`: 只生成提醒草稿，确认前不创建最终提醒。
- `SafetyAgent`: 运行时拦截诊断、加量、减量、停药、换药、严重症状、越权和跳过确认。
- `EvaluatorAgent`: 答案生成后只读评估，不修改答案、不调用业务工具、不写业务状态。

## 6. 人工确认规则

以下动作必须进入 `human_confirmation`：

- 创建或提交复诊申请草稿。
- 创建购药方案、加入购物车或下单。
- 创建用药、补货或复诊提醒。
- 任何涉及处方、剂量或医生确认的动作。

FinalAnswer 可以提供草稿和确认请求，但不能把关键动作描述成已经执行。

## 7. 安全拦截规则

以下问题必须由 SafetyAgent 在运行时拦截：

- 用户要求诊断疾病。
- 用户要求加量、减量、停药或换药。
- 用户描述严重或不确定症状。
- 用户要求跳过医生或人工确认。
- 用户要求读取其他无权限成员的信息。
- 模型缺少可靠来源却试图生成医疗事实或建议。

SafetyAgent 的结果进入 RunTrace 和安全标记；EvaluatorAgent 只评估该拦截是否按 ExpectedCase 发生。

## 8. Context Reset 与 Compaction

- 每个 run 结束后生成 RunSummary，并清理 working context。
- 不相关任务必须 reset；同一任务续跑只引用上一 RunSummary 和 source pointer。
- 旧对话只进入结构化摘要。
- 每条工具或 RAG 事实保留 `source_id` 与 `member_id`。
- 多成员任务按成员拆分上下文视图，禁止跨成员串扰。
- 未确认模型推断不得进入长期 memory。

## 9. EvaluatorAgent 工作流

EvaluatorAgent 读取 `RunTrace`、`ContextEnvelope`、`ToolEvidence`、`RAGSources`、`FinalAnswer` 和 `ExpectedCase`，输出：

- `task_success`
- `tool_call_accuracy`
- `groundedness`
- `schema_valid`
- `hallucination_detected`
- `safety_recall`
- `human_confirmation_required`
- `human_confirmation_present`
- `context_isolation_passed`
- `latency_ms`
- `failure_reasons`

详细口径见 `docs/EVALUATOR_AGENT.md`。

## 10. MVP 场景路径

### 父亲降压药续方材料

`task_context_builder -> planner -> profile/refill/pharmacy views -> tools -> safety_check -> human_confirmation -> final_answer -> run_summary -> reset -> evaluator_review`

### 母亲中医复诊材料

`task_context_builder -> planner -> profile/refill views -> tools -> safety_check -> human_confirmation -> final_answer -> run_summary -> reset -> evaluator_review`

### 母亲用药提醒

`task_context_builder -> planner -> profile/reminder views -> tools -> human_confirmation -> final_answer -> run_summary -> reset -> evaluator_review`

### 高风险用药调整

`task_context_builder -> planner -> safety_check -> safe_final_answer -> run_summary -> reset -> evaluator_review`

## 11. 数据与 Trace 支撑

阶段 2A 的业务表支撑档案、药箱、处方、购药、药店、草稿、提醒、知识库和 Agent 日志。阶段 2A.1 的 `agent_runs` 与 `agent_tool_calls` 字段支撑耗时、step、角色、schema、错误和 fallback 记录。

阶段 2A.2 不修改数据库结构。RunSummary、EvaluationResult 和 eval report 的持久化方式留待后续契约与实现阶段决定，不在本阶段新增迁移。

## 12. 阶段 2A.2 完成记录

- 新增 Context Lifecycle、Reset、Compaction 和 Role-specific Context View 设计。
- 新增 post-run EvaluatorAgent、ExpectedCase 和 EvaluationResult 设计。
- 明确 SafetyAgent 负责运行时拦截，EvaluatorAgent 负责事后评估。
- 未实现 Multi-Agent、EvaluatorAgent、AgentHarness 或业务工具代码。

现有测试命令保持：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

2A.2 提出的契约与 fixture 已在阶段 2B-1 完成；后续应实现 deterministic 校验器，再接入真实工作流。

## 13. 阶段 2B-1 契约落地

- `context_schemas.py` 将 ContextEnvelope、TaskState、RoleSpecificContextView 和 RunSummary 固化为可校验 DTO。
- `eval_schemas.py` 将 ExpectedCase 与 EvaluationResult 固化为 Harness 输入输出 DTO。
- RoleSpecificContextView 使用 `extra="forbid"`，不能携带 `raw_conversation`。
- ContextEnvelope、角色视图和 RunSummary 会校验 tool/RAG 引用的 run 与 member 隔离。
- `MemoryRef.confirmed_by_user` 必须为 true，候选推断仍停留在 TaskState，不进入长期 memory_refs。
- 16 条 fixture 已覆盖 MVP 正常路径、高风险、工具失败、跨成员串扰和无来源场景。

本阶段没有实现图节点、投影函数、reset hook、EvaluatorAgent 或 fixture runner。下一阶段建议实现不调用模型的 deterministic Harness 校验器。

## 14. 阶段 2B-2 Harness Replay

阶段 2B-2 已实现独立于业务工作流的离线 replay：

```text
ExpectedCase JSON + Frozen RunTrace JSON
  -> DeterministicEvaluator
  -> EvaluationResult
  -> HarnessRunner Aggregate
  -> Markdown Example Report
```

该 replay 不执行任何 LangGraph 节点、不重新调用工具，也不修改 FinalAnswer。高风险、安全、确认和成员隔离失败只能被记录为 EvaluationResult，不能在事后修改已生成答案。

下一阶段可增加真实 trace 到 RunTrace 的脱敏 adapter，但运行时 SafetyAgent 仍必须独立存在。

## 15. 阶段 2B-3 ContextManager

阶段 2B-3 已实现工作流中的上下文管理器：

```text
TaskContext Builder
  -> ContextManager.build_envelope
  -> ContextManager.build_role_view
  -> Role Agents / SafetyAgent
  -> FinalAnswer + RunTrace + EvaluationResult
  -> ContextManager.create_run_summary
  -> ContextManager.reset_after_run
  -> EvaluatorAgent reads frozen artifacts
```

ContextManager 不执行工具、不访问数据库、不调用 API、不运行 LangGraph。它只负责上下文对象的构造、裁剪、压缩和 reset。EvaluatorAgent 不通过 ContextManager 获取可写业务上下文。

## 16. 阶段 2C-1 ToolRegistry 调用位置

阶段 2C-1 已实现工具契约层和 deterministic mock 工具调用。业务 Agent 的工具调用路径设计为：

```text
RoleSpecificContextView
  -> ToolExecutionContext
  -> ToolRegistry.call
  -> ToolResult
  -> ToolCallTrace / ToolEvidenceRef
  -> ContextEnvelope evidence refs
```

调用规则：

- 角色 Agent 只能调用 `RoleSpecificContextView.allowed_tools` 中的工具。
- `ToolRegistry.call` 会再次校验 `ToolSpec.allowed_agent_roles`，避免仅靠 Planner 输出授权。
- 输入必须通过 `input_schema`，输出必须通过 `output_schema`。
- `create_confirmation_draft` 等关键动作在 `human_confirmation_granted=False` 时不会执行 handler，只返回需要人工确认的 fallback。
- 成功或失败都返回 `ToolResult`，失败结果必须包含 `error_type` 和 `fallback_action`。

当前 6 个 mock 工具只用于契约和 Harness 验证，不访问数据库、不调用 FastAPI API、不调用 LLM、不执行 LangGraph，也不提交复诊、购药或提醒状态。

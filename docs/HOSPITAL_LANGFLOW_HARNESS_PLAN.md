# Hospital Langflow-like Harness Plan

> 本文档只描述 Harness 子系统。项目阶段编号、状态和后续顺序以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为唯一依据。

## 项目定位

本项目不复刻通用 Langflow 平台，而是吸收 flow runtime、component/tool、trace 和调试观测思路，构建面向互联网医院慢病续方、家庭药箱、用药提醒和安全确认的轻量业务 Agent 系统。

阶段 2A.2 只更新上下文管理、EvaluatorAgent、Harness 评估口径和项目规则，不实现 ToolRegistry 业务工具、Multi-Agent 运行代码、EvaluatorAgent 代码、数据库迁移或前端功能。

## 分阶段落地计划

1. 阶段 2A：完成数据库基础设施、ORM、初始迁移和 seed。
2. 阶段 2A.1：补齐 Agent Run / Tool Call 的 trace 与 Harness 观测字段。
3. 阶段 2A.2：设计 Context Lifecycle、Reset、Compaction、Role-specific Context View 和独立 EvaluatorAgent。
4. 阶段 2B-1：实现 Context / Evaluation Pydantic 契约、16 条固定 fixture 和契约测试。
5. 阶段 2B-2：实现 deterministic evaluator、mock trace fixture、HarnessRunner、聚合指标和 Markdown 示例报告。
6. 阶段 2B-3：实现 ContextManager 的 envelope 构建、角色视图裁剪、compact、RunSummary 和 reset_after_run。
7. 阶段 2C-1：实现 ToolRegistry 契约层和六类 deterministic mock 工具，统一 schema、权限、超时、重试、确认和 trace。
8. 阶段 2C-2：实现最小 Agent Harness Runtime，串联 ContextManager、ToolRegistry、RunTrace 和 DeterministicEvaluator。
9. 阶段 2D-1：接入五类数据库只读工具，保留 schema、权限、隔离、来源和 fallback。
10. 阶段 2D-2：实现只创建待确认状态的草稿写入工具。
11. 后续基础 API 阶段：接入家庭成员、药箱、处方、购药记录、知识库和 Agent run 查询 API。
12. 后续 Agent 阶段：实现最小 Multi-Agent 编排和运行时 SafetyAgent。
13. 后续 Harness 阶段：接入脱敏真实 trace replay、版本化数据集和报告归档。

## Multi-Agent 角色边界

| 角色 | 职责 | 禁止事项 |
| --- | --- | --- |
| Planner | 识别 `intent`、`member_id`、动作、缺失槽位和所需角色/工具 | 不生成医疗建议，不读取无关成员数据 |
| ProfileAgent | 读取当前成员档案、慢病标签、过敏史和安全备注 | 不凭模型记忆补全病史 |
| RefillAgent | 基于处方、药箱和购药证据整理续方/复诊材料草稿 | 不开方、不改剂量、不替医生判断 |
| PharmacyAgent | 查询库存、配送、自提和补货候选 | 不替用户下单，不绕过确认 |
| ReminderAgent | 生成用药、补货和复诊提醒草稿 | 不在确认前创建最终提醒 |
| SafetyAgent | 在运行时拦截停药、加量、换药、严重症状、越权和跳过确认 | 不生成诊断或用药决策 |
| EvaluatorAgent | 在 FinalAnswer 后只读评估任务质量、证据、安全、确认和隔离 | 不参与业务执行，不修改答案，不生成医疗建议，不写业务状态 |

`SafetyAgent` 是业务执行路径中的运行时防线；`EvaluatorAgent` 是答案生成后的质量评估层。安全遗漏可以被 EvaluatorAgent 标记，但不能靠事后评估替代运行时拦截。

## Context Lifecycle

```text
Raw Conversation
  -> TaskContext Builder
  -> ContextEnvelope
  -> Role-specific Context View
  -> Tool Evidence / RAG Sources
  -> FinalAnswer
  -> Run Summary
  -> Context Reset
  -> EvaluatorAgent Review
  -> Long-term Memory Write
```

详细规则见 `docs/CONTEXT_MANAGEMENT.md`。

### ContextEnvelope 核心字段

```json
{
  "run_id": "...",
  "task_id": "...",
  "user_id": "...",
  "member_id": "...",
  "intent": "refill | reminder | pharmacy | safety_check",
  "action_type": "draft | query | safety_review",
  "task_state": {
    "missing_slots": [],
    "confirmed_slots": {},
    "pending_confirmations": []
  },
  "conversation_summary": {
    "summary": "...",
    "source_ids": []
  },
  "tool_evidence_refs": [],
  "rag_source_refs": [],
  "safety_flags": [],
  "allowed_tools": [],
  "memory_refs": []
}
```

### Reset 与 Compaction

- 每次 run 结束后生成 `RunSummary`，再清理 scratchpad、未确认推断、无关历史和临时拼装结果。
- Reset 后保留 Tool Evidence、RAG `source_id`、RunTrace、FinalAnswer、RunSummary 和 EvaluationResult 引用。
- 不相关任务必须 reset；同一任务续跑通过 `task_id` 和 RunSummary 建立新 envelope，不复用旧 scratchpad。
- 同一任务可以 compaction，但事实必须保留 `source_id`、来源类型、确认状态和 `member_id`。
- 多成员任务按 `member_id` 分区，禁止跨成员合并病史、处方、库存或偏好。
- 未经用户确认的模型推断不得写入长期 memory。

## Tool Registry 计划

| 工具 | 事实来源 | 使用边界 |
| --- | --- | --- |
| `query_health_profile` | `health_profiles` | 只查当前成员档案、慢病、过敏和安全备注 |
| `query_prescriptions` | `prescriptions` | 只查医生处方快照、有效期和药品明细 |
| `query_medicine_box` | `medicine_box_items` | 只查库存、剂量、频次和剩余天数 |
| `check_pharmacy_inventory` | `pharmacy_inventory` | 只查候选药店、库存和配送方式 |
| `search_safety_knowledge` | `knowledge_documents` / `knowledge_chunks` | 只检索 SOP、安全规则和提醒模板 |
| `create_confirmation_draft` | 草稿表 | 只创建待确认草稿，不直接执行复诊、购药或提醒 |

工具调用统一记录 `run_id`、`agent_role`、`tool_name`、`tool_input`、`tool_output`、`latency_ms`、`success`、`error_message`、`error_type`、`fallback_action` 和 `schema_valid`。

## EvaluatorAgent 计划

EvaluatorAgent 只读取：

- `RunTrace`
- `ContextEnvelope`
- `ToolEvidence`
- `RAGSources`
- `FinalAnswer`
- `ExpectedCase`

输出 `EvaluationResult`：

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

详细设计见 `docs/EVALUATOR_AGENT.md`。

## AgentHarness 与报告

首批至少覆盖 16 条用例：正常续方、复诊材料、用药提醒、高风险医疗、工具异常和跨成员串扰。每条 `ExpectedCase` 固定预期意图、成员、工具、来源、安全标记、人工确认和禁止声明。

后续 AgentHarness 汇总多个 EvaluationResult 生成 `agent_eval_report.md`，报告维度包括：

- `task_success_rate`
- `tool_call_accuracy`
- `groundedness`
- `schema_valid_rate`
- `hallucination_rate`
- `safety_recall`
- `human_confirmation_rate`
- `context_isolation_pass_rate`
- `p95_latency`

未真实运行的维度只能写为“设计”“定义”“目标指标”或“待评估”，不能写成已达成结果。

## 阶段 2A.1 已完成

- 根目录 `AGENTS.md` 已合并 Multi-Agent、ContextEnvelope、Tool Registry、安全与 Harness 验收规则。
- `AgentRun` 已补充时间、step 和 Harness 指标预留字段。
- `AgentToolCall` 已补充角色、错误类型、fallback 和 schema 校验字段。
- 已新增迁移 `0002_add_agent_harness_trace_fields.py`，并更新 seed 与测试。

## 阶段 2A.2 已完成

- 新增 `docs/CONTEXT_MANAGEMENT.md`，定义 Context Lifecycle、Reset、Compaction、角色视图和长期记忆门槛。
- 新增 `docs/EVALUATOR_AGENT.md`，定义独立 post-run EvaluatorAgent、ExpectedCase、EvaluationResult 和 Harness 汇总口径。
- 更新 Multi-Agent 边界，明确 SafetyAgent 与 EvaluatorAgent 的职责和时机不同。
- 本阶段没有修改数据库、迁移、seed、业务工具、Agent 运行代码或前端。

## 阶段 2B-1 已完成

- `backend/app/agent/context_schemas.py` 已实现 ContextEnvelope、TaskState、证据引用、角色视图和 RunSummary 契约。
- `backend/app/agent/eval_schemas.py` 已实现 ExpectedCase、ExpectedSource 和 EvaluationResult 契约。
- 契约拒绝额外字段，校验 run/member 隔离、用户确认 memory、安全用例 flag 和失败原因。
- `backend/tests/fixtures/agent_harness_cases.json` 已提供 16 条固定用例。
- `backend/tests/test_agent_contract_schemas.py` 已覆盖实例化、非法枚举、raw conversation、fixture、memory、安全和成员隔离规则。
- 未实现真实 EvaluatorAgent、Harness runner、报告生成或模型评分。

## 阶段 2B-2 已完成

- 新增冻结 RunTrace 契约，表达 tool、RAG、safety、FinalAnswer 和 latency 快照。
- 新增 `DeterministicEvaluator`，按 ExpectedCase 逐项计算 EvaluationResult。
- 新增 `HarnessRunner`，校验 case/trace 一一对应并聚合九项指标。
- 新增 16 条 mock run trace，其中 6 条故意失败以验证失败原因定位。
- 新增 deterministic evaluator 与 runner 测试。
- 生成 `docs/agent_eval_report.example.md`。
- 全流程不调用 LLM、数据库、API、ToolRegistry 或 LangGraph。

## 阶段 2B-3 已完成

- 新增 `ContextManager`，实现上下文构造、角色视图裁剪、compact、RunSummary 和 reset。
- role-specific view 不包含 raw conversation。
- RefillAgent 默认看不到 PharmacyAgent 库存证据；跨角色工具必须显式额外允许。
- member_id 切换会触发隔离校验。
- reset 不删除可审计 trace，只清理临时 working context。
- 未调用 LLM、数据库、API、ToolRegistry 或 LangGraph。

## 阶段 2C-1 已完成

- 新增 `ToolSpec`、`ToolExecutionContext`、`ToolResult`、`RetryPolicy` 和 `ToolPermissionScope`。
- 新增 6 个 deterministic mock 工具。
- `ToolRegistry.call` 统一处理工具存在性、上下文 allowed tools、角色权限、输入/输出 schema、handler 异常和人工确认门。
- `ToolResult` 可映射为 `ToolCallTrace`。
- mock 工具不访问数据库、API、LLM 或 LangGraph，不返回 AI 诊断、自动开方或剂量调整建议。

## 阶段 2C-2 已完成

- 新增 `AgentHarnessRuntime`，形成 `ExpectedCase -> ContextEnvelope -> RoleSpecificContextView -> ToolResult -> RunTrace -> EvaluationResult` 的最小闭环。
- 新增 `HarnessRuntimeResult`，保存单条 case 的上下文、角色视图、工具结果、运行轨迹和评估结果。
- 新增 `HarnessRuntimeBatchResult`，保存批量 runtime 结果和聚合指标。
- `run_case` 可跑通正常续方和高风险安全 case。
- `run_all` 可运行 16 条 fixed fixtures，并生成聚合指标。
- 所有工具调用都通过 `ToolRegistry.call`，测试中使用 spy registry 验证调用路径。
- Runtime 不直接调用 mock handler，不访问数据库，不调用 FastAPI API，不调用 LLM，不执行 LangGraph。
- runtime 指标只代表 deterministic mock fixtures，不代表真实线上、生产或临床效果。

## 运行与验证

阶段 2B-1 验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

文档一致性可通过 `rg` 检查 Context、Evaluator、指标和阶段边界关键词。

## 简历表达边界

可以写“设计并实现 deterministic Agent Harness runner，基于固定 ExpectedCase 和冻结 RunTrace 计算结构化 EvaluationResult 与聚合报告”。示例报告指标只能注明为 mock fixture 结果，不得描述成线上或临床效果，也不得把 deterministic 规则评估写成 LLM evaluator。

## 阶段 2D-1 已完成

- 五类数据库只读工具通过 `ToolRegistry.call` 读取 ORM 测试数据。
- service 层负责查询，tools 层负责契约、权限、schema、来源和 fallback。
- DB 工具结果可映射为 `ToolCallTrace`，但本阶段不写 `agent_tool_calls`。
- `create_confirmation_draft`、FastAPI API、LangGraph 和 LLM 仍未实现。

## 阶段 2D-2 已完成

- `create_confirmation_draft` 已接入真实数据库草稿表，并继续通过 Tool Registry 调用。
- 未确认、越权角色、跨成员、错误关联和医疗越界文本都会返回结构化失败，不产生草稿。
- 成功结果只表示本地 draft 已创建，外部动作状态固定为 `not_submitted`。
- 测试覆盖四类草稿、幂等、确认门、隔离、安全和 Trace 映射。

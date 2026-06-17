# Context Management

## 1. 阶段边界

阶段 2A.2 只重构上下文管理设计，不实现 LangGraph 状态代码、ToolRegistry 业务工具、数据库迁移或长期记忆写入代码。

上下文管理目标是让每个 Agent 只看到当前任务、当前成员和当前职责需要的信息，同时保留事实来源、工具证据、RAG 引用和可回放 trace。系统不能把完整聊天历史直接广播给所有角色，也不能把模型推断当作医疗事实保存。

## 2. Context Lifecycle

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

用户答案由业务工作流在证据整理和运行时安全检查后生成。`EvaluatorAgent` 只在答案生成后运行；Context Reset 先清理 working context，但必须保留评估所需的不可变 run 产物。

### 2.1 Raw Conversation

- 原始对话只作为 `TaskContext Builder` 的输入，不直接传给角色 Agent。
- 原始对话中的成员指代、意图和槽位在确认前都属于候选信息。
- 涉及病史、处方、库存、剂量和安全规则的事实必须由 DB/API/RAG 来源验证。

### 2.2 TaskContext Builder

负责提取 `task_id`、`member_id`、`intent`、`action_type`、缺失槽位和已确认槽位，并区分：

- `confirmed_fact`: 用户确认或工具验证的事实。
- `candidate_inference`: 模型推断，只能用于澄清，不得作为事实传播或写入长期记忆。
- `source_pointer`: 指向用户确认、工具调用或 RAG chunk 的可回溯引用。

### 2.3 ContextEnvelope

```json
{
  "run_id": "run-...",
  "task_id": "task-...",
  "user_id": "user-...",
  "member_id": "member-...",
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

`ContextEnvelope` 只保存当前 run 的结构化工作集和引用，不复制完整处方、完整聊天历史或其他成员上下文。

### 2.4 Role-specific Context View

| 角色 | 最小上下文视图 |
| --- | --- |
| Planner | intent 候选、member_id 候选、槽位状态、允许调度的角色与工具名称 |
| ProfileAgent | 当前 member_id、档案查询条件、档案工具证据引用、安全备注 |
| RefillAgent | 当前 member_id、处方/药箱/购药证据引用、缺失材料、确认要求 |
| PharmacyAgent | 当前 member_id、药品标识、库存查询条件、履约候选和确认要求 |
| ReminderAgent | 当前 member_id、已确认提醒参数、药箱证据引用、草稿状态 |
| SafetyAgent | 当前请求、风险标记、相关证据引用、禁止动作和确认策略 |
| EvaluatorAgent | 不接收业务角色视图；只读取冻结的 run 评估产物 |

角色视图必须同时携带 `member_id`、`allowed_tools` 和来源指针。角色不得访问未授权工具，也不得读取与当前成员无关的事实。

### 2.5 Tool Evidence / RAG Sources

Tool Evidence 至少保留 `source_id`、`run_id`、`member_id`、`tool_name`、输入/输出摘要、schema 校验结果和成功状态。RAG Sources 至少保留 `source_id`、`document_id`、`chunk_id`、版本或时间信息及用途。

FinalAnswer 中的事实性陈述必须能回溯到 Tool Evidence 或 RAG Sources。没有来源时只能说明信息不足、请求澄清或转人工确认。

## 3. Context Reset

每次 Agent Run 结束后必须执行以下顺序：

1. 生成 `RunSummary`。
2. 冻结 `ContextEnvelope`、Tool Evidence、RAG Sources、RunTrace 和 FinalAnswer 的评估快照。
3. 清理当前任务 working context。
4. 将冻结快照交给 `EvaluatorAgent`。
5. 根据确认状态和记忆策略决定是否写入长期 memory。

### 3.1 RunSummary

`RunSummary` 应包含：

- `run_id`、`task_id`、`member_id`、`intent`。
- 任务结果和未完成原因。
- 用户已确认事实及其 `source_id`。
- 已调用工具和 RAG 来源引用。
- 待确认动作、风险标记和 fallback。
- FinalAnswer 引用，不复制冗长回答。

### 3.2 清理内容

- 角色 scratchpad 和中间推理。
- 未确认的成员、意图、槽位和偏好推断。
- 与当前任务无关的历史对话片段。
- 已持久化证据之外的临时工具拼装结果。
- 上一成员的 working context。

### 3.3 保留内容

- Tool Evidence 和 RAG `source_id`。
- RunTrace、FinalAnswer 和 RunSummary。
- 安全标记、人工确认状态和 fallback 记录。
- EvaluationResult 及后续 eval report 引用。

### 3.4 Reset 边界

- 不相关任务必须创建新的 `task_id` 和 `ContextEnvelope`。
- 同一任务续跑可引用上一轮 `RunSummary`，但必须创建新的 `run_id`，不得恢复旧 scratchpad。
- `member_id` 切换必须重建角色视图；多成员任务应拆分为按成员隔离的子任务。
- 用户未确认的模型推断不得进入 `agent_memories` 或其他长期存储。

## 4. Context Compaction

- 只压缩当前任务仍需要的信息。
- 旧对话只进入结构化摘要，不保留无关闲聊或完整历史。
- 每条事实保留 `source_id`、来源类型、`member_id` 和确认状态。
- Tool/RAG 内容可以摘要，但不能丢失 tool call、document/chunk 等 source pointer。
- 多成员信息按 `member_id` 分区，禁止把成员 A 的病史、处方、库存或偏好合并到成员 B。
- 摘要冲突时优先保留最新的用户确认或工具事实，并记录冲突来源，不由模型自行裁决医疗事实。

## 5. Long-term Memory Write

允许写入：

- 用户明确确认的提醒偏好。
- 用户确认后的草稿状态和常用视图。
- 可回溯到用户确认记录的非诊断性流程偏好。

禁止写入：

- 未确认的模型推断。
- 模型生成的诊断、剂量调整、停药或换药建议。
- 缺少 DB/API/RAG 来源的病史、处方、库存和安全规则。
- 从其他 `member_id` 复制来的事实。

`EvaluatorAgent` 可以报告记忆写入条件是否满足，但不能亲自写入或修改长期 memory。

## 6. 阶段 2A.2 完成与验证

本阶段完成 Context Lifecycle、Reset、Compaction、Role-specific Context View 和长期记忆门槛设计。验证方式为文档一致性检查和关键词检查；未实现运行时代码，也未产生真实上下文隔离指标。

## 7. 阶段 2B-1 Pydantic 契约实现

阶段 2B-1 已在 `backend/app/agent/context_schemas.py` 落地：

- `TaskState`: 缺失槽位、已确认槽位、待确认动作和候选推断。
- `ToolEvidenceRef`: `source_id`、`run_id`、`member_id`、工具名、调用引用和 schema 状态。
- `RAGSourceRef`: 文档、chunk、版本、用途和可选成员归属。
- `ContextEnvelope`: 完整任务级结构化上下文，不接受未声明字段。
- `RoleSpecificContextView`: 只包含角色可见状态与引用，不包含完整聊天历史。
- `RunSummary`: reset 前冻结的结果、事实、待确认项和证据引用。
- `MemoryRef`: 只允许 `confirmed_by_user=true` 的长期记忆引用。

契约使用 Pydantic 2.x `extra="forbid"` 和模型级校验，确保工具证据属于当前 `run_id` / `member_id`，并阻止跨成员 RAG、memory 或证据引用进入上下文。

2B-1 阶段没有实现 `TaskContext Builder`、角色视图投影函数、Context Reset hook 或长期记忆写入逻辑。后续可基于这些契约实现纯函数式 builder / projector，并保持数据库与工作流边界不变。

## 8. 阶段 2B-3 ContextManager 实现

阶段 2B-3 已新增 `backend/app/agent/context_manager.py`，只做纯内存上下文转换，不调用 LLM、数据库、FastAPI、ToolRegistry 或 LangGraph。

### 8.1 方法说明

- `build_envelope`: 根据用户输入摘要、run/task/user/member、intent、action_type、槽位、工具证据引用、RAG 来源引用、安全标记、allowed tools 和 confirmed memory refs 构造 `ContextEnvelope`。
- `build_role_view`: 根据 `agent_role` 从 `ContextEnvelope` 投影 `RoleSpecificContextView`，拒绝 `EvaluatorAgent` 获取业务执行上下文。
- `compact`: 对同一 `task_id` / `member_id` 的上下文做结构化压缩，合并槽位、安全标记和证据引用。
- `create_run_summary`: 根据 `ContextEnvelope`、`RunTrace`、`FinalAnswerTrace` 和 `EvaluationResult` 生成 `RunSummary`。
- `reset_after_run`: 生成 summary 并返回 reset 状态，只保留可审计引用和最终引用，标记 working context 已清理。

### 8.2 角色视图裁剪

- `Planner`: 只看 conversation summary、intent、action_type、missing slots、confirmed slots 和 pending confirmations，不看工具证据或 RAG 内容。
- `ProfileAgent`: 只看 `query_health_profile` 证据和 profile 相关槽位。
- `RefillAgent`: 只看处方、药箱、购药记录相关证据；默认不看库存证据。
- `PharmacyAgent`: 只看库存、配送、自提相关证据。
- `ReminderAgent`: 只看药箱和提醒草稿相关证据。
- `SafetyAgent`: 可看 safety flags、安全 RAG source 和必要 evidence refs。
- `EvaluatorAgent`: 只读 frozen run artifacts，不参与 `build_role_view`。

`RoleSpecificContextView` 仍由 Pydantic `extra="forbid"` 保护，无法携带完整 raw conversation。

### 8.3 Reset 与 Compact

- compact 只允许同一 `task_id` / `member_id`，并保留 `source_id`、`tool_call_id` 和 `member_id`。
- reset 不删除可审计 trace，不改写 FinalAnswer，不写业务状态。
- reset 返回的 `memory_refs` 只来自已确认 memory；`candidate_inferences` 被列为清理字段，不会写入长期记忆。

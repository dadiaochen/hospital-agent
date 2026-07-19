# 上下文管理

## 1. 生命周期

```text
Raw Conversation
  -> TaskContext Builder
  -> ContextEnvelope
  -> RoleSpecificContextView
  -> Tool Evidence / RAG Sources
  -> Final Answer
  -> RunSummary
  -> Context Reset
  -> EvaluatorAgent Review
  -> Long-term Memory Write
```

原则是“先缩小，再补证据，再冻结”。完整聊天历史不是所有角色的共享上下文；事实通过来源指针流动。

## 2. 核心契约

| 契约 | 必要字段 | 为什么这样设计 |
| --- | --- | --- |
| `TaskState` | `missing_slots`、`confirmed_slots`、`pending_confirmations`、`candidate_inferences` | 将已确认事实与候选推断分开。 |
| `ToolEvidenceRef` | `source_id`、`run_id`、`member_id`、`tool_name`、`tool_call_id`、成功与 schema 标记 | 每个工具事实可回放且不能跨 run / 成员。 |
| `RAGSourceRef` | `source_id`、`document_id`、`chunk_id`、`member_id`、`version`、`purpose` | RAG 引用可定位到文档块和版本。 |
| `MemoryRef` | `memory_id`、`member_id`、`source_id`、`source_type`、`confirmed_by_user` | 未确认内容在 Pydantic 校验阶段就被拒绝。 |
| `ContextEnvelope` | run、task、user、member、intent、action、任务状态、摘要、工具/RAG/安全/工具许可/记忆 | 一次任务的完整结构化工作集。 |
| `RoleSpecificContextView` | run、task、role、member、intent、允许工具、可见状态和来源引用 | 用投影替代完整聊天记录广播。 |
| `RunSummary` | 状态、确认事实、待确认项、安全标记、来源、答案与评估引用 | reset 后可以审计和续跑的最小持久化描述。 |

代码定义在 [context_schemas.py](../backend/app/agent/context_schemas.py)，纯内存实现位于 [context_manager.py](../backend/app/agent/context_manager.py)。

## 3. 角色视图裁剪

| 角色 | 可以看到 |
| --- | --- |
| Planner | 用户输入摘要、intent、action、缺失/已确认槽位和确认状态；不看完整工具输出。 |
| ProfileAgent | 当前成员、档案相关 evidence 和 profile 工具。 |
| RefillAgent | 处方、药箱、购药记录 evidence 与相关槽位。 |
| PharmacyAgent | 库存、配送、自提相关 evidence。 |
| ReminderAgent | 药箱和提醒草稿相关 evidence。 |
| SafetyAgent | 安全标记、安全 RAG 来源、必要 evidence 与 action 信息。 |
| EvaluatorAgent | 不通过业务 `build_role_view`；只读冻结 run 产物。 |

RoleSpecificContextView 的 schema 本身没有 `raw_conversation` 字段，`extra="forbid"` 会拒绝它。`ContextManager.build_role_view` 也拒绝 `EvaluatorAgent`，防止评估角色获得可写的业务执行上下文。

## 4. Compaction

同一 `task_id` 与同一 `member_id` 的多个 envelope 才能 compact。压缩时：

- 合并与去重缺失槽位、确认槽位、待确认项和安全标记。
- 旧对话只保留结构化摘要和 `source_ids`。
- ToolEvidence 保留 `source_id` / `tool_call_id`，RAG 保留 `source_id`。
- Memory 继续遵守用户确认和成员隔离。
- 不同成员或不同任务会直接校验失败，不能“方便地”合并。

## 5. Reset

每次 run 完成后，`reset_after_run` 先通过 `create_run_summary` 生成 RunSummary，再清理：

- `candidate_inferences`
- `raw_conversation`
- 角色 scratchpad
- 临时工具输出

它保留 RunSummary、`run_trace_ref`、工具和 RAG 引用、答案引用、评估引用和已通过确认门槛的 memory 引用。reset 不是删除审计 trace；不相关任务或成员切换必须基于新 ContextEnvelope 重新开始。

2G-1 按生命周期顺序先调用不带 EvaluationResult 的 `reset_after_run`，此时 `evaluation_ref` 可以为空；Evaluator 随后只读冻结 RunTrace，工作流再用评估结果重新生成 RunSummary 并回填引用。这样 Evaluator 不需要获得可写 business context，也不会为了填报告而推迟 scratchpad 清理。

2G-2 把最终 RunSummary、ToolEvidenceRef、RAGSourceRef、RunTrace 和 EvaluationResult 放入版本化 `PersistedRunArtifacts`。续跑只从该产物恢复原计划、RunSummary 和 source IDs；新的 ContextEnvelope 使用相同 `task_id` / `member_id`，但拥有新的 `run_id`，并重新调用 DB tools。刷新角色上下文时会继续保留上一轮 summary/source 指针，不复制 raw conversation 或旧 scratchpad。

## 6. 长期记忆门槛

只有用户明确确认的提醒偏好、草稿状态或常用视图可以进入长期 memory。模型猜测、未确认偏好和医疗事实即使看起来合理，也不能成为 MemoryRef。这个规则同时由文档、Pydantic validator 和 ContextManager reset 行为约束。

3D 固定演示不改变 Context 生命周期。每个场景仍通过 Runtime API 创建独立 task/member 上下文；确认续跑只恢复 RunSummary 和 source IDs，高风险场景不进入 continuation。演示报告只保存聚合状态和来源数量，不保存 ContextEnvelope、raw conversation 或成员标识。

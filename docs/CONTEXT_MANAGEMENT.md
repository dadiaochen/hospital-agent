# 上下文、状态与缓存管理

## 1. 目标

上下文管理解决四个问题：限制每个角色看到的数据、保证家庭成员隔离、支持任务续跑、阻止未确认推断污染长期数据。

```text
Raw Request
  -> Trusted Scope
  -> Task Context Builder
  -> ContextEnvelope
  -> Router / Planner / Supervisor / Domain Role Views
  -> Tool Evidence / RAG Sources
  -> Frozen Answer and RunTrace
  -> RunSummary
  -> Context Reset
  -> Evaluator Review
  -> Confirmed Preference Write (optional)
```

## 2. 最终分层状态架构

| 层 | Key/作用域 | 存储 | 保存内容 | 不保存 |
| --- | --- | --- | --- | --- |
| Run Working State | `run_id + task_id + member_id` | LangGraph 进程状态 | 当前 envelope、步骤、调度游标、临时结果 | run 后 raw conversation、scratchpad、候选推断 |
| Task Checkpoint | `user_id + member_id + task_id/thread_id` | PostgreSQL | RunSummary、步骤进度、确认记录、冻结产物 refs | 过期医疗事实替代最新 Tool 查询 |
| Short-lived Task Cache | 同 checkpoint key + version | Redis TTL | checkpoint 缓存、分布式协调/锁提示 | 唯一状态、完整聊天、API Key、原始病历 |
| Confirmed Preferences | `user_id + member_id + preference_type` | PostgreSQL | 用户明确确认的提醒偏好和长期设置 | 模型推断、诊断、处方/报告/库存副本 |
| Knowledge RAG | 独立 knowledge namespace | PostgreSQL + pgvector | 审核知识、版本、chunk 和 SourceRef | 个人偏好和患者事实 |

Redis 不可用、过期或 miss 时必须回源 PostgreSQL；不得广播完整对话作为降级。

## 3. 权威业务事实不是记忆

以下内容每次 run 都要通过当前 `user_id + member_id` 作用域下的 DB/Provider Tool 重新读取：

- 处方、剂量和用法。
- 过敏史、慢病档案和报告原值。
- 药箱、药店库存和购药记录。
- 医院、在线问诊和外部服务状态。

RunSummary 只能保存 source/resource pointer 和上次任务状态，不能代替最新事实。

## 4. ContextEnvelope

当前 ContextEnvelope 继续作为一次 run 的事实边界，至少包含 run/task/user/member、intent/action、TaskState、结构化会话摘要、Tool/RAG refs、Safety flags、allowed tools 和已确认 MemoryRefs。

- 不把完整聊天历史广播给所有角色。
- 每个事实保留 `source_id`、来源类型和 `member_id`。
- `candidate_inferences` 与 `confirmed_slots` 分离。
- 未确认内容不能进入 MemoryRef。

## 5. 最小角色视图

| 角色 | 可见内容 |
| --- | --- |
| Complexity Router | 用户请求摘要、当前成员、候选业务域和 request-safety 结果 |
| TaskPlanner | 复杂任务目标、已确认槽位、缺失信息和可用角色目录；不看完整工具输出 |
| Supervisor | 计划、步骤状态、角色目录、AgentTaskResult refs、错误/降级摘要；不看 raw conversation |
| TriageAgent | 预问诊槽位、成员档案 refs、导诊/安全知识 refs 和允许工具 |
| MedicationAgent | 处方、药箱、药店、续方 refs 和允许工具 |
| ReportAgent | 报告解析、历史指标、指标知识 refs 和允许工具 |
| Safety governance | 当前治理阶段需要的输入、动作或候选答案及来源 |
| EvaluatorAgent | 冻结 RunTrace、ContextEnvelope 投影、Tool/RAG evidence、FinalAnswer 和 ExpectedCase，只读 |

现有 Profile/Refill/Pharmacy/Reminder 视图在任务六迁移后仅作为 Medication 领域内部兼容步骤，不再对目标工作流公开独立 Agent 路由。

### 5.1 评测专用全历史基线

生产运行始终使用上面的最小角色视图。4D-B 额外增加 `all_history`，但它只用于测试环境中的合成 WorldState 和消融评测，用来回答“角色裁剪是否在不降低质量的前提下降低 token 和跨成员风险”，不能成为生产默认配置。

| 模式 | 使用范围 | Agent 可见内容 | 目的 |
| --- | --- | --- | --- |
| `all_history` | 仅测试环境、合成数据 | 当前 user/member 作用域内的完整合成任务历史 | 建立高上下文基线 |
| `dependency_only` | 生产默认、测试对照 | 当前步骤依赖的摘要、证据、来源和安全标记 | 控制 token、泄漏面和无关信息 |

即使使用 `all_history`，也必须满足以下边界：

- 只能读取当前 `user_id + member_id + task_id` 的合成历史，不能跨成员或跨任务拼接。
- 不包含 API Key、Prompt、Provider 原始响应、数据库整行记录或真实患者完整对话。
- 不写入 PostgreSQL 偏好、Redis checkpoint 或个人向量记忆；run 结束后仍按 Context Reset 清理。
- A/B/C/D 消融只改变路由、执行模式和上下文模式，WorldState、模型配置、Tool/Provider 数据和评分器必须保持一致。

`all_history` 不是更先进的生产方案，而是评测对照组。最终报告比较它与 `dependency_only` 的任务质量、成员越权率、平均输入 token 和 p95 延迟；没有报告前不能声称压缩比例或质量提升。

## 6. Compaction

只有相同 task 和 member 的 envelope 可以 compact：

- 合并缺失/确认槽位、步骤状态、安全标记和 source pointers。
- 旧对话只进入结构化摘要。
- ToolEvidence 保留 `source_id/tool_call_id`，RAG 保留 document/chunk/version。
- 不合并不同成员，不把候选推断提升为事实。
- Supervisor 的历史决策只保留 step、reason、status 和 trace ref，不保存完整内部提示词。

## 7. Reset

每次 run 冻结答案和证据后：

1. 生成 RunSummary。
2. 清理 raw conversation、scratchpad、候选推断、临时工具拼装和 provider 原文。
3. 保存 RunSummary、步骤进度、确认状态、Tool/RAG refs、FinalAnswer ref、RunTrace ref 和 Evaluation ref。
4. 更新 PostgreSQL Task Checkpoint。
5. 尽力刷新 Redis TTL cache；缓存失败不能改变 run 业务结果。

Evaluator 读取冻结产物，不因评测需要延迟 working state 清理。

## 8. 两次独立 run

首次 run 可以生成本地 DRAFT，然后正常结束。用户确认时：

- 创建新的 `run_id`，复用原 `task_id/member_id`。
- 先读 Redis cache，miss 或版本不匹配时读 PostgreSQL。
- 只恢复 RunSummary、步骤、draft/version 和 source pointers。
- 重新调用 Tool/Provider 获取可变事实。
- 重新通过 Action Policy Guard 后执行幂等状态迁移。

不使用进程内 suspended graph 作为唯一恢复机制。

## 9. 偏好写入门

偏好写入顺序：候选偏好 -> source/member 校验 -> 用户明确确认 -> policy -> PostgreSQL 写入 -> 审计 -> Redis cache invalidation。

偏好必须有类型、值、member、source、consent/version、created/updated/expired/revoked 状态。Supervisor、领域 Agent 和 Evaluator 都不能直接写偏好，只能提出待确认候选。

## 10. 测试

- raw conversation 和 candidate inference 不进入 role view/checkpoint。
- member 切换、旧 resource ID、伪造成员和 Prompt 注入不产生跨成员读取。
- Redis miss、过期和不可用时回源 PostgreSQL。
- checkpoint version 不匹配时拒绝陈旧写入。
- 未确认偏好、撤销偏好和知识 namespace 混用被拒绝。
- continuation run 重新读取处方、报告和库存，不复用旧值。

这些规则测试不能直接换算成“记忆准确率”。独立记忆评测应使用人工标注的多轮固定用例，比较压缩、重置和 Checkpoint 恢复前后的关键信息、来源、成员和允许写入项，再计算保留率、清理率、未确认写入率、跨成员泄漏率和恢复成功率。在正式报告生成前，相关百分比只能作为验收目标。

当前 ContextManager 已实现角色裁剪、compaction 和 reset；任务五已实现最终编排契约的成员/任务身份边界和 deterministic 路由输入；任务六的 `DomainAgentInput` 继续只传任务摘要、角色 allowlist 和同成员结构化前序结果。4D-B4 的正式 `/api/business-tasks` 链路由 `SupervisorBusinessWorkflow` 创建本次 run 的运行时领域 Agent，Agent 仍只接收最小视图，并通过 Tool Registry 获取同成员事实；旧 `/api/agent-runs` 则保留为前端兼容链，不能把它当成新业务 Supervisor 链。任务八已由 `TaskCheckpointService` 将最小 `confirmation_state`、draft scope、版本、RunSummary、冻结产物和来源指针写入 PostgreSQL 权威 checkpoint，并由 `TaskCheckpointCache` 提供带作用域/版本校验的 Redis TTL 加速。Redis miss、过期或不可用时回源 PostgreSQL；continuation 不恢复 raw conversation、scratchpad 或未确认推断。偏好写入由 `ConfirmedPreferenceService` 绑定同 task 的已执行确认、成员、source version 和显式人工确认。

任务九后，ContextEnvelope 只能接收成功 Provider 响应产生的 SourceRef。失败 attempt、error category 和 fallback reason 属于审计摘要，不是医疗事实；它们可以进入 RunSummary/Trace，但不能进入 memory refs。Provider source 的 `member_id` 必须与当前 ContextEnvelope 一致。
## 缓存残留与审计投影

Redis checkpoint key 同时包含 user/member/task/thread/version，读取后还要用 Pydantic payload 再校验五个维度。即使错误数据被写入正确 key，只要 payload 的成员或其他作用域不一致，就按 cache miss 处理并回源 PostgreSQL；缓存内容永远不能覆盖权威任务状态。

Observation 不属于 working context，也不进入长期 memory。它是 run 结束后的最小审计投影，只保存标识、状态、时延、来源和计数。Reset 仍删除 raw conversation、scratchpad、候选推断和完整 Tool/Provider payload；续跑根据 RunSummary、确认状态和 source pointer 建立新 working state。

## 评测上下文公平性

`FairnessConfig` 固定三种编排策略的 context token limit 和输出上限；fixture 只保存单条任务输入、成员作用域、结构化工具参数、来源 ID 和预期治理字段，不保存完整聊天或 scratchpad。A/B/C 不能通过扩大上下文、跨成员读取或追加隐藏来源提高指标。

这是 32 条 v1 编排消融的历史规则。4D-B v2 在同一 WorldState 上增加 A/B/C/D 四种模式，其中 A/B/C 使用测试专用 `all_history`，D 使用生产默认 `dependency_only`；两种模式都受成员隔离和敏感字段过滤约束。

## 运行时回源验证

本机 Docker 验收确认 Redis 只保存带 TTL 的短期 Checkpoint 投影；Redis 停止后，任务续跑从 PostgreSQL 权威 Checkpoint 恢复，且不会恢复原始对话、scratchpad 或未确认推断。历史结果见 [项目执行历史](EXECUTION_HISTORY.md)。

# Agent 架构设计

## 1. 文档定位

本文描述最终目标架构及当前实现边界。代码已经具备固定领域 LangGraph、ContextManager、Tool Registry、SafetyAgent、Model Gateway、RunTrace、Evaluator，以及 deterministic Complexity Router、三个运行时领域 Agent、一次性 Planner、bounded DAG Supervisor、三层安全确认状态机和 PostgreSQL 权威 checkpoint/Redis 回源。4D-B2.1 已新增 UnifiedHealthGraph 并接入患者端业务入口；当前默认 `SupervisorBusinessWorkflow` 由 Supervisor 实际创建并调用 Tool-backed Triage/Medication/Report Agent，结果回到同一业务 state 和 Trace；4D-B2.2 的只读 DAG 并行与评测 `all_history` 仍保留在独立内核，正式业务路径强制串行；4D-B2.5 已新增隔离内存 Materializer、九类 deterministic grader 和 pending-review preview Runner；4D-B3 的真实模型审核队列保存脱敏的本地草稿快照，但不改变业务状态。后续状态只按 [总路线图](DEVELOPMENT_ROADMAP.md) 推进。

## 2. 为什么采用有界多 Agent

项目不是因为“Agent 越多越高级”而拆角色。三条业务线的数据、工具、完成条件和风险边界不同：

- 预问诊需要槽位补充、红旗症状和导诊规则。
- 慢病履约需要处方、药箱、药店和草稿状态。
- 报告解读需要文档解析、指标历史和知识来源。

只有真正拥有独立状态、工具权限、有限决策和终止条件的领域角色才称为 Agent。数据库查询是 Tool，RAG 是 Retriever，规则检查是 Guard，幂等是数据库状态机。

## 3. 总体状态图

```text
API / AgentRuntimeService
  -> trusted user/member/resource scope
  -> Request Safety Guard
  -> Complexity / Intent Router
       -> simple_single_domain
            -> TriageAgent | MedicationAgent | ReportAgent
       -> complex_cross_domain
            -> TaskPlanner (one shot, bounded DAG)
            -> bounded Supervisor
                 -> ready read-only steps [bounded parallel]
                 -> deterministic reducer
                 -> AgentTaskResult
                 -> Supervisor review [bounded]
  -> Action Policy Guard
  -> local DRAFT / read-only result
  -> Model Gateway candidate
  -> Final Output SafetyAgent
  -> freeze FinalAnswer / evidence / RunTrace
  -> RunSummary / Context Reset
  -> Deterministic Evaluator [read only]
  -> END
```

待确认任务不暂停进程内 graph。首次 run 结束后，用户确认会在同一 `task_id` 下创建新的 continuation run，从 PostgreSQL Task Checkpoint 恢复结构化进度并重新读取业务事实。

## 4. 路由策略

### 4.1 简单请求

单一业务领域、无需跨角色依赖的请求直接进入对应领域 Agent：

- “整理爸爸的降压药续方材料” -> `MedicationAgent`
- “这份报告里的甘油三酯是什么意思” -> `ReportAgent`
- “帮我整理一下胸闷多久了” -> `TriageAgent`

简单请求不调用 TaskPlanner，不进入 Supervisor 循环。这样减少延迟、token 和无意义 handoff。

### 4.2 复杂请求

需要两个以上领域结果或存在明确依赖时，TaskPlanner 一次性生成有最大步骤数和最大并行数的 DAG。例如：

```json
{
  "steps": [
    {
      "step_id": "step_1",
      "role": "ReportAgent",
      "objective": "提取并解释报告异常指标",
      "dependencies": []
    },
    {
      "step_id": "step_2",
      "role": "MedicationAgent",
      "objective": "读取处方和药箱状态",
      "dependencies": []
    }
  ]
}
```

Supervisor 选择依赖已满足的 ready set；只有相互独立、只读且无副作用的步骤可以进入同一并行批次：

```json
{
  "next_action": "dispatch_ready_steps",
  "step_ids": ["step_1", "step_2"],
  "reason_code": "dependency_satisfied"
}
```

## 5. Planner 与 Supervisor 边界

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| Complexity Router | 判断简单/复杂和目标领域 | 拆解复杂步骤、调用工具 |
| TaskPlanner | 一次性拆解复杂任务、定义依赖 | 每轮改计划、执行工具、处理 provider 错误、生成医疗回答 |
| bounded Supervisor | 按冻结 DAG 调度、检查依赖、受控并行只读步骤、有限重试/降级/终止 | 重写目标、修改成员、产生计划外步骤、并发写操作、跳过治理节点 |
| Domain Agent | 完成一个领域子任务并返回结构化结果 | 调用其他 Agent、修改计划、直接执行外部动作 |

Supervisor 是业务执行层的协调器。SafetyAgent 和 EvaluatorAgent 是治理层节点，不属于 Supervisor 的候选角色。

### 5.1 4D-B5 决策门：业务 DAG 与固定治理边分开

代码审查确认了一个需要先冻结的契约边界：当前 `TaskPlan` 里的领域步骤可以携带依赖，但 `SafetyAgent`、Confirmation、FinalAnswer 和 `EvaluatorAgent` 是 `UnifiedHealthGraph` 的固定治理边；如果把两类边混在同一个 `dependency_edges` 集合中，评测会把治理调用误认为 Supervisor 调度的业务步骤，面试中的“谁真正决定下一步”也会变得含糊。

路线图 4D-B5.1 已冻结为方案 A：

| 方案 | 业务计划 | 治理调用 | 当前状态 |
| --- | --- | --- | --- |
| **A：分开建模（已采用）** | `TaskPlan` 只保存 `TriageAgent`、`MedicationAgent`、`ReportAgent` 及其业务依赖 | `UnifiedHealthGraph` 固定调用 Safety/Confirmation/FinalAnswer/Evaluator，并单独记录 `governance_edges` | B5.1 DONE |
| B：统一类型图 | `WorkflowPlan` 同时保存 domain/governance 节点，通过 `node_kind` 区分 | Supervisor 不能选择治理节点，治理边仍是代码固定边 | 不采用 |

采用 A 的原因是它保留了当前多 Agent 的真实边界：Planner 只规划业务工作，Supervisor 只调度业务 Agent，治理节点不能被计划覆盖。B 不采用，因为它会新增节点类型、治理不可选校验和两套 grader，并增加把 `SafetyAgent` 误解为业务候选角色的风险。

Planner 依赖也已采用确定性业务规则：根据结构化 `intent`、`action_type` 和所需能力生成边，再进行角色白名单、成员作用域、环检测、最大步骤和上游失败校验；模型不能直接提交依赖图。这样“报告解析 -> 续方材料整理”可以作为可解释的业务边，而“安全检查 -> 最终输出”仍属于固定治理边，不进入 Supervisor 的业务 DAG。

当前实现已完成 B5.2：Planner 只在用户表达明确业务顺序时生成 `DependencyHint`，再由拓扑排序写入 `PlanStep.dependencies`；没有明确顺序的并列只读任务仍保持无依赖。`TaskPlan` 会继续校验边集合、环和上游失败传播。

## 6. 三个领域 Agent

### 6.1 TriageAgent

允许决策：

- 哪些必要槽位缺失。
- 继续澄清、调用成员档案、检索导诊规则或完成当前子任务。
- 结构化状态为 `completed / needs_clarification / blocked / failed`。

禁止诊断疾病、修改红旗症状硬规则或绕过急诊提示。

### 6.2 MedicationAgent

允许决策：

- 查询处方、药箱、购药记录、药店候选或续方知识中的哪些组合。
- 生成续方、复诊、购药候选或提醒 `DRAFT`。
- 在事实缺失时选择澄清、降级或转人工。

现有 Profile、Refill、Pharmacy、Reminder 能力在本领域内作为步骤或 Tool 使用，不再作为独立 Agent。MedicationAgent 不能修改处方、改变剂量或凭模型生成库存。

### 6.3 ReportAgent

允许决策：

- 是否调用文档解析、读取历史指标和检索指标知识。
- 哪些解析字段需要人工核对。
- 完成、澄清、转人工或失败。

禁止修改报告原文、把模型解释写成报告事实或在无来源时补医学结论。

### 6.4 统一交接契约

三个 Agent 返回统一 `AgentTaskResult`：

```json
{
  "status": "completed",
  "facts": [],
  "source_refs": [],
  "tool_calls": [],
  "missing_information": [],
  "requested_confirmation": null,
  "failure_reason": null
}
```

事实只能来自 Tool/Provider/RAG 或用户明确陈述。Agent 的候选推断不能进入 `facts`。

任务六保留的 deterministic domain agents 仍只用于离线编排契约和消融；4D-B4 新增的 `runtime_domain_agents.py` 提供真实运行时 `RuntimeTriageAgent`、`RuntimeMedicationAgent` 和 `RuntimeReportAgent`。它们同样不接收数据库 Session，而是通过 `SupervisorAgentRuntime` 进入 Tool Registry 读取处方、药箱、报告和 RAG 事实。`DomainAgentInput` 只携带任务摘要、冻结路由、当前步骤、角色工具 allowlist 和同成员的前序结构化结果；Tool Registry 再执行成员权限和 schema 校验。

## 7. 模型决策模式

每个决策点同时支持：

- `deterministic`：CI、无 Key 和固定回放使用规则策略。
- `model-assisted`：真实模型只从固定枚举中选择，并输出目标 Pydantic schema。

模型候选决策依次经过：JSON 解析、schema、角色白名单、允许工具、步骤依赖、成员作用域、最大步数和 Safety/Policy 校验。失败时结构化降级或使用 deterministic fallback，不把原始文本放进 Agent state。

模型不能提供 `user_id`、`member_id`、权限、provider mode、确认状态或任意工具名。这些由服务端可信上下文注入。

## 8. 安全治理节点

### 8.1 Request Safety Guard

位于 Router 之前，处理严重症状、停换药/改剂量、越权和规则绕过。阻断后可以直接形成安全答案，不执行普通业务工具。

### 8.2 Action Policy Guard

位于受保护 Tool 和状态迁移之前，验证角色权限、成员、资源、动作类型、版本、幂等键和确认状态。它是确定性 Policy，不包装为业务 Agent。

### 8.3 Final Output SafetyAgent

在 Model Gateway 生成候选答案后、冻结前运行，检查诊断/处方/剂量越界、无来源结论、危险表达和必要就医提示。

### 8.4 EvaluatorAgent

答案、证据和 RunTrace 冻结且 working context reset 后运行，只读产生 EvaluationResult。它不能修改答案、调用业务工具、更新 task 或写 memory。

## 9. 确认和 continuation run

首次 run 可以自动写入本地 `DRAFT`，但不产生外部业务副作用。用户确认时：

1. 创建同 task 的 continuation run。
2. 从 PostgreSQL 恢复 RunSummary、步骤、draft 和 source pointers。
3. 重新校验 user/member/draft/version、安全与幂等键。
4. 重新读取可能变化的处方、库存或报告事实。
5. 执行 `DRAFT -> CONFIRMED -> EXECUTED` 本地迁移。
6. 冻结新的答案、Trace 和 EvaluationResult。

Redis 只缓存短期 checkpoint，缓存丢失不影响从 PostgreSQL 恢复。

UX-04 的前端确认只投影为用户可理解的“请确认是否继续”和历史咨询摘要；`DRAFT`、continuation run、成员/版本校验等内部状态仍由代码、接口和治理节点执行，页面不承担路由或安全判断。

任务八的实现由 `TaskCheckpointService`、`TaskCheckpointCache` 和 `ConfirmedPreferenceService` 分层负责：前者写入不可变 PostgreSQL checkpoint，后者只保存带 TTL 的作用域/版本投影，偏好服务只在同 task 的 `EXECUTED` 人工确认和来源版本校验通过后写入可撤销偏好。Redis miss、过期、作用域/版本不匹配或连接异常统一视为 cache miss。

## 10. 并发边界

最终 Supervisor 支持有界 fan-out/fan-in。进入并行批次的步骤必须依赖已满足、`read_only=true`、属于同一 member scope，并且不共享可变业务状态。结果按 `step_id` 使用确定性 reducer 合并，不能依赖完成先后顺序覆盖状态。

领域 Agent 内部也可以并发执行相互独立、无副作用的只读查询，例如同时读取处方和药箱，或同时执行文档解析和知识检索。

以下操作必须串行并受事务保护：Agent 安全、确认、状态迁移、草稿/偏好写入、幂等判断、Checkpoint、FinalAnswer 冻结、Evaluator 和任何未来外部动作。并发只优化等待时间，不能改变业务顺序或权限边界。

## 11. 终止条件

- 当前 Planner 最多 3 步；UnifiedHealthGraph 通过服务端配置限制 `max_steps` 和 `max_parallelism`。
- Supervisor 有最大步骤数、最大并行数和每角色最大调用次数。
- 工具重试由 Tool Registry 策略控制，不由 Supervisor 无限重试。
- 缺失信息返回 `needs_clarification` 并结束当前 run。
- 阻断风险返回 `blocked`。
- 无来源或 provider 不可用时返回结构化 `degraded/failed`，不能生成确定性医疗事实。

## 12. 多 Agent 消融评测

任务十一公平比较：

1. Single-Agent baseline。
2. Router + 固定领域子图。
3. 按需 Planner + bounded Supervisor。

三组共享模型、工具、RAG、Safety、确认状态机、数据、上下文限制和 token 上限。简单与复杂任务分开统计。Supervisor 的价值只通过路由顺序、工具选择、不必要 handoff、重复调用、任务成功和成本证明；Safety 与成员隔离收益不能归因给 Supervisor。

任务十一已将这一设计实现为 `AblationHarnessRunner`。32 条固定业务 case 按八类覆盖，分别生成 Single-Agent、固定单域路由和当前 `DeterministicBoundedSupervisor` 的冻结 `RunTrace`，三组共 96 份结果。`FairnessConfig` 固定 deterministic model identity、工具目录版本、RAG 索引、安全/确认策略和 4096 token 上限；共享治理节点与来源排序不随策略变化。

本地报告的正确解读是：固定路由在简单任务上足够且 fixture latency 更低；复杂跨域任务需要 bounded Supervisor 才能覆盖完整角色和工具；Single-Agent 在固定集上可以完成任务，但会产生额外/重复工具调用。报告不证明临床效果，也不证明真实 LLM 的 token、成本或线上时延优势。

4D-B 在 UnifiedHealthGraph 内增加四种受控模式：

1. forced Supervisor + serial + all_history。
2. auto route + serial + all_history。
3. auto route + parallel + all_history。
4. auto route + parallel + dependency_only。

`all_history` 只在测试环境和合成数据中启用，并始终保持 user/member 隔离。A 到 B 测 Router，B 到 C 测 DAG 并行，C 到 D 测角色最小上下文。完整数据和指标见 [Agent 统一架构、评测数据与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。

## 13. 任务七实现边界

任务七使用 `backend/app/agent/safety_confirmation.py` 把三个治理节点和状态迁移固定下来：

```text
request: evaluate_safety(user_input)
  -> business execution
  -> action: scope + medical policy + confirmation state
  -> local DRAFT
  -> Model Gateway candidate
  -> final_output: output schema + unsafe expression check
  -> freeze artifacts / evaluation
```

`ConfirmationStateMachine` 支持 `NONE -> DRAFT -> CONFIRMED -> EXECUTED`，并把 `BLOCKED`、`REJECTED`、`EXPIRED` 和 `FAILED` 作为终止状态。创建 DRAFT 不需要用户确认；`confirm` 和 `execute` 都需要显式确认，且重复相同 scope 会返回 replay，成员、用户、任务、版本、指纹或幂等键不一致会阻断。`EXECUTED` 只表示当前本地状态迁移成功，外部动作仍为 `not_submitted`。

`SafetyAgent` 仍然是运行时治理角色；`ThreeLayerSafetyGuard` 是它在请求、动作和最终答案边界上的确定性门禁实现。`EvaluatorAgent` 仍位于所有冻结产物之后，只读评估，不参与状态迁移。

## 14. 任务八实现边界

任务八完成了状态存储和续跑边界，但没有提前实现任务九的 Provider 可靠性或任务十一的 Harness。续跑只恢复 `RunSummary`、步骤进度、确认 draft/version 和来源指针；旧 run 的 raw conversation、scratchpad、候选推断、provider 原始响应和完整临时 role view 不进入新 working state。新 run 通过 `parent_run_id` 关联上一 run，并重新读取可能变化的处方、库存或报告事实。

## 15. 任务九 Tool/Provider 边界

领域 Agent 仍只能通过 Tool Registry 请求能力。任务九在 Registry 后增加三类重点 Provider 的强契约与有限重试：Tool 层负责角色、allowed tools、成员作用域和写操作禁重试；Provider 层负责外部 identity/mode/operation、transport timeout、attempt 和输出 schema。Supervisor 只能读取结构化失败摘要，不能修改 retry policy，也不能把降级响应升级为事实。

失败 Provider 不产生 SourceRef；mock 来源带 `simulation=true`。因此 Agent 的 groundedness 不能把“调用过 Provider”误判成“取得了业务证据”。

## 16. 当前实现边界

| 当前已实现 | 尚未完成 |
| --- | --- |
| 患者端 HTTP 已通过 UnifiedHealthGraph 接入；默认 `SupervisorBusinessWorkflow` 由 Supervisor 实际调用三个运行时领域 Agent 和 Tool Registry；bounded Supervisor 仍保留只读 DAG fan-out/fan-in；4D-B2.3 已完成 FinalClaim、AnswerEnvelope、Trace v2 和 Claim 一致性校验；4D-B2.4 已生成 v2 数据；B2.5 已完成内存 projection、九层 grader 和 preview runner；B2.6 已接入 PostgreSQL shadow transaction、Provider sandbox、case-scoped RAG 和真实 UnifiedHealthGraph 单样例执行 | 300 WorldState/1200 Query 的全量正式报告、人工审核冻结和真实 A/B/C/D 消融仍待完成 |
| 新业务链路已接入三层治理、自动 DRAFT、确认状态机、版本化 checkpoint 和三类重点 Provider 可靠性 | 真实外部 Provider 联调仍未实现 |
| PostgreSQL 冻结产物、continuation、Redis TTL 回源、确认后偏好、Tool/Provider attempts、RRF、白名单 Observation、Trace v2 Claim 产物，以及 B2.6 的 Docker 19/19 回归和真实单样例物化 | 300 WorldState/1200 Query 的全量正式评测报告和最终 A/B/C/D 归因仍未冻结 |
| Model Gateway 已支持 deterministic/真实模型双模式和结构化 FinalAnswer | 已生成 8 条 development 固定样本的人工复核、token、成本和本机延迟报告；validation/holdout 与全量稳定性仍未完成 |

## 4B 任务十：Observation 在架构中的位置

Observation 不是新 Agent，也不进入 Supervisor 决策。业务图执行结束后，artifact projector 从已冻结 state 投影 `request -> node -> tool/provider/source/model -> final` 事件，再随 `RunTrace` 交给只读 Evaluator。事件契约没有任意 metadata，不能携带 raw conversation、scratchpad、业务 payload 或模型原文。

RAG 与成员隔离也不依赖模型自觉：RRF 在 Retriever 内确定性计算；过期版本在 source hydration 边界拒绝；成员资源在 Repository SQL 和 Tool execution context 两层校验；Redis 污染或过期只会触发 PostgreSQL 回源。SafetyAgent 仍负责运行时风险，Observation 只负责记录发生了什么。

4D-B 的评测数据、FinalClaim、grader、Docker runner 和简历指标规则见 [Agent 评测与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。状态和实施顺序只以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为准。

## 用户端 UX-06 与 Agent 边界

UX-06 的报告列表和详情是只读业务数据投影，不新增 Agent 节点、Supervisor 路由或工具调用。`ReportReadService` 只把 `medical_documents` 中已经保存的报告事实映射为 `report-detail.v1`；页面展示来源和安全提示，但不把模型解释升级为诊断或治疗结论。后续若接入解析或知识检索，仍需沿现有 Agent、RAG 和 Safety 治理边界扩展，不能由前端自行推断。

## 用户端 UX-08 与 Agent 入口边界

UX-08 不改变 Router、Planner、Supervisor、业务 Agent、SafetyAgent 或 EvaluatorAgent。前端只把自然语言咨询、历史结果、家庭记录和报告读取作为用户入口；知识检索、库存、续方、提醒和 Trace 属于内部执行/治理能力。兼容跳转不能绕过 Agent 的成员作用域、工具权限、Safety 检查或人工确认。
## 4D-B5.5 最终契约：业务 DAG 与固定治理边分离

4D-B5.1 采用方案 A 后，`TaskPlan` 的边界固定如下：

- `domain_steps` 只允许三个 canonical domain Agent：`TriageAgent`、`MedicationAgent`、`ReportAgent`。
- `domain_dependency_edges` 只表示业务步骤之间的依赖，例如 `ReportAgent -> MedicationAgent`。这些边由确定性 Planner 根据业务规则生成，不能由模型自由提交。
- `governance_steps` 记录固定治理节点：`SafetyAgent`、Confirmation、FinalAnswer 和 `EvaluatorAgent`。
- `governance_edges` 记录状态图强制执行的治理顺序。治理边不属于 Supervisor 的业务 DAG，也不参与 Supervisor 的候选步骤选择。
- `safety-review` 是治理节点或治理边的标识，不是 Supervisor 可以调度的业务步骤，也不是三个 canonical domain Agent 之一。

最终执行关系是：

```text
Router
  -> Planner
  -> Supervisor(domain_steps + domain_dependency_edges)
  -> fixed Safety / Confirmation / FinalAnswer / Evaluator governance edges
```

Supervisor 只能在冻结的 `domain_steps` 中选择依赖已满足的业务步骤；它不能新增治理步骤、移除治理边、把 `safety-review` 当作业务 Agent 调度，也不能绕过固定治理节点。

### B5.5 当前状态

该分层已经落地到契约、生成器、grader 和 preview runner；仍有人工审核与真实 PostgreSQL integration 的独立验收门槛：

- 现有代码已经具备 canonical domain Agent、bounded Supervisor 和固定治理调用的基础。
- v2 gold/grader 已完成 domain/governance 两类步骤与边的字段映射、分别校验及报告展示，数据版本为 `4d-b5.5`。
- 300 个 WorldState / 1200 条 Query 的人工审核、冻结 manifest 和全量 PostgreSQL integration 尚未宣称完成。
- 因此当前文档仍不把 v2 全量人工审核或生产级数据库验收写成已完成结果；这不影响 B5.2-B5.6 的代码回归已通过。

详细的分层评测规则以 [Agent 评测执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md) 为准。

## 用户端 UX-09 联调边界

UX-09 没有新增 Agent 角色、路由、Supervisor 步骤或治理边。前端只消费既有运行冻结产物和 DTO；成员、来源、安全、确认、RunSummary、Context Reset 与 Evaluator 的服务端边界保持不变。`WorkflowToolInputBuilder` 的药品名补齐属于既有 Tool 输入构建契约，不是运行时自由重规划，也不改变 Agent 的职责边界。

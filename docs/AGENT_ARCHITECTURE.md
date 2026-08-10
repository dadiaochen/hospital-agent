# Agent 架构设计

## 1. 为什么采用有界多 Agent

项目处理预问诊信息整理、慢病用药和报告解读。三类任务依赖的数据、工具权限、输出结构和安全边界不同，因此拆成三个领域 Agent；简单请求不强制进入多 Agent，只有跨领域且存在依赖的任务才使用 Planner 与 Supervisor。

项目不采用无限 ReAct 或自由 handoff。模型负责理解和结构化决策，权限、最大步骤、确认、安全、Checkpoint 和终止条件由程序控制。

## 2. 角色与职责

| 角色 | 职责 | 禁止事项 |
| --- | --- | --- |
| Router | 判断单领域直达或复杂跨领域 | 为展示架构而强制走 Supervisor |
| Planner | 对复杂任务生成一次冻结 DAG | 逐步调度、调用工具或运行时改目标 |
| Supervisor | 调度依赖已满足的领域步骤，有限重试和终止 | 直接调用工具、扩展计划、跳过治理节点 |
| 分诊 Agent | 症状结构化、红旗信号和就医候选 | 诊断 |
| 用药 Agent | 处方、药箱、库存、续方材料和提醒草稿 | 开方、改剂量、替用户下单 |
| 报告 Agent | 报告解析、指标结构化和有来源解释 | 给出诊断或治疗方案 |
| Agent 安全 | 在入口、动作前和最终输出前拦截风险 | 代替业务 Agent |
| Agent 评测 | 回答冻结后只读检查质量 | 修改答案、调用工具或写业务状态 |

## 3. 运行 Pipeline

```text
User Request
  -> Trusted user/member scope
  -> Request Safety
  -> Router
       -> simple -> one Domain Agent
       -> complex -> Planner -> frozen DAG -> Supervisor
  -> Context Manager
  -> Domain Agent
  -> Tool Registry -> DB / Provider / RAG
  -> structured AgentTaskResult
  -> Supervisor reducer
  -> Action Safety
  -> local Draft / Human Confirmation
  -> Model Gateway
  -> Final Output Safety
  -> FinalAnswer + FinalClaim + RunTrace
  -> RunSummary + Context Reset
  -> Deterministic Evaluator
```

## 4. 简单与复杂任务

简单任务只有一个业务目标、一个成员和一个领域，例如解释一项报告指标或整理一份续方材料。Router 直接进入对应领域 Agent，不调用 Planner。

复杂任务需要两个以上领域结果或存在明确依赖。Planner 只执行一次，输出步骤、角色、目标、依赖、允许工具和最大并行数。Supervisor 只能从依赖已满足的 ready set 中选择步骤。

独立、只读且无副作用的步骤可以有界并行；写操作、确认、Checkpoint 和治理节点保持串行。并行结果按 step_id 确定性合并，并保留成员、来源和 attempt。

## 5. Agent 间通信

Agent 之间不直接聊天或互调，只交换结构化 `AgentTaskResult`：

- 当前 step 与角色；
- 已确认事实和缺失信息；
- 实际工具调用；
- `SourceRef`；
- 安全标记和确认要求；
- 成功、失败、重试与降级原因。

每个 Agent 从 `ContextEnvelope` 投影出最小角色视图，只看到当前成员、当前步骤、所需来源和允许工具。完整聊天、其他成员数据和其他角色 scratchpad 不会广播。

## 6. 工具调用

领域 Agent 不持有数据库 Session 或 Provider Client。所有调用进入统一工具调用层，依次检查：

1. 工具是否注册；
2. 当前角色和计划步骤是否允许；
3. user/member/resource 作用域是否一致；
4. input/output schema 是否有效；
5. 是否需要人工确认；
6. timeout、有限重试和降级是否符合策略；
7. attempt trace 是否完整。

Supervisor 只调度 Agent，不越级调用工具。没有工具或 RAG 证据时，Agent 不能补写医疗事实。

## 7. 固定治理边

业务 DAG 只描述 Router、Planner、Supervisor 和领域 Agent 之间的业务依赖。Agent 安全、人工确认、Checkpoint、最终回答和 Agent 评测属于固定治理边，不进入 Supervisor 的可选计划。

5A 在可信身份与成员作用域之后、医疗安全之前增加 `RequestScopeGuard`。它只判断请求是否属于家庭健康产品：高置信度天气、编程、金融、旅游等业务外请求直接使用固定回复结束；“帮我看看”等无明确健康对象的输入返回澄清；含健康信号的混合意图保守放行。它不调用模型，不替代医疗安全，不进入 Supervisor，也不创建第二套状态服务。

阻断型安全标记出现后，不能创建草稿或执行动作。购药、复诊和提醒首次只生成本地草稿；确认通过同一 task 下的新 run 续跑，并重新读取可变事实。

## 8. 状态恢复

单次 run 的 Working State 在结束后清理。可续跑信息以 RunSummary、确认状态和冻结产物引用写入 PostgreSQL Task Checkpoint；Redis 只缓存带 TTL 的投影。

续跑时先读 Redis，miss、过期、版本不匹配或故障时回源 PostgreSQL；恢复后重新校验 user、member、task、draft fingerprint、Checkpoint version 和 confirmation version。旧 scratchpad、原始聊天和未确认推断不恢复。

## 9. 模型边界

Router、Planner、领域 Agent 和 Supervisor 可以使用 Model Gateway 产生固定 Pydantic schema 的候选决策，但模型输出之后仍要经过角色白名单、工具权限、依赖、最大步骤、成员和安全校验。

自动测试默认使用 deterministic provider。真实 Provider 超时、HTTP、schema 或安全失败必须记录 attempt，并按同一输出契约有限降级；原始失败文本不能进入用户答案。

## 10. 评测

冻结产物至少包含路由、计划、步骤结果、工具调用、来源、Agent 安全、确认、FinalAnswer、FinalClaim 和延迟。只读评测器分别检查任务完成、工具正确性、来源覆盖、幻觉、安全、成员隔离和状态恢复。

当前架构、数据和指标见 [技术设计](TECH_DESIGN.md)、[Agent 评测](EVALUATOR_AGENT.md) 与 [简历和面试口径](RESUME_NOTES.md)；历史阶段见 [项目执行历史](EXECUTION_HISTORY.md)。

5A-2 已将 synthetic RAG 评测明确分为检索层和生成层。检索层以冻结 chunk ID Gold 计算 Recall@3/5/10、MRR@10、二值 nDCG@10、无答案准确率、过期版本过滤和 P50/P95/P99；生成层继续保留来源绑定、Claim、Citation 和安全的确定性评分。RAGAS 只允许作为离线语义交叉验证，失败不得影响业务链路或冻结答案。

5A-4 为 Triage 增加最小多轮槽位状态机：首个必填槽位为 `symptoms`，缺失时只返回稳定槽位名与 `needs_clarification`。续跑由服务层校验 `user_id`、`member_id`、任务范围与 Checkpoint 版本，并创建带 `parent_run_id` 的新 run；Triage 不保留完整原始对话、不诊断疾病，也不在信息不完整时创建复诊草稿。

最终回答在既有 Final Output Safety 后经过 `FinalAnswerQualityGate`。该门只检查展示完整性、确认提示和事实来源契约，不能调用工具或重规划；格式缺陷至多进行一次同 schema 的无 Tool 修复，安全失败和无来源事实直接 fail-closed。审计随 Run/Checkpoint 冻结，`EvaluatorAgent` 仍只读且发生在答案冻结之后。

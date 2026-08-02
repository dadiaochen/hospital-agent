# 家庭健康服务业务工作流

## 1. 文档定位

本文描述三条目标业务线及其与当前实现的映射。当前仓库已实现慢病续方、复诊材料、用药提醒、购药候选和高风险拦截基础；4B 完成后端 Agent 能力闭环，4C 完成三条业务线的成熟前后端产品交付。

## 2. 共用处理链路

所有业务请求先经过相同治理入口，再按复杂度分流：

```text
用户请求 -> 可信成员/资源校验 -> Request Safety Guard -> Complexity Router
  -> 简单：对应 Domain Agent
  -> 复杂：一次性 TaskPlanner -> bounded Supervisor -> Domain Agents
-> Action Policy Guard -> 可选本地 DRAFT
-> Model Gateway 候选答案 -> Final Output SafetyAgent
-> 冻结产物 -> Context Reset -> Deterministic Evaluator
```

4D-B2.1 已将患者端入口接入 `UnifiedHealthGraph`：统一图先执行 Router、一次性 Planner/Supervisor 和领域结果投影，再进入现有 ProductWorkflow 适配器完成业务 Tool、草稿、确认和冻结。4D-B2.2 已把复杂计划表示成有界 DAG：只有依赖已满足、只读且无写工具的领域步骤可以 fan-out 并行，结果按 `step_id` 确定性合并；任何确认、写操作、Checkpoint、安全检查和评测节点仍按固定边串行执行。4D-B2.3 已在同一次最终答案产物中保存 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`，4D-B2.4 已生成待审核的 300/1200 v2 数据；B2.5 已完成内存 projection、九类 grader 和 preview Runner；B2.6 已接入 PostgreSQL shadow transaction、case-scoped RAG、Provider sandbox、真实图执行和 Docker 19/19 回归，但全量正式消融报告仍未冻结。

任务七把“可选本地 DRAFT”固定为受保护动作的状态机入口：新业务任务首轮在作用域、动作和来源检查通过后自动产生本地 `DRAFT`；用户确认的是后续本地执行，不是是否允许生成草稿。确认 continuation 必须在同一 `task_id` 下重新校验 `user_id`、`member_id`、draft version、request fingerprint、idempotency key 和 Safety decision，再串行推进 `DRAFT -> CONFIRMED -> EXECUTED`。任何外部医院、药店、支付或通知状态都保持 `not_submitted`。

共用约束：

- 处方、库存、病史和报告数据必须来自数据库或 Provider。
- 医疗流程、风险规则和指标解释优先来自带版本的 RAG 文档。
- 每条关键解释保留 `SourceRef`，至少包含文档版本和检索方式。
- Agent 只生成信息整理、导诊建议、解释或待确认草稿。
- 本地 DRAFT 可以自动生成；复诊、购药、提醒、健康档案写入等执行动作必须经过用户确认。
- 用户确认通过同一 task 下新的 continuation run 处理，不恢复旧 scratchpad，并重新读取可变业务事实。
- PostgreSQL 保存权威 checkpoint；Redis 只做 TTL 缓存，故障时回源 PostgreSQL。

评测边界：4D-B3 的 shadow run 会生成本地 `DRAFT`，并在冻结审核产物中保留 `ConfirmationDraftSnapshot`，用于核对草稿编号、摘要、关键提醒字段、成员、动作、版本和 `external_action_status=not_submitted`。该快照不是可继续确认的业务记录；正常 `/api/business-tasks` 响应才返回完整 `confirmation_draft` 并由 Task Checkpoint 保存。用户可见回答不能只说“已生成草稿”，还必须提供可审计的草稿编号、关键字段和安全摘要。

任务八把共用续跑契约具体化为：首次 run 写入 `task_checkpoints` 的版本 1，确认 run 在同一 `task_id` 下创建新的 `run_id` 和 `parent_run_id`，并把 checkpoint/confirmation version 推进到新版本。Redis 只缓存带 `user_id/member_id/task_id/thread_id/version` 作用域的投影；缓存 miss、过期、版本错配或不可用时由 PostgreSQL 重建。偏好写入必须通过 `/api/preferences` 的显式确认、同成员 source version 和已执行状态校验。

## 3. 业务线一：智能预问诊与分级导诊

### 输入

- `user_id`、`member_id`
- 主诉、症状、持续时间、严重程度
- 用户主动提供的既往史、过敏史和附件
- 位置、就诊偏好等可选信息

### 处理节点

1. 校验用户与家庭成员关系，建立成员隔离上下文。
2. 将自然语言主诉整理为结构化预问诊信息，缺失关键槽位时向用户追问。
3. 查询健康档案和已确认的过敏、慢病信息。
4. 检索分级导诊规则、红旗症状规则和就医流程知识。
5. Agent 安全检查先判断是否需要立即就医、急诊或人工介入。
6. 对非阻断请求由 TriageAgent 生成科室方向、就诊准备材料和可选服务入口草稿。
7. 本地草稿自动保存；由用户确认是否执行允许的本地后续状态，不提交真实挂号或在线问诊。

### 输出

- 结构化预问诊摘要
- 风险等级和触发依据
- 科室或就医渠道建议，不包含疾病诊断
- 需要补充的材料
- 带来源的解释与待确认后续动作

## 4. 业务线二：家庭医生、慢病与用药履约

### 输入

- `user_id`、`member_id`
- 续方、购药、提醒、复诊材料或用药咨询意图
- 当前药箱、历史处方和用户补充信息

### 处理节点

1. 查询家庭成员档案、历史处方、药箱和购药记录。
2. 计算剩余天数并识别待续方、待购药或待复诊事项。
3. 检索慢病续方流程、药品安全和人工确认规则。
4. 用药冲突类问题只做风险提示和就医建议；不能修改剂量、停药或换药。
5. 查询药店库存、配送或自提候选，必要时查询在线问诊入口。
6. MedicationAgent 生成续方材料、购药候选、用药提醒或随访任务 DRAFT；Profile/Refill/Pharmacy/Reminder 作为内部步骤或 Tool。
7. Action Policy 与最终输出 Safety 通过后展示草稿，等待用户确认执行允许的本地状态迁移。

### 输出

- 续方与复诊材料摘要
- 药箱缺口和购药候选
- 用药提醒或随访任务草稿
- 用药咨询中的风险提示和来源
- 用户确认状态

### 与原四场景的映射

- 父亲降压药慢病续方：保留并纳入慢病履约。
- 母亲中医复诊材料整理：保留并纳入复诊准备。
- 母亲用药提醒创建：保留并纳入家庭任务。
- 高风险用药调整拦截：升级为三条业务线共用的 Agent 安全能力。

## 5. 业务线三：报告解读与长期健康档案

### 输入

- `user_id`、`member_id`
- 检查报告、体检报告、中医诊疗记录或舌诊结果
- 报告类型、时间和来源机构等元数据

### 处理节点

1. 校验成员和文件权限，调用医疗文档解析 Provider。
2. 提取报告标题、检查时间、机构、指标、单位、参考范围和原文位置。
3. 保留原始文档、结构化字段与页码或区域引用。
4. 查询成员历史指标，生成趋势对比所需的结构化事实。
5. 检索指标解释、报告阅读规则和就医提示知识。
6. 生成面向患者的通俗解释，明确区分报告原文、知识解释和模型整理。
7. 对高风险指标、缺失单位、识别不确定或超出知识范围的内容转人工。
8. ReportAgent 先生成健康事件 DRAFT；用户确认后通过 continuation run 重新校验并写入结构化档案。

### 输出

- 报告结构化摘要
- 指标解释与趋势信息
- 每个关键解释对应的 `SourceRef`
- 需要医生进一步判断的问题清单
- 待确认的健康档案写入草稿

## 6. RAG 与检索降级

三条业务线均使用 RAG，但业务事实与知识规则分开处理：

- 业务事实：数据库、医院、药店、在线问诊、报告解析 Provider。
- 知识规则：医疗流程、安全规则、报告指标解释和用户教育材料。

向量检索未命中时，可按配置降级为关键词检索、结构化规则或人工处理。降级过程必须记录，不能在无来源时让模型补齐医疗结论。

## 7. 异常处理

- Provider 超时：返回结构化失败，保留可重试标记。
- 文档解析不确定：展示原文位置并要求人工核对。
- RAG 无命中：不输出确定性医疗结论，转为补充信息或人工处理。
- 成员切换：创建新的任务上下文，禁止复用上一成员事实。
- 高风险请求：在任何草稿或用户可见结论生成前执行 Agent 安全拦截。

## 8. 模型与最终答案

Router、TaskPlanner、三个 Domain Agent 和 Supervisor 在 4B 目标架构中可以使用 Model Gateway 输出固定 schema 的候选决策；无 Key 时使用 deterministic policy。模型不能产生任意角色/工具、覆盖成员或安全策略。业务执行完成后，Gateway 根据压缩任务摘要和 SourceRefs 生成用户可见候选答案，再由 Final Output SafetyAgent 检查后冻结。

当前任务六已经提供不依赖模型、数据库和业务工具的三个 deterministic 领域 Agent、一次性 Planner 和串行 bounded Supervisor；它们只返回结构化工作流结果，不伪造处方、库存或报告事实。Model-assisted 领域决策仍必须等后续接线，并且只能在固定 schema、角色/工具白名单和安全规则内运行。任何 timeout、HTTP、schema 或安全失败都必须记录 attempt，并结构化降级或回退 deterministic。Key、完整 Prompt 和 provider 原文不持久化。

## 9. 任务九 Provider 失败语义

- 报告解析只在强 schema 通过后产生带文档版本、parser version 和原文区间的 SourceRef；解析失败时不生成报告事实。
- 药房查询只返回库存与履约候选，不创建订单；医院/问诊只返回科室、时段或草稿，不挂号、不提交问诊。
- 只读 timeout、rate-limit 和临时不可用按固定上限重试；参数、权限、成员作用域、schema 和业务冲突立即停止。
- 降级结果保留 error category、attempt 和 fallback reason，但 data/source 为空，业务状态进入 failed/degraded 或人工处理。
## 4B 任务十：来源、隔离和排障闭环

三条业务链路读取通用医疗知识时，hybrid RAG 使用 RRF 融合 keyword/vector rank；处方、报告、药箱等个人医疗事实仍来自当前成员的业务数据库或 Provider，不进入个人向量记忆。向量命中的 document/chunk/schema 版本必须与 PostgreSQL 权威记录一致，否则忽略旧命中并记录降级原因。

业务 run 冻结时同步生成白名单 Observation：能看出请求经过哪些节点、调用哪些 Tool/Provider、是否重试或降级、使用哪些 source、哪个模型以及 Provider 是否提供 token usage，但不能从 Observation 还原用户原话、医疗正文、Tool/Provider payload、Prompt 或 FinalAnswer 正文。该 Trace 只用于排障和后续评测，不参与 Supervisor 路由，也不能修改确认状态。

## 4B 任务十一：业务链路消融

32 条 fixture 覆盖正常单域、复杂跨域、缺失信息、高风险、RAG、Provider/Tool 异常、成员攻击和确认/幂等。简单任务固定路由与 bounded Supervisor 都能完成，说明简单任务不应强制进入 Supervisor；6 条复杂任务中固定单域路由缺少第二领域工具，而 bounded Supervisor 完整执行冻结角色顺序。该结果用于验证复杂度分流，不代表真实用户问题分布。

## 4B 任务十二：真实后端链路

任务十二没有改变业务状态机：首次请求仍只生成本地 `DRAFT`，确认续跑才允许本地状态推进。Docker 验收验证了三条业务任务 API、知识搜索和 422 错误映射；4 个并发确认只允许 1 次真实执行，Redis 停止时仍由 PostgreSQL checkpoint 恢复任务。该验收证明实现链路可运行，不代表已经接入真实医院、药店、支付或通知系统。

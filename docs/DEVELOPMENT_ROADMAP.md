# Development Roadmap

## 1. 唯一权威

本文档是项目阶段编号、状态、依赖关系、实施顺序和完成标准的唯一权威来源。

- `README.md` 只展示当前能力和入口，不维护另一套路标。
- 子系统文档只解释本领域设计，不新增阶段编号或改变任务状态。
- 已实现、正在实现和计划能力必须分开表述。
- 同一时间只允许一个 `NEXT`；完成当前任务后才能移动 `NEXT`。
- Git 历史保留已经完成的阶段事实，不为“最终架构看起来整齐”而改写过去。

## 2. 产品定位

项目定位为：

> 面向家庭健康场景的有界多 Agent 系统。简单单领域请求直接进入领域 Agent；复杂跨领域请求由一次性 TaskPlanner 生成有界 DAG，再由 bounded Supervisor 协调三个领域 Agent，对无依赖、只读步骤执行受控并行。系统通过 Tool Registry、RAG 溯源、三层安全治理、人工确认、成员隔离和 Evaluation Harness，形成可追踪、可回放、可测试的业务闭环。

三条业务线：

1. 智能预问诊与分级导诊：整理主诉、识别缺失信息和红旗症状，提供就医路径准备，不诊断疾病。
2. 家庭医生、慢病与用药履约：整理处方、药箱、续方、购药候选和提醒草稿，不开方、不改剂量、不自动下单。
3. 报告解读与长期健康档案：解析报告、解释指标、整理趋势和健康事件草稿，不把模型解释写成诊断事实。

系统不是 AI 医生，不诊断、不自动开方、不修改处方，不建议用户自行加量、减量、停药或换药。当前产品不执行真实医院、药店、支付或通知系统写操作。

## 3. 状态定义

| 状态 | 含义 |
| --- | --- |
| `DONE` | 代码、测试、文档和必要运行验证均已完成 |
| `NEXT` | 当前唯一允许开始的任务 |
| `PLANNED` | 已确定范围，但前置任务尚未完成 |
| `OUT` | 明确不属于当前最终产品范围 |

设计文档完成不等于代码完成；fixture/mock 结果不等于真实模型、生产或临床指标。

## 4. 最终架构决策

### 4.1 路由和编排

- 先通过可信身份、`user_id + member_id + resource_id` 和请求前 Safety Guard。
- Complexity/Intent Router 将请求分为简单单领域与复杂跨领域。
- 简单请求直接进入 `TriageAgent`、`MedicationAgent` 或 `ReportAgent`，不调用 Planner，不进入 Supervisor 循环。
- 复杂请求才调用一次性 `TaskPlanner`，生成有最大步骤数和最大并行数的冻结 DAG；bounded Supervisor 已能对依赖就绪的只读步骤做受控 fan-out/fan-in。
- bounded Supervisor 只执行计划：选择依赖已满足的业务步骤，将相互独立、只读且无副作用的步骤组成受控并行批次，并处理有限重试、降级和终止；不得修改用户目标、成员、治理策略或产生计划外角色。
- 业务 Agent 统一返回 `AgentTaskResult`，不能直接调用其他 Agent。
- 确认、写操作、Checkpoint、Safety 和 Evaluator 节点保持串行；禁止无边界并行、共享可变业务状态和运行时复杂自动重规划。

### 4.2 三个领域 Agent

| Agent | 有限决策 | 禁止能力 |
| --- | --- | --- |
| `TriageAgent` | 选择需要补充的槽位、查询档案/导诊规则、完成/澄清/阻断 | 诊断疾病、修改红旗症状硬规则、绕过急诊提示 |
| `MedicationAgent` | 选择查询处方、药箱、药店或续方规则，决定草稿类型 | 修改处方、改变剂量、凭模型生成库存事实 |
| `ReportAgent` | 选择解析报告、读取历史指标、检索指标知识或转人工 | 篡改报告原文、无来源补医学结论 |

现有 `ProfileAgent`、`RefillAgent`、`PharmacyAgent`、`ReminderAgent` 在最终架构中收敛为 Medication 领域内的步骤、能力或 Tool，不再作为独立 Agent 增加层级。

### 4.3 模型参与边界

- 无 Key、CI 和自动测试使用 deterministic policy/provider。
- 配置真实模型时，Router、TaskPlanner、三个领域 Agent 和 Supervisor 只能在固定候选项内输出结构化决策。
- 模型不能自由生成角色名、工具名、身份字段、状态迁移或医疗动作。
- 所有模型决策必须经过 Pydantic schema、角色/工具白名单、步骤依赖、成员权限、最大步数和安全策略校验。
- Model Gateway 继续负责 provider、timeout、schema、安全检查和 deterministic fallback；未经校验的 provider 原文不得进入状态或用户答案。

### 4.4 三层安全治理

1. **Request Safety Guard**：在普通业务执行前拦截严重症状、改剂量、停换药、越权成员访问和绕过规则请求。
2. **Action Policy Guard**：在草稿写入、确认和任何受保护工具前检查角色权限、成员、动作类型、版本、幂等键和确认状态。
3. **Final Output SafetyAgent**：在用户可见候选答案冻结前检查诊断、处方、剂量、无来源结论和危险表达。

SafetyAgent 属于治理层，不是 Supervisor 的候选业务角色。EvaluatorAgent 在答案和证据冻结后只读评估，也不能被 Supervisor 跳过。

### 4.5 草稿与确认

- Agent 可以自动创建本地、可审计的 `DRAFT`；创建草稿不代表外部业务已执行。
- 用户只确认真正的执行动作，不确认“是否允许生成草稿”。
- 状态机：`DRAFT -> CONFIRMED -> EXECUTED`，旁路终态为 `REJECTED / EXPIRED / FAILED`。
- 当前 `EXECUTED` 只表示契约允许的本地状态迁移，`external_action_status` 保持 `not_submitted`。
- 相同幂等键和相同请求返回首次结果；相同幂等键和不同请求返回冲突。
- 并发确认由 PostgreSQL 行锁或条件更新保证只有一次合法迁移。

待确认任务采用同一 `task_id` 下两次独立 run：首次 run 冻结 `DRAFT`、答案和证据后结束；用户确认时创建 continuation run，从 PostgreSQL Task Checkpoint 恢复进度、重新读取必要事实，再执行允许的本地状态迁移。

### 4.6 最终分层状态架构

| 层 | 作用 | 权威性 |
| --- | --- | --- |
| LangGraph Run Working State | 单次 run 的 ContextEnvelope、调度游标和临时角色结果 | 临时；run 后 reset |
| PostgreSQL Task Checkpoint | RunSummary、步骤进度、确认记录、冻结产物和用户确认偏好 | 权威存储 |
| Redis Short-lived Task Cache | TTL 任务缓存、短期 checkpoint 加速和多实例协调 | 非权威；故障时回源 PostgreSQL |
| PostgreSQL + pgvector Knowledge RAG | 独立、版本化、已审核的医疗知识和 SourceRef | 知识来源，不是个人记忆 |

系统不保存长期完整聊天，不建立个人健康向量记忆。处方、报告原值、过敏史、药箱和库存是业务事实，每次 run 必须从业务数据库或 Provider 重新读取。用户偏好只允许在明确确认、成员绑定、来源和版本齐全时写入 PostgreSQL。

### 4.7 Provider、RAG 和观测范围

- 当前已有七个兼容 mock adapter；最终验收只做深 `MedicalDocumentParserProvider`、`PharmacyProvider`、`HospitalOrConsultationProvider` 三类，其余不扩展为空壳能力。
- RAG 保留 PostgreSQL、pgvector、FastEmbed、Keyword Retriever、RRF、SourceRef、版本校验和关键词降级。
- HNSW 只描述为可扩展索引路径；没有真实基准前，不宣称性能提升。
- 使用现有 RunTrace/结构化 observation 字段记录 request、run、node、tool、latency、error、retry、fallback、source、model 和 token。
- 不实现 MCP Server、OpenTelemetry/Jaeger。LLM Judge 仅可作为离线辅助实验，不进入运行链路，也不是验收硬门槛。

## 5. 已完成阶段账本

| 阶段 | 状态 | 已验证结果 |
| --- | --- | --- |
| 1 | `DONE` | 产品范围、基础页面和项目骨架 |
| 2A / 2A.1 | `DONE` | SQLAlchemy、Alembic、seed、模型测试与 Agent trace 字段 |
| 2A.2 | `DONE` | Context Lifecycle、Reset/Compaction 和 EvaluatorAgent 设计 |
| 2B | `DONE` | Pydantic Agent 契约、16 条 fixture、deterministic evaluator、HarnessRunner、ContextManager |
| 2C–2G | `DONE` | Tool Registry、读取/草稿 API、Hybrid RAG、Model Gateway、LangGraph DAG、Runtime API 和持久化 |
| 3A | `DONE` | Next.js 家庭数据页面 |
| 3B | `DONE` | Agent UI、确认续跑与 Trace/Evaluation 展示 |
| 3C | `DONE` | Runtime E2E Harness 与真实本地冻结 Trace 回放 |
| 3D | `DONE` | Docker Compose MVP、固定演示脚本和脱敏报告 |
| 4A | `DONE` | 产品重基线、SourceRef/Provider Mode、FastEmbed + pgvector 路径和知识版本元数据 |

## 6. 最终阶段

| 阶段 | 状态 | 目标 |
| --- | --- | --- |
| 4B | `DONE` | 完成可靠后端 Agent：最终契约、三领域 Agent、按需 Planner、bounded Supervisor、安全/确认、状态缓存、Provider/RAG 可靠性和 32 条评测 |
| 4C | `DONE` | 完成患者端、浏览器 E2E、黄金演示和最终交付；MVP 产品功能在此收口 |
| 4D-A | `DONE` | 五组 gold 评测集已审核、冻结并写入 manifest hash |
| 4D-B | `IN_PROGRESS` | 统一 Agent 运行图和最终评测：有界 DAG、FinalClaim、v2 数据、故障注入、重复运行和指标报告；不新增业务领域 |

## 7. 4B 任务拆分与审计

任务一至四保留真实完成历史；此前过重的“任务五”已按 grill-me 决策拆分为可独立验收的任务五至十三。

| 任务 | 状态 | 目标 | 关键验收 |
| --- | --- | --- | --- |
| 1. 整理 Git 线性历史 | `DONE` | 保护旧成果并把 4B 放到线性基线上 | 当前分支从 `2571f91` 线性延伸，存在备份分支和 stash |
| 2. 解决 Alembic 冲突 | `DONE` | 统一迁移链和向量维度 | 当前唯一链 `0001 -> ... -> 0007`，pgvector 为 512 维 |
| 3. 统一向量 RAG | `DONE` | FastEmbed/pgvector + 关键词降级 | canonical embedding、HNSW、版本/hash/schema 和 SourceRef 已有离线回归 |
| 4. 接通新业务 Model Gateway | `DONE` | 新业务子图支持 deterministic/真实模型双模式 | 三条业务分支已接 Gateway；无 Key 可运行，失败保留 trace/fallback |
| 5. 最终契约与复杂度路由 | `DONE` | 冻结目标角色和结构化决策契约 | 新契约、deterministic Router、简单/复杂/高风险/歧义 gold cases 和旧工作流回归通过 |
| 6. 三领域 Agent 与 bounded Supervisor | `DONE` | 实现简单直达和复杂任务串行协作 | 三 Agent 各有有限决策点；Planner 最多 3 步；非法角色、依赖、超步数失败；无 Agent 级并行/自由重规划 |
| 7. 三层安全与确认状态机 | `DONE` | 消除 Safety 顺序和双重确认矛盾 | Request/Action/Output 三层门禁；自动 DRAFT；只确认执行；幂等、并发、越权和阻断测试通过 |
| 8. 分层状态与两次 run 续跑 | `DONE` | PostgreSQL 权威 checkpoint + Redis TTL cache | 首次/continuation run 同 task；Redis 丢失回源 PostgreSQL；不恢复 scratchpad；偏好写入需确认 |
| 9. Tool 与三类 Provider 可靠性 | `DONE` | 统一错误、有限重试和三个重点 Provider | 参数/权限错误不重试；timeout/429/可恢复 5xx 有限重试；三个 Provider 的 mock/degraded/schema/source 测试通过 |
| 10. RAG、成员隔离与可观测性补强 | `DONE` | RRF、来源决策、攻击式隔离和排障 Trace | keyword/vector/RRF/fallback、过期版本、跨成员资源攻击、缓存污染和脱敏 observation 测试通过 |
| 11. 32 条 Harness 与消融实验 | `DONE` | 用冻结业务 RunTrace 评测三种架构 | 32 条分类完整；A/B/C 共享模型、工具目录、RAG、安全、确认和 token 上限；可重复报告已生成 |
| 12. PostgreSQL/Redis/Docker 后端验收 | `DONE` | 验证迁移、缓存回源、并发确认、API 和真实 wall-clock | Docker PostgreSQL/Redis/FastAPI/Next.js、migration/seed、RAG 索引、Redis 故障、并发状态机和三业务 API 已通过 |
| 13. 4B 文档与 Git 收口 | `DONE` | 校准事实、报告并建立回滚点 | 文档无竞争路线图；真实指标复核；完整测试通过；4B tag 已创建并合并 main |

### 7.1 任务五：最终契约与复杂度路由

状态：`DONE`。本任务只冻结边界和确定性路由，没有修改旧 LangGraph 图，也没有实现 Supervisor 或领域 Agent。

交付：

- `ComplexityRoute`：`simple_single_domain` 或 `complex_cross_domain`，包含目标领域和理由码。
- `TaskPlan`：只为复杂请求生成，最多 3 个步骤，每步有 `step_id/role/objective/dependencies`。
- `AgentTaskResult`：统一返回 `status/facts/source_refs/tool_calls/missing_information/requested_confirmation/failure_reason`。
- `SupervisorDecision`：只允许 `call_role/retry/degrade/finish/stop`，包含 step、role、依赖和终止原因。
- `SafetyDecision`：区分 request、action 和 final-output 三种治理阶段。
- 三个目标领域角色的契约枚举、允许工具和完成条件边界。

已实现文件：

- `backend/app/agent/orchestration_schemas.py`
- `backend/app/agent/complexity_router.py`
- `backend/app/agent/safety.py`：增加 request/action/final-output 阶段和标准 outcome。
- `backend/tests/test_orchestration_contracts.py`
- `backend/tests/test_complexity_router.py`

验收：

- 简单任务不会创建 TaskPlan，也不会进入 Supervisor 循环。
- 复杂任务计划最多 3 步，角色只能是 Triage/Medication/Report。
- 模型只输出固定候选决策；非法字段、角色、工具或成员覆盖被拒绝。
- 当前旧角色保留兼容读取，但在目标工作流中不再作为独立 Agent 路由。
- deterministic Router 不访问数据库、LLM、Provider、Tool Registry 或 LangGraph；它只读取结构化身份、成员和用户输入。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_orchestration_contracts.py backend\tests\test_complexity_router.py backend\tests\test_agent_contract_schemas.py backend\tests\test_langgraph_workflow.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task5
```

### 7.2 任务六：三领域 Agent 与 bounded Supervisor

状态：`DONE`。本任务实现了不依赖外部系统的确定性领域编排内核；它消费任务五冻结的 `ComplexityRoute`、`TaskPlan`、`AgentTaskResult` 和 `SupervisorDecision`，不接入真实工具、Provider、数据库或 LangGraph。

目标运行链：

```text
trusted scope -> request safety -> complexity router
  -> simple: domain agent
  -> complex: one-shot TaskPlanner -> serial bounded Supervisor -> domain agents
  -> compose candidate -> final output safety
```

- Supervisor 不直接调用 Tool、不生成医疗回答、不修改计划目标。
- 每个 AgentTaskResult 必须回到 Supervisor；Agent 之间不得直接 handoff。
- 默认 deterministic；真实模型决策失败、越权或 schema 不合法时进入结构化失败或 deterministic fallback。
- `max_plan_steps=3`、`max_supervisor_steps` 和每角色最大调用次数必须配置并进入 Trace。
- 领域 Agent 内只允许对相互独立的只读查询使用受控异步并发；写状态仍串行进入 Policy Guard。

已实现：

- `TriageAgent`：只结构化预问诊/安全复核任务；歧义输入返回 `needs_clarification`，不生成诊断事实。
- `MedicationAgent`：只准备处方、药箱、库存、续方和提醒工作流的结构化草稿要求；关键动作标记需确认，不执行写操作。
- `ReportAgent`：只结构化报告任务并标记需要来源，不生成无来源医学结论。
- `DeterministicTaskPlanner`：仅接受复杂路由，一次性按冻结角色顺序生成最多 3 步串行依赖。
- `DeterministicBoundedSupervisor`：简单路由直达一个 Agent；复杂路由按依赖串行执行，支持有限重试、降级、澄清、失败和超步数终止。
- `DomainAgentInput`：只传任务摘要、冻结路由、当前步骤、角色工具白名单和结构化前序结果，不传完整聊天历史。
- `OrchestrationRunResult`：冻结路由、计划、Agent 结果、Supervisor 决策和终止原因，作为后续 Safety/Checkpoint/Trace 接入边界。

实现文件：

- `backend/app/agent/domain_agents.py`
- `backend/app/agent/orchestration.py`
- `backend/app/agent/orchestration_schemas.py`
- `backend/app/agent/__init__.py`
- `backend/tests/test_domain_orchestration.py`

验收：

- 简单请求不创建 `TaskPlan`，不产生 Supervisor 决策；复杂请求只创建一次 Planner 并串行执行。
- 角色只能来自 Triage/Medication/Report 白名单；角色工具只能来自对应 allowlist。
- 计划依赖只能指向前序步骤；最大计划步数、Supervisor 总步数和每角色调用次数均有上限。
- Agent 只能返回 `AgentTaskResult`；重试、降级、澄清和失败都有结构化 `SupervisorDecision` 与终止原因。
- 任务和 `member_id` 在路由、Agent 输入、前序结果和聚合结果之间保持一致。
- 本任务没有把 Tool/Provider 查询结果伪装成事实，也没有宣称真实医疗质量或线上性能指标。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_domain_orchestration.py backend\tests\test_orchestration_contracts.py backend\tests\test_complexity_router.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task6
```

### 7.3 任务七：安全和确认

状态：`DONE`。任务七没有修改 ORM、Alembic、seed 或前端；它在现有业务任务 runtime 上增加了可审计的纯状态机和三层治理接线。旧 `AgentRuntimeService`/旧确认草稿 API 保留兼容行为，最终新业务链路已采用下面的目标语义。

首次 run：

```text
request guard -> business execution -> action policy
-> persist local DRAFT -> Model Gateway candidate -> final output safety
-> freeze answer/evidence/trace -> deterministic evaluator -> END
```

确认 continuation run：

```text
reload task checkpoint -> revalidate user/member/draft/version/safety
-> idempotent DRAFT -> CONFIRMED -> EXECUTED(local only)
-> final acknowledgement safety -> freeze/evaluate -> END
```

新业务任务链路已经删除“用户先确认允许创建草稿”的目标语义；旧 `AgentRuntimeService` 和旧草稿 API 仍作为兼容接口保留，因此 API 文档必须明确两套契约的差异，直到后续统一迁移。

已交付：

- `backend/app/agent/safety_confirmation.py` 提供无副作用的 `ThreeLayerSafetyGuard`、`ConfirmationStateMachine`、作用域/版本/幂等契约和输出审计结果。
- `FamilyHealthProductWorkflow` 在请求入口、动作策略和最终答案冻结前记录独立 Safety decision；高风险请求不会进入业务工具。
- 新业务任务首轮会把本地草稿投影为 `confirmation_state=DRAFT`，响应携带 `confirmation_draft` 和 `external_action_status=not_submitted`；创建草稿不要求用户先确认。
- 确认续跑在同一 `task_id` 下重新校验 `user_id`、`member_id`、草稿版本、请求指纹和幂等键，再按 `DRAFT -> CONFIRMED -> EXECUTED` 推进；EXECUTED 仍只代表本地状态，不代表外部提交。
- `BusinessTaskService.confirm_task` 使用 PostgreSQL 行锁语义串行化确认判断；同一幂等请求回放，作用域、版本、指纹和状态冲突会结构化阻断。
- 任务七测试覆盖高风险拦截、危险最终答案、自动 DRAFT、确认缺失、重复确认、成员越权、幂等冲突、版本冲突和完整业务 API 回归。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_safety_confirmation.py backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task7
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest\4b-task7-full
```

### 7.4 任务八：状态、缓存和偏好

状态：`DONE`。任务八把两次独立 run 的续跑边界落成可迁移、可审计的持久化契约。

已交付：

- Alembic `0007_task_checkpoint_state` 新增 `task_checkpoints`、`task_confirmation_records` 和 `confirmed_preferences`；`business_tasks` 保存当前 checkpoint/confirmation version，`agent_runs.parent_run_id` 记录 continuation 因果关系。
- `TaskCheckpointService` 在事务内写入不可变 PostgreSQL checkpoint，冻结 RunSummary、步骤进度、确认状态、最终产物和来源指针；续跑只投影允许恢复的最小状态，重新读取可变业务事实。
- `TaskCheckpointCache` 的 Redis key 包含 `user_id/member_id/task_id/thread_id/checkpoint_version` 并设置 TTL。miss、过期、作用域/版本不匹配或 Redis 异常都会回源 PostgreSQL；Redis 不保存唯一事实。
- `/api/business-tasks/{task_id}/confirm` 支持 checkpoint/confirmation version 乐观并发校验；`ConfirmedPreferenceService` 只接受同 task 的已执行确认、匹配 source/version 和显式 `human_confirmation_granted=true`，并保存可撤销的版本化偏好。

实现文件和测试边界统一见 [上下文管理](CONTEXT_MANAGEMENT.md)、[数据库设计](DB_SCHEMA.md) 与本节验收记录。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_business_task_api.py backend\tests\test_task_checkpoint_cache.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task8
```

历史顺序为任务十一完成后进入任务十二，再进入任务十三“4B 文档与 Git 收口”；三项现均已完成，当前 `NEXT` 以 4D-B 执行顺序为准。

### 7.5 任务九：Tool 和 Provider

状态：`DONE`。本任务把 Tool/Provider 的失败语义、有限重试、attempt trace 和来源边界落成可运行代码；没有接入真实医院或药店，也没有执行外部写操作。

重点 Provider：

1. `MedicalDocumentParserProvider`
2. `PharmacyProvider`
3. `HospitalOrConsultationProvider`

现有其他 mock adapter 只作为兼容实现，不新增空能力，不作为最终简历重点。统一错误至少覆盖 validation、permission、not-found、timeout、rate-limit、provider-unavailable、business-conflict、schema 和 internal error。任何降级不得伪造预约、库存、通知或外部写入成功。

已交付：

- `backend/app/core/reliability.py` 提供稳定错误分类；旧错误名仍可兼容，但 Trace 使用统一 `error_category`。
- `ToolRegistry` 对只读工具的 timeout、rate-limit 和临时 provider-unavailable 按固定上限重试；参数、权限、schema、业务冲突、内部错误和写工具不重试。
- `ProviderRegistry` 记录逐次 `ProviderAttemptTrace`、总耗时、最终降级原因，并在身份、模式或 operation 不匹配时返回结构化 schema failure。
- `MedicalDocumentParserProvider` 保留文档版本、parser version 和原文区间；`PharmacyProvider` 只返回库存候选；`HospitalOrConsultationProvider` 只返回科室、时段或问诊草稿候选。
- mock 成功来源明确标记 `simulation=true`；sandbox/real 未配置、重试耗尽或 schema 失败时 `success=false`、`degraded=true`、`source_refs=[]`，且订单、预约、问诊提交始终为 false。
- Provider attempt/error/source 信息进入 ToolResult、业务响应和现有 `provider_calls.response_payload` 审计 JSON；本任务未新增 ORM 或 Alembic migration。

实现与测试文件：

- `backend/app/providers/reliable.py`
- `backend/app/providers/registry.py`
- `backend/app/providers/schemas.py`
- `backend/app/tools/tool_registry.py`
- `backend/app/tools/tool_schemas.py`
- `backend/tests/test_provider_reliability.py`
- `backend/tests/test_provider_adapters.py`
- `backend/tests/test_tool_registry.py`
- `backend/tests/test_business_task_api.py`

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_provider_adapters.py backend\tests\test_provider_reliability.py backend\tests\test_tool_registry.py backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=output\pytest-task9
```

详细边界统一见 [Tool 契约](TOOL_CONTRACTS.md) 与本节验收记录。

### 7.6 任务十：RAG、隔离和 Trace

状态：`DONE`。本任务未新增 ORM 表或 Alembic migration，也未引入 OpenTelemetry/Jaeger；它补强现有 RAG、Repository/Tool 作用域和冻结 RunTrace。

- 使用 RRF 融合 keyword/vector rank，不直接比较不同量纲的 raw score。
- 保存 keyword rank、vector rank、RRF score、文档/分块版本、embedding schema 和 fallback reason。
- Repository/Tool 在同一 SQL 条件中约束 user/member/resource；测试旧资源 ID、伪造成员、Prompt 注入和缓存残留。
- RunTrace/Observation 覆盖 request、task、run、node、tool、provider、latency、retry、fallback、source、model/token，并执行敏感字段白名单/脱敏。

实现结果：

- `RetrievedChunk` 同时保存两路原始分数、各自 rank 和最终 RRF score；hybrid 排序只使用 RRF，原始分数只用于审计。
- `VectorMatch` 冻结文档版本、分块版本和 embedding schema；与 PostgreSQL 当前权威版本不一致时拒绝向量命中并记录明确 fallback reason。
- 档案、处方和药箱读取在 SQL 中同时约束用户、成员和资源归属；Tool Pydantic 契约拒绝额外 Prompt/身份字段，Redis 跨成员残留被视为 cache miss。
- `ObservationTrace` 是冻结、`extra=forbid` 的白名单事件；保留 ID、节点、结果、时延、重试、降级、来源、模型和可用 token 计数，不保留请求正文、Tool/Provider payload、Prompt、最终答案正文或凭据。
- 84 条任务十定向测试和 287 条后端全量测试通过；这些是本地自动化结果，不是线上 RAG 召回率、临床正确率或生产 p95。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:PYTHONPYCACHEPREFIX=(Resolve-Path 'output').Path + '\pycache-task10'
python -m pytest backend\tests -q --basetemp output\pytest-task10-full
python -m compileall backend\app backend\tests
```

详细边界统一见 [RAG 设计](RAG_RETRIEVAL.md)、[测试指南](TESTING_GUIDE.md) 与本节验收记录。

### 7.7 任务十一：32 条 Harness

状态：`DONE`。实现位于 `backend/app/agent/ablation_schemas.py`、`backend/app/agent/ablation_harness.py` 和 `backend/tests/fixtures/business_harness_cases.4b.json`。运行器对 32 条固定业务 case 分别生成 Single-Agent、固定路由和 bounded Supervisor 三组冻结 `RunTrace`，共 96 份评测结果；三组共享 `FairnessConfig`，不得更换模型身份、工具目录、RAG 索引、安全/确认策略或 token 上限。

| 类别 | 数量 |
| --- | ---: |
| 正常单领域任务 | 6 |
| 跨领域复杂任务 | 6 |
| 信息缺失与澄清 | 3 |
| 高风险医疗请求 | 5 |
| RAG 与来源 | 4 |
| Provider/工具异常 | 3 |
| 成员隔离攻击 | 3 |
| 确认、重复与并发 | 2 |
| 合计 | 32 |

公平比较三种架构：

- A：Single-Agent baseline。
- B：Router + 固定领域子图。
- C：按需 Planner + bounded Supervisor。

三组必须共享模型、工具、RAG、Safety、确认状态机、知识、上下文限制和 token 上限。分别报告简单任务和复杂任务；Safety 和成员隔离带来的收益不得归因给 Supervisor。

重点指标：任务完成率、工具集合/参数 exact-match、Supervisor 路由顺序、不必要 handoff、重复工具调用、高风险召回/精确率、成员隔离、治理覆盖、RAG Recall@3/@5、引用正确率、P50/P95、token 和成本。32 条是 4B 硬门槛；48 条只根据真实 bad case 自然扩展。

本地 deterministic 报告见 [任务十一消融报告](agent_ablation_report.4b.md)。结果显示：固定路由在 26 条简单任务上完成率为 1.0000，6 条复杂任务为 0.0000；bounded Supervisor 在简单/复杂任务上均为 1.0000，工具集合与参数 exact-match 均为 1.0000；Single-Agent 完成率为 1.0000，但工具 exact-match 为 0.3750 且存在重复调用。三组 Safety、成员隔离、治理覆盖和 RAG 指标一致，因此这些收益不归因给 Supervisor。

以上只属于冻结 deterministic fixture 的架构回归证据。P50/P95 是固定 fixture latency，不是服务 wall-clock；deterministic provider 没有返回 token usage，因此 token 和成本保持 `N/A`。任务十二已经补充真实本机 PostgreSQL/Redis/Docker 和 wall-clock 验收，但这些结果仍不是生产 SLO、临床安全或真实模型质量指标。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.ablation_harness
python -m pytest backend\tests\test_ablation_harness.py -q -p no:cacheprovider --basetemp output\pytest-task11
```

任务十一专项测试 6 项通过；完整后端回归 293 项通过，伴随 4 条既有依赖/配置弃用 warning。

### 7.8 任务十二：PostgreSQL/Redis/Docker 后端验收

状态：`DONE`。验收使用本机 Docker Compose 的 PostgreSQL、Redis、FastAPI 和 Next.js，不调用 LLM、不访问真实医院/药店 Provider，也不把本机耗时写成生产性能指标。脚本位于 `scripts/task12_acceptance.py`，结果快照见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。

验收结果：

- baseline：19/19 checks 通过；Alembic head 为 `0007_task_checkpoint_state`，seed 数据可读，pgvector 中 4 个 chunk 均为配置的 512 维，三条业务 API、知识检索、422 错误映射和前端 health 通过。
- 并发确认：4 个相同确认请求只产生 1 次真实执行，另外 3 次返回状态冲突；没有重复写入。
- Redis 故障：Redis 不可用时检测到故障，业务任务仍从 PostgreSQL 恢复 checkpoint，18/18 checks 通过。
- wall-clock：baseline 样本 13 个，p95 为 426.67 ms；Redis 故障样本 10 个，p95 为 9407.17 ms。后者包含故障连接等待，只能作为本机回归记录。

验证命令：

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
docker compose up -d --build --wait --wait-timeout 300
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

Redis 故障场景需要临时停止 Redis，运行 `--mode redis-failure` 后立即执行 `docker compose start redis`。该检查验证回源与一致性边界，不代表高可用、压测或生产灾备。

### 7.9 任务十三：4B 文档与 Git 收口

状态：`DONE`。本任务完成了 4B 的文档、测试和 Git 收口。

- 删除并保留删除已确认的竞争路线图/过时审计文档：`NEXT_STEPS.md`、`docs/CURRENT_STATE_AUDIT.md`、`docs/IMPLEMENTATION_PLAN.md` 和旧项目 Prompt。
- 复核 README、API、DB、Agent、RAG、安全、部署、测试、学习和面试材料；所有阶段状态继续只引用本文档。
- 记录任务十二真实 Docker 报告、后端/前端最终测试和未实现边界；没有把 deterministic、mock 或本机 wall-clock 写成生产指标。
- 当前分支已提交并建立 4B 回滚 tag，随后以 fast-forward 方式合并到本地 `main`；未自动推送远端。

最终验证：

```text
Backend: 297 passed, 4 dependency/config deprecation warnings
Frontend: 23 passed; TypeScript typecheck passed; Next.js production build passed
Docker Task 12: baseline 19/19; Redis failure 18/18
```

## 8. 4C 最终产品交付

4C 只完成最终患者端和交付，不再新增后端架构名词：

| 任务 | 状态 | 目标 | 关键验收 |
| --- | --- | --- | --- |
| 4C-1 患者端信息架构与视觉壳层 | `DONE` | 以药品/健康服务场景常见的搜索、分类、快捷入口和状态卡片为参考，重做患者端首页与导航 | 桌面端/移动端可用；成员作用域清晰；不引入药品价格、支付或真实下单暗示 |
| 4C-2 黄金链路 UI | `DONE` | 接通慢病续方、用药提醒两条黄金链路的草稿审阅、确认续跑、来源和安全状态 | `/agent` 展示首次 run -> `DRAFT` -> 用户确认 -> continuation run；blocked/degraded/无来源状态可解释 |
| 4C-3 浏览器 E2E | `DONE` | 为续方、提醒各写 2–3 条浏览器场景，预问诊作为第三条回归线 | 成功、拒绝确认、高风险拦截、成员切换和 API 失败路径可重复 |
| 4C-4 固定演示与最终交付 | `DONE` | 一键启动、黄金演示、测试报告和 README 收口 | 5 分钟完成演示；Docker、迁移、seed、后端 Harness、浏览器 E2E 证据齐全 |

### 8.1 4C-1 设计决策：患者端不是电商下单页

美团买药等健康服务界面常见的有效信息架构是：顶部搜索、按需求分类、快捷服务入口、附近供给/配送信息和清晰的状态反馈。本项目借鉴这些交互结构，不复制品牌视觉、促销话术或交易流程：

- 顶部保留当前成员、搜索/任务入口和安全提示，让用户先明确“正在为谁处理什么事”。
- 分类改为“续方材料、用药提醒、复诊材料、知识检索、家庭药箱”，每个入口都说明系统能做什么和不能做什么。
- 药店库存只展示候选库存、配送/自提能力和来源，不出现“立即购买”“支付成功”或已提交订单状态。
- 首页卡片优先展示 `DRAFT`、待确认、已阻断、来源和外部动作未提交等业务状态。
- 任何患者端页面都不能绕过 `member_id` 隔离、SafetyAgent、确认状态机和只读 Trace。

4C-1 当前实现边界：只修改 `frontend/` 以及对应前端文档和测试，不新增后端业务接口；已有 API 不满足页面需求时，先在现有 DTO 中寻找可用字段，不通过前端拼接医疗事实。

### 8.2 4C-2 黄金链路 UI

状态：`DONE`。本任务只改造患者端 `/agent` 的展示和交互，不新增后端接口、不改变确认状态机。

交付内容：

- 用五步生命周期展示 `首次 run -> DRAFT -> 用户确认 -> continuation run -> 本地记录完成`。
- 展示 `task_id`、当前 `run_id` 和 `resumed_from_run_id`，让用户看懂同一任务的两次 run 关系。
- 只有后端返回 `needs_confirmation` 且未被 SafetyAgent 拦截时，才展示确认区和“确认并创建本地草稿”按钮。
- 明确外部动作仍为 `not_submitted`，高风险请求显示 `BLOCKED` 且没有确认按钮。
- 保留 Tool/RAG source、Safety、EvaluationResult 和只读 Trace 入口。
- Docker 部署文档补充数据库、backend、Agent（运行在 backend 内）和 frontend 的启动、日志、健康检查与停止方式。

验证：

```text
Frontend Vitest: 5 files, 25 passed
TypeScript typecheck: passed
Next.js production build: passed
Docker Compose: postgres/redis/backend/frontend healthy
HTTP smoke: backend /health = 200; frontend / = 200
```

### 8.3 4C-3 浏览器 E2E

状态：`DONE`。本任务只增加患者端浏览器级回归，不改变后端业务契约。测试使用 Docker 中的 deterministic backend，浏览器通过真实 HTTP 请求访问 `http://localhost:3000`，不调用真实 LLM 或外部 Provider。

场景覆盖：

- 续方首次运行进入 `DRAFT`，未勾选确认时按钮保持禁用，验证“拒绝/暂不确认”不会推进副作用。
- 续方确认后产生 continuation run，并展示 `LOCAL_COMPLETED` 与续跑来源。
- 用药提醒确认后完成本地草稿闭环。
- 高风险加量请求被 `SafetyAgent` 拦截，不显示业务确认按钮。
- 切换 `member_id` 后清理前一成员的运行结果，页面只保留新成员作用域。
- 模拟 Agent API 失败时展示可读错误，不伪造成功答案。

验证：Playwright 使用本机 Edge 执行 7 条场景，结果为 `7 passed`；Docker Compose 的 PostgreSQL、Redis、backend、frontend 均为 `healthy`。详细结果见 [4C 浏览器 E2E 验收报告](browser_e2e_report.4c.md)。该结果只证明本机 deterministic 演示链路可重复，不是生产 SLO、临床安全率或真实 LLM 指标。

### 8.4 4C-4 固定演示与最终交付

状态：`DONE`。本任务没有新增业务 API、数据库表、Agent 角色或模型能力，只把已有交付物组织成一条可重复的本地 MVP 验收路径。

```powershell
Set-Location E:\project_code\hospital
.\scripts\closeout_4c.ps1
```

脚本按固定顺序执行：

1. 构建并启动 PostgreSQL、Redis、backend 和 frontend；backend 启动入口执行 Alembic migration、幂等 seed 和可选索引准备。
2. 通过公开 Runtime API 执行四个固定业务场景，验证 `DRAFT -> confirmation -> continuation`、高风险 `BLOCKED`、来源和 `external_action_status=not_submitted`。
3. 在宿主机离线运行 deterministic Agent Harness 和 Single Agent / fixed router / bounded Supervisor A/B/C 消融；Harness fixture 不进入 backend 生产镜像。
4. 使用本机 Edge 通过真实 HTTP 执行 7 条浏览器 E2E，验证患者端确认、成员隔离、安全拦截和 API 失败路径。
5. 把脱敏结果写入被 Git 忽略的 `var/closeout/`，失败时返回非零退出码。

本次本机收口结果：固定 Demo `4/4`、backend/frontend health `200`、Harness/A/B/C `PASS`、浏览器 E2E `7/7`。详细记录见 [4C-4 MVP 收口报告](mvp_closeout_report.4c.md)。

## 9. 简历和指标边界

- 设计能力只能写“设计了”；代码和测试完成后才能写“实现了”。
- deterministic/mock、sandbox、real 数据必须分开。
- 只有真实生成并复核的报告数值可以写入简历。
- 不把 fixture 预填 latency 写成服务性能，不把确认提示率写成人工采纳率。
- 不把 Safety、Tool 权限或成员隔离的提升归因给 Supervisor。
- 多 Agent 是否优于固定路由由 A/B/C 消融实验决定；若简单任务固定路由更快，应如实保留复杂度分流结论。

## 10. 4D 简历指标与评测证据化

4D 不增加新的医疗能力，也不把本地评测包装成生产指标。目标是把 [简历学习文档 5.2](learning/RESUME_GUIDE.md#52-下一轮简历指标怎么测) 中的测量方案落成版本化测试集、可重复 runner 和 JSON/Markdown 报告。所有简历数字必须能回到固定 case、Git commit、运行环境和计算公式。

### 10.1 4D-A：候选用例生成与人工 gold 审核

状态：`DONE`。五组共 260 条候选用例已经按用户授权完成审核标记、Pydantic/JSON 校验、source_id 校验和 hash/manifest 冻结。本任务只冻结“什么是正确”，不把批量审核本身当作模型质量证据；后续真实回答 badcase 仍需人工复核。

AI 可以生成测试问题和表达变体，也可以根据现有知识文档预填候选 `source_id`、安全标签和必须包含/禁止出现项；但 AI 生成的内容只是候选数据，不能让同一个模型同时出题、给标准答案并证明自己正确。你负责最终审核，Codex 负责生成初稿、审核表、数据校验脚本和修改说明。

#### A.1 数据集与最低规模

| 数据集 | 最低规模 | Codex 先生成什么 | 你最终确认什么 |
| --- | ---: | --- | --- |
| 回答质量 | 60–100 条 | 从黄金链路、异常路径和现有 fixture 生成中文问题；预填必须包含、禁止出现、应拒答、应确认 | 问题是否自然；规则标签是否符合业务边界；不能要求模型给诊断或改药结论 |
| RAG gold | 至少 30 条 | 从现有知识 chunk 反向生成同义问法、关键词问法和混合问法；预填候选 `source_id` | 每个问题应该命中哪些已存在来源；问题是否泄露答案原句 |
| Agent 安全 | 至少 100 条：50 高风险 + 50 普通 | 生成口语、错别字、隐含改药、严重症状、越权成员和容易误报的普通表达 | `must_block`、安全标记和普通请求标签；只按项目安全规则审核，不把它当临床诊断题 |
| 上下文与记忆 | 40 条 | 生成同任务多轮、换任务、换成员、确认/未确认偏好、缓存故障和版本冲突用例 | 应保留、应删除、允许长期写入的 `fact_id/source_id/member_id` |
| Provider 故障 | 至少 30 条 | 生成 timeout、429、可恢复 5xx、格式错误、权限错误和写操作失败组合 | 哪些错误允许有限重试，哪些必须立即失败；写操作误重试必须为 0 |

固定文件规划：

```text
backend/tests/fixtures/benchmarks/answer_quality.v1.json
backend/tests/fixtures/benchmarks/rag_gold.v1.json
backend/tests/fixtures/benchmarks/safety_gold.v1.json
backend/tests/fixtures/benchmarks/memory_context.v1.json
backend/tests/fixtures/benchmarks/provider_faults.v1.json
backend/tests/fixtures/benchmarks/benchmark_manifest.v1.json
docs/4D_B_BENCHMARK_GUIDE.md
```

#### A.2 你实际需要做什么

1. Codex 先从仓库现有知识、业务 fixture 和安全规则生成候选数据，不要求你从空白开始写题。
2. 你按照审核文档逐条选择“通过、修改、删除”；重复表达可以保留，但必须覆盖不同语言现象，不能只改一个标点。
3. RAG 用例核对 `source_id` 是否真实存在；回答质量只标注关键事实和禁用表达，不编写一篇唯一标准答案。
4. 安全用例只判断项目应当放行、确认、拦截或转人工，不要求你判断疾病和处方是否正确。
5. 上下文用例确认哪些事实属于当前任务和成员，哪些只是未确认猜测。
6. 如果要测真实 LLM，你在未提交的 `.env` 中填写模型地址、Key、模型名和官方输入/输出价格；Key 不进入 fixture、报告或 Git。
7. 跑延迟测试前确认本机没有大型任务，并允许 Docker 连续创建本地测试记录；测试数据只能使用 seed/合成数据。

#### A.3 人工审核门

每条 gold case 必须包含：

- 唯一 `case_id` 和数据集版本。
- `generated_by_ai=true/false`，记录是否由 AI 生成初稿。
- `human_reviewed=true`、审核日期和非敏感 reviewer 标识。
- 期望行为、来源或安全标签，不允许只保存“回答应该正确”。
- 不包含真实患者姓名、身份证、电话、病历或真实 API Key。

`benchmark_manifest.v1.json` 记录各数据集 hash、数量、标签分布、知识库版本、模型配置名和价格版本。任何 gold 修改都必须升级版本或更新 hash，避免边跑边改标准答案。

#### A.4 完成标准

- 五组数据达到最低数量，并全部通过 Pydantic/JSON 校验。
- RAG 的每个期望 `source_id` 都能在当前知识库找到。
- 高风险/普通、安全动作、家庭成员和业务域分布有统计，不用总 case 数掩盖缺组。
- 所有 case 完成人工审核；AI 候选未审核时不能进入正式报告。
- 真实模型配置与价格可以选择暂不提供；此时 4D-B 先完成 deterministic 自动化，但 token/成本和真实回答质量保持 `N/A`，不伪造数字。

### 10.2 4D-B：统一自动化评测与最终指标

状态：`IN_PROGRESS`，依赖 4D-A 已冻结的 `benchmark_manifest.v1.json`。

- `B1 DONE`：Pydantic 契约、manifest/hash 校验、deterministic 数据契约 runner、报告和 `N/A` 真实性边界。
- `B2 PARTIAL`：本地观测 runner 已执行 32 次 bounded Supervisor、12 次真实 `KeywordRetriever` 查询、40 次 ContextManager compact/reset 和 30 次 Provider 故障注入；结果写入 `docs/local_benchmark_report.4d.md`。这些使用合成 fixture 和本地实现，不是 Docker pgvector、真实外部 Provider 或真实 LLM 指标。
- `B2.1 DONE`：新增 `UnifiedHealthGraph`，将 `/api/business-tasks` 接入统一 Router/Planner/Supervisor 边界；业务执行继续由现有 ProductWorkflow 适配器负责数据库工具、确认和冻结，`RunTrace.orchestration` 已保存编排投影。
- `B2.2 DONE`：Supervisor 已支持依赖 ready-set、有界只读 fan-out/fan-in、确定性 reducer 和写步骤串行隔离；`EvalRuntimeOptions` 与 ContextManager 已提供仅评测可用的结构化 `all_history`，生产默认仍为 `dependency_only`。
- `B2.3 DONE`：已增加结构化 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`，产品业务冻结产物会保存成员、来源指针、依赖结果和 token usage（若 provider 提供），deterministic Evaluator 已增加 Claim 覆盖率、来源精度和正文/Claim 一致性校验。
- `B2.4 DONE（待人工审核/物化）`：已用固定 seed 生成独立的 300 个 WorldState 和 1200 条 v2 Query，完成 development/validation/holdout 切分、四种表达变体、关联校验和 SHA-256 manifest；数据明确标记为 `pending_review`，不能当作临床 gold 或最终评测结果。
- `B2.5 DONE（本地 preview）`：已实现隔离的内存 WorldState Materializer、九类确定性 Grader、失败原因分类和统一 v2 Eval Runner；可生成 1200 条 preview 报告。当前 runner 不访问 PostgreSQL、Provider、RAG、LLM，preview 数字不进入简历。
- `B3 OPTIONAL`：配置真实 OpenAI-compatible provider 后，执行回答质量、真实 token/cost 和模型延迟评测；没有 Key 时继续保持 `N/A`，不影响 deterministic 项目运行。

4D-B 的最终数据规模、架构升级、指标公式、执行任务和简历口径统一见 [Agent 统一架构、评测数据与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。DAG 并行、`all_history` 评测基线、UnifiedHealthGraph、FinalClaim/Trace v2、v2 数据生成、Materializer、分层 grader 和本地 preview Runner 已完成；人工审核后的 PostgreSQL/Provider/RAG 物化、真实业务图执行、消融和正式报告仍属于后续目标；LLM Judge 仍只作为离线辅助。

#### B.1 自动化实现

1. 保留现有 260 条 v1 专项 gold、32 条 A/B/C 编排 fixture 和当前 manifest，作为兼容回归基线。
2. 新增 UnifiedHealthGraph，将 Complexity Router、一次性 Planner、bounded Supervisor、三个领域 Agent 和固定治理边接入当前 HTTP 主链。
3. 把复杂任务建模为有界 DAG；只并行依赖已满足、无副作用的只读领域步骤，确认、写操作、Checkpoint 和治理节点保持串行。
4. 新增仅供评测使用的 `all_history` 上下文模式，与生产默认 `dependency_only` 比较；即使在基线中也必须保持 user/member 隔离。
5. `[DONE]` 为 FinalAnswer 增加 FinalClaim，保留成员作用域、事实键、值、类型和 `source_ids`，避免评测时再用 LLM 从正文猜事实。
6. `[DONE]` 生成 300 个结构化 WorldState，并为每个 WorldState 生成 4 条表达，共 1200 条 v2 Query；按 base case 拆分 development、validation 和 holdout，数据状态为 `pending_review`。
7. `[DONE]` 先用隔离内存 backend 物化 WorldState、Provider 投影、RAG namespace 和 Gold，验证 case namespace、成员来源范围、清理和失败阻断；生产 PostgreSQL/Provider/RAG adapter 已在 B2.6 增加 shadow transaction 边界。
8. `[DONE]` 为 Route、Plan、Dependency、Tool、Claim、RAG、Agent 安全、上下文、可靠性和最终数据库状态建立确定性 grader，并统一 failure taxonomy。
9. `[DONE]` 实现统一 v2 Eval Runner、split/max_cases/repeat、幂等 report id、JSON/Markdown 输出和 pending-review gate；B2.6 已增加 A/B/C/D preview、真实图执行器和 Docker 集成报告入口。

#### B.2 报告与证据

已生成或计划生成：

```text
output/benchmarks/benchmark_report.4d.json
docs/benchmark_report.4d.md
docs/local_benchmark_report.4d.md
docs/benchmark_badcases.4d.md
```

报告必须包含 Git commit、manifest hash、运行时间、模式、模型名、知识版本、样本数、公式、聚合指标、置信区间或重复运行波动、失败 case 和真实性边界。deterministic、真实模型和 Docker wall-clock 结果分表展示，不能混成一个总分。

#### B.3 最终可选择的简历指标

只从实跑且复核完成的结果中选择三到五项：

- 真实回答规则通过率及样本数，不称临床准确率。
- RAG Recall@3/@5 和引用正确率。
- Agent 安全召回率与普通请求误报率，注明固定安全集。
- 上下文关键信息保留率、跨成员泄漏率和恢复成功率。
- Provider 故障恢复率与写操作误重试率。
- 本机 p50/p95、平均 token 和成本，明确模型、硬件和测试环境。

#### B.4 完成标准

- 同一 manifest 和 commit 的 deterministic 结果可重复。
- 患者端 HTTP RunTrace 已包含 Router、Plan、Supervisor decision 和领域 Agent result；当前主运行架构不再与独立编排内核相互矛盾。
- UnifiedHealthGraph 已通过统一入口保存 Router/Plan/Supervisor/领域结果；4D-B2.2 的只读 DAG fan-out/fan-in 已在 bounded Supervisor 内核完成，固定业务适配器的安全、确认、冻结和副作用仍串行。
- 300 个 WorldState、1200 条 v2 Query 已按 base case 拆分 development、validation、holdout，并通过固定 seed、hash 和关联校验；本地物化、清理和失败恢复已完成，真实 PostgreSQL/Provider/RAG 物化仍待完成。
- v2 本地 preview Runner 已对 1200 条 Query 生成九层 grader 结果、task success、各层通过率和 p95 preview latency；该报告只证明评测管线接线，不证明业务质量。
- FinalClaim 可以在不解析自然语言正文的情况下完成事实、来源和成员评分。
- A/B/C/D 四种路由、执行和上下文模式能够运行同一数据集并生成可比较报告。
- 所有指标能追溯到 case、冻结运行产物和计算公式。
- 故意失败用例必须被 runner 识别，不能只证明成功路径。
- 自动化、Docker 集成和可选真实模型运行分别生成报告。
- `README`、测试指南、面经、核心代码学习文档和简历口径同步更新。
- 只有报告中的真实数字可以进入简历；未提供 Key 或人工 gold 时对应指标保持 `N/A`。

### 10.3 执行顺序

```text
4D-A1 候选用例和审核表 DONE
  -> 4D-A2 人工 gold 审核 DONE
  -> 4D-A3 校验并冻结 benchmark manifest DONE
  -> 4D-B1 契约、manifest 和 deterministic 报告 DONE
  -> 4D-B2 本地实现观测 PARTIAL
  -> 4D-B2.1 UnifiedHealthGraph DONE
  -> 4D-B2.2 有界 DAG 并行和评测用 all_history 基线 DONE
  -> 4D-B2.3 FinalClaim / Trace v2 DONE
  -> 4D-B2.4 300 WorldState / 1200 Query DONE（待人工审核/物化）
  -> 4D-B2.5 Materializer / Graders / Eval Runner DONE（本地 preview）
  -> 4D-B2.6 DONE（实现与本机证据层）：PostgreSQL/Provider/RAG 物化、真实图样例、真实 A/B/C/D 单样例和 Docker 回归已通过；正式全量指标仍受人工审核/身份映射门槛约束
  -> 4D-B3 DONE：可选真实 LLM、token、成本和性能测试；8 条 development 样本已人工复核并冻结 final report
  -> 人工复核 B3 badcase DONE（8/8 通过）
  -> 更新简历与面经真实指标 DONE（明确 8 条样本范围）
  -> 补齐 v2 全量 identity/source map 与三 split integration/A-B-C-D 正式报告 NEXT
```

## 11. 明确非目标

- 疾病诊断、自动开方、处方修改或剂量调整建议。
- 未经确认的受保护状态迁移，或真实医院、药店、支付和通知写操作。
- 完整认证、多租户、生产级合规认证和互联网医疗知识自动抓取。
- 无边界 Agent 并行、写操作并发、无限循环和运行时复杂自动重规划。
- MCP Server、OpenTelemetry/Jaeger 和生产级分布式追踪平台。
- 长期完整聊天存储、个人健康向量记忆、模型自动写回医疗事实。
- 七个 Provider 都做成完整外部集成。
- LLM Judge 进入运行链或成为最终验收硬门槛。
- 以 48 条用例数量替代 32 条高质量覆盖。

## 12. 当前唯一下一步

`4B` 和 `4C` 已完成，MVP 产品能力已经收口。4D-A 的五组 v1 gold 已完成人工审核并冻结 manifest；4D-B2.1 至 B2.6 的实现与本机证据层已经完成，Docker 证据为 19/19 通过。4D-B3 也已完成：`deepseek-v4-flash` 在 8 条 development 固定样本上真实运行，人工对 FinalAnswer 和冻结草稿/来源快照逐条复核，8/8 通过；平均总 token `1032.5`、平均单次成本 `$0.00146525`、本机 workflow/model p95 为 `5239/4452 ms`，final report 和 manifest 已冻结。

当前唯一下一步是补齐 300 个 WorldState/1200 条 Query 的人工审核与本机 identity/source map，再运行 development/validation/holdout 的完整 integration 和 A/B/C/D 正式报告。B3 的 8 条结果只能按固定样本范围写入简历，不能扩展为生产 SLO、临床安全率或开放医疗问答准确率。

2026-07-30 完成一次 4C 后文档与证据维护：补充面向初学者的逐行核心代码走读、简洁版 Agent 简历、可复现指标与后续 gold set/延迟/Token/重试测量方案、测试充分性边界、本地演示数据库说明和十步 Docker 启动路径。本次维护不改变阶段状态，不把尚未接入业务 API 的 bounded Supervisor 编排内核描述为当前运行链能力。

2026-07-31 完成文档信息架构收口：学习区只保留“从 0 到 1 的任务拆分与技术选型、核心代码逐行走读、完整 API 实战”三条工程主线，简历和项目面经独立分类；删除被当前设计覆盖的阶段教程、旧 3C/3D/4A 与局部 4B 报告和无关通用八股。当前有效证据只保留 32 条编排消融、Docker 后端验收、浏览器 E2E、MVP 收口和 4D 报告。本次整理不改变 4D-B 状态，也不改写简历或面经正文。

2026-07-31 根据最终评测实施方案升级 4D-B：保留 260 条 v1 专项 gold，同时将 UnifiedHealthGraph、有界 DAG 并行、评测用 `all_history` 基线、FinalClaim、300 个 WorldState/1200 条 v2 Query、分层 grader 和统一 Eval Runner 纳入最终目标。生产默认仍使用角色最小上下文，确认、写操作和治理节点保持串行。简历继续使用简洁中文口径，所有新增百分比必须由最终报告生成。

2026-08-01 完成 4D-B2.1：`UnifiedHealthGraph` 接入 `/api/business-tasks`，复用现有 ProductWorkflow 完成业务工具、确认、安全和冻结；`RunTrace.orchestration` 保存统一编排投影，并新增统一图边界测试。

2026-08-01 完成 4D-B2.2：TaskPlan 支持显式依赖边、只读标记和并行上限；bounded Supervisor 已实现 ready-set、受控 worker fan-out、按 step_id 确定性归并、有限重试和写步骤隔离；`all_history` 仅可由评测运行选项开启。随后进入 4D-B2.3 FinalClaim / Trace v2。

2026-08-01 完成 4D-B2.3：新增 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`；业务冻结答案与 claims 同步生成，Claim 强制绑定 `member_id` 和 `source_ids`，RunTrace 保存上下文来源、依赖结果和可选 token usage；deterministic Evaluator 新增 Claim evidence coverage、source precision 和 consistency 校验。当前唯一下一项为 4D-B2.4 的 300 个 WorldState / 1200 条 v2 Query。

2026-08-01 完成 4D-B2.4：新增 `v2_benchmark_schemas.py` 和 `v2_benchmark_generator.py`，生成 `backend/tests/fixtures/benchmarks/v2/` 下的 300 个 WorldState、1200 条 Query 和 manifest；固定 seed 为 `20260801`，切分为 180/60/60 个 WorldState，四种表达保持同一 base case 和 split。数据当前为 `pending_review`，唯一下一项为 4D-B2.5 Materializer / Graders / Eval Runner。

2026-08-01 完成 4D-B2.5：新增 `v2_materializer.py`、`v2_graders.py`、`v2_eval_schemas.py` 和 `v2_eval_runner.py`，实现隔离内存 WorldState projection、九类确定性 grader、failure taxonomy、pending-review gate、稳定 report id、JSON/Markdown preview 报告和 1200 条 Query 全量 preview。修正并重新生成多成员 Gold 的来源范围，保证 expected source 不包含其他成员事实。当前唯一下一项为 4D-B2.6：真实 PostgreSQL/Provider/RAG 物化、UnifiedHealthGraph 集成、A/B/C/D 消融和 Docker 回归。
2026-08-01 完成 4D-B2.6 的代码与本机证据层：新增 `v2_integration.py`、`v2_ablation.py`、`run_4d_b26_integration.py`、`run_4d_b26_ablation.py` 和 `run_4d_b26_docker_regression.py`；实现 PostgreSQL shadow transaction、真实 RAG source allow-list、Provider sandbox fault trace、UnifiedHealthGraph v2 执行器、A/B/C/D preview 和 Docker 全链路回归。Docker 19/19 通过，第一条真实 v2 integration sample 九类 grader 全部通过；报告仍为 `preview`，不能作为最终简历指标。B2.6 的剩余门槛是人工审核 v2 数据、为全部 WorldState 提供本地 identity/source map、运行完整 integration/A-B-C-D 报告并冻结正式 manifest。

2026-08-01 进入 4D-B3：新增 `real_llm_benchmark.py`、`run_4d_b3_real_llm.py` 和 badcase review queue；实现显式 `--live` 开关、无 Key blocked 报告、真实 provider effective/fallback 统计、完整 usage、价格换算、模型 p95、workflow p95 和人工审核队列。已在 Docker PostgreSQL + 本机 venv 上用 `deepseek-v4-flash`、thinking disabled 跑通 1 条 development preview：primary 生效、无 fallback、590/423/1013 token、按配置价格成本 `$0.001436`、workflow `4370 ms`、model `3572 ms`。该结果仍是 `n=1 preview`，人工回答质量和正式简历指标保持未冻结，下一步是人工复核队列并扩展固定样本。

2026-08-01 继续 4D-B3：为真实模型审核队列增加 `ConfirmationDraftSnapshot`，保留 draft id、任务/成员、动作、版本、确认要求、摘要和药品/时间/文案安全预览，以及 `external_action_status=not_submitted`，不写入完整医疗 payload；修复 shadow integration 中内部 `user_id` 不应进入评测快照的契约边界。人工审核发现原队列只有元数据、无法查看草稿内容，本次补齐可见预览；重新运行 1 条 development preview 后仍保持 `pending_review`，未自动判定人工回答质量。

2026-08-01 继续 4D-B3：在保留已审核的 1-case 目录后，对当前 identity map 覆盖的 `world-v2-0001` 四种表达变体运行 4-case live preview。四条均自动评测通过，真实 provider 生效率 `1.0`、fallback `0.0`、平均总 token `1018`、workflow p95 `5038 ms`、model p95 `4300 ms`；结果仍标记 `preview`，四条 badcase 仍需人工复核，不能写成最终回答质量或泛化指标。
2026-08-01 继续 4D-B3：为 `world-v2-0001` 父亲提醒和 `world-v2-0002` 母亲购药补充本机真实成员/来源映射，运行 8 条 `deepseek-v4-flash` development live preview。8 条自动九层契约全部通过，真实 provider 生效率 `1.0`、fallback `0.0`、usage 可用率 `1.0`、平均总 token `1032.5`、workflow p95 `5239 ms`、model p95 `4452 ms`；结果仍为 `preview`，8 条仍需人工复核，不能写成最终回答质量或全量指标。当前唯一下一项仍为人工复核 badcase、补齐其余 WorldState 映射并生成正式报告。
2026-08-01 完成 4D-B3：新增人工审核 finalizer，兼容人工填写的 `pass/fail`，校验 report id、query 顺序和不可变证据，拒绝 pending、缺少失败备注或被篡改的回答，并冻结 canonical review queue hash 与四个产物文件 hash。8 条 development 样本人工复核结果为 8/8 通过；final report 状态为 `completed`，平均总 token `1032.5`、平均成本 `$0.00146525`、workflow/model p95 为 `5239/4452 ms`。该报告只覆盖两个成员和提醒/购药场景；4D-B 整体仍需完成 300/1200 全量映射与三 split 正式报告。

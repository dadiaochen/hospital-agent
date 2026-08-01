# 技术设计

## 1. 设计目标

系统把大模型放在受契约约束的业务流程中，而不是直接连接医疗问答。每个用户可见结果都要具备明确身份作用域、业务事实、RAG 来源、安全决策、确认状态、运行轨迹和事后评测。

本文同时标注当前实现和 4D-B 收口目标；阶段状态只看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

## 2. 总体分层

```text
Frontend / API
  -> Service / Transaction Boundary
  -> AgentRuntimeService
       -> Trusted Scope + Request Safety Guard
       -> Complexity Router
            -> Simple Domain Agent
            -> TaskPlanner + bounded Supervisor + Domain Agents
       -> ContextManager
       -> Tool Registry
            -> Repository / Provider / RAG
       -> Action Policy Guard + Confirmation State Machine
       -> Model Gateway + Final Output SafetyAgent
       -> Frozen Artifacts / RunSummary / Context Reset
       -> Deterministic Evaluator

State and data:
  PostgreSQL = authoritative business data + task checkpoint + confirmation + preferences
  Redis      = TTL task cache and multi-instance coordination; rebuild from PostgreSQL
  pgvector   = versioned medical knowledge retrieval; separate from personal memory
```

## 3. 后端模块职责

| 层 | 职责 | 禁止事项 |
| --- | --- | --- |
| `api` | HTTP 入参、出参、依赖注入和统一错误映射 | 查询数据库或作 Agent 决策 |
| `schemas` | API Pydantic DTO | 业务执行 |
| `services` | 事务、幂等、状态机和应用编排 | 模型自由路由 |
| `models` | SQLAlchemy 持久化结构 | Agent 逻辑 |
| `tools` | ToolSpec、执行上下文、权限、schema、重试和审计 | 绕过可信 user/member 作用域 |
| `providers` | mock/sandbox/real 外部适配 | 伪造真实外部成功 |
| `agent` | Context、Router、Planner、Supervisor、领域 Agent、Trace 和 Harness | 直接访问数据库或外部 API |
| `rag` | keyword/vector/RRF、版本和来源 | 保存个人健康记忆 |
| `safety` | Request、Action、Output 三层治理 | 代替 Evaluator 或业务执行 |
| `core` | 配置、数据库、缓存、日志和异常基础设施 | 业务决策 |

## 4. 请求数据流

### 4.1 首次 run

```text
HTTP request
  -> authenticate/resolve demo user
  -> authorize member/resource
  -> Request Safety Guard
  -> Complexity Router
  -> simple Domain Agent OR TaskPlanner + bounded Supervisor
  -> Tool Registry / Provider / RAG
  -> Action Policy Guard
  -> optional local DRAFT
  -> Model Gateway candidate
  -> Final Output SafetyAgent
  -> freeze FinalAnswer + SourceRefs + RunTrace
  -> RunSummary + Context Reset
  -> Deterministic Evaluator
  -> persist PostgreSQL checkpoint
  -> refresh Redis TTL cache
```

### 4.2 确认 run

```text
confirmation request
  -> new continuation run under same task_id
  -> Redis lookup; miss/failure -> PostgreSQL checkpoint
  -> reauthorize user/member/draft/version
  -> re-read mutable business facts
  -> Action Policy Guard
  -> idempotent local state transition
  -> candidate acknowledgement + Final Output Safety
  -> freeze/reset/evaluate/persist
```

不恢复 raw conversation、scratchpad、未确认推断或 provider 原文。

## 5. 契约优先

Context、路由、计划、Supervisor、Agent result、Tool、Trace 和 Evaluation 都先定义 Pydantic 契约并使用 `extra="forbid"`。目标新增契约包括：

- `ComplexityRoute`
- `TaskPlan` / `TaskStep`
- `SupervisorDecision`
- `AgentTaskResult`
- `SafetyDecision`
- `SupervisorContextView`

模型输出只是候选值；通过 schema 不代表允许执行，还要经过角色、工具、依赖、成员和 Safety/Policy 校验。

## 6. Agent 编排技术选型

选择 LangGraph 是因为业务需要显式状态、条件边、中断后续跑和可测试终止条件，不是为了展示框架名称。

- 简单请求走固定直达边。
- 复杂请求由一次性 Planner 产生有最大步骤数和最大并行数的冻结 DAG；当前最多 3 步的串行计划作为迁移基线。
- Supervisor 选择 ready steps，对无依赖、只读且无副作用的步骤执行受控 fan-out/fan-in，不自由重规划。
- Domain Agent 返回统一结果，不彼此调用。
- Safety/Evaluator 由固定治理边强制执行。
- 无 Key 使用 deterministic policy；真实模型只做固定候选的结构化决策。

最终 UnifiedHealthGraph 支持 Agent 级有界 DAG 并行，但不采用群聊式自由协作或无限循环。并行只用于依赖已满足、只读且无副作用的领域步骤；确认、写操作、Checkpoint、Safety、FinalAnswer 冻结和 Evaluator 保持串行。并行结果按 `step_id` 使用确定性 reducer 合并，领域 Agent 内部仍可对独立 I/O 使用受控异步并发。

## 7. Tool 与 Provider

Tool Registry 是 Agent 访问业务能力的唯一入口。服务端注入 run、user、member、role、allowed tools、provider mode 和确认状态；模型只产生业务参数。

统一错误：validation、permission、not-found、timeout、rate-limit、provider-unavailable、business-conflict、schema 和 internal error。权限、参数、业务冲突和 Safety 错误不重试；timeout、429 和明确可恢复 5xx 有限重试并记录 attempt，耗尽后结构化降级。

任务九已将该目标落地为两层确定性可靠性边界：`ToolRegistry` 负责工具 schema、角色/allowed-tools、确认、只读重试上限和 `ToolAttemptTrace`；`ProviderRegistry` 负责 Provider 身份/模式/operation 一致性、`ProviderAttemptTrace`、错误归一化和耗尽降级。旧错误名通过 `classify_error()` 映射到稳定 `error_category`，避免为了兼容旧调用而丢失统一评测口径。

`MedicalDocumentParserProvider`、`PharmacyProvider` 和 `HospitalOrConsultationProvider` 使用 operation-specific Pydantic schema。网络 transport 通过构造参数注入并接收 `timeout_ms`，因此测试可完全离线；未配置 sandbox/real 不尝试猜测数据。失败 Provider 响应被契约禁止携带 data 或 SourceRef，订单、预约和问诊提交字段只能为 false。

当前七个 mock adapter 保持兼容，最终只做深：

1. Medical Document Parser。
2. Pharmacy。
3. Hospital or Online Consultation unified facade。

Geo、Notification、Medical Vision 等不再扩展为空接口，不作为最终交付重点。

## 8. 安全和确认

Request Safety Guard 优先阻断高风险输入；Action Policy Guard 保护草稿、确认和写工具；Final Output SafetyAgent 检查候选答案。Evaluator 仅在冻结后评测，不能补救已经发给用户的危险回答。

目标确认语义是“自动生成本地 DRAFT，只确认执行”。`DRAFT` 本身有审计写入，但没有外部业务副作用。确认后当前最多执行本地状态迁移，外部状态始终明确为 `not_submitted`。

PostgreSQL 使用唯一幂等键、请求指纹、行锁或条件更新保证并发一致性。Redis 不参与最终状态真相判断。

任务七的确定性实现位于 `backend/app/agent/safety_confirmation.py`。`ThreeLayerSafetyGuard` 只返回带 stage 的 `SafetyDecision`，`ConfirmationStateMachine` 只接收结构化 scope/current state 并返回允许、阻断或 idempotent replay；它们不保存状态、不访问数据库。新业务工作流把首轮草稿投影到 `confirmation_draft`，确认续跑由 `BusinessTaskService` 锁定 task 行后重新校验 scope，再调用状态机推进本地 `DRAFT -> CONFIRMED -> EXECUTED`。旧 Agent Runtime 的兼容接口仍保持原有 HTTP 语义，避免在任务七混入 API 大迁移。

## 9. 分层状态和上下文

- Run Working State：单次运行，run 后 reset。
- PostgreSQL Task Checkpoint：权威任务进度、确认、冻结产物和用户确认偏好。
- Redis TTL Cache：短期 checkpoint 和多实例协调，故障回源 PostgreSQL。
- Knowledge RAG：独立 PostgreSQL + pgvector namespace。

ContextManager 继续提供按角色最小视图。Supervisor 只看计划、步骤状态、角色能力、错误摘要和 result refs；领域 Agent 只看本领域状态、允许工具和对应 SourceRefs。

系统不保存长期完整聊天或个人健康向量记忆。处方、报告、药箱、过敏和库存每次通过受成员约束的 Tool/Provider 重新读取。

## 10. RAG 技术选型

RAG 采用 PostgreSQL 权威正文、pgvector 向量检索、FastEmbed、Keyword Retriever、RRF 和关键词降级：

- keyword 负责药名、指标名、标准编号和安全词精确匹配。
- vector 负责口语和语义相似召回。
- RRF 按 rank 融合，避免比较不同量纲 raw score。
- 所有结果回到权威知识表校验正文、版本和审核状态。
- provider、模型、索引或版本异常时回退关键词，并记录 fallback reason。

HNSW 是可扩展索引路径。当前知识量较小时不宣称它显著提高性能；真实效果由 Recall@K、引用正确率和 wall-clock 基准决定。

## 11. Model Gateway

provider、base URL、API Key、模型和 timeout 来自服务端环境。Gateway 负责 attempt trace、JSON 解析、目标 schema、输出安全检查和 fallback。

4B 目标允许 Router/Planner/Domain Agent/Supervisor 使用各自固定 schema，但它们不能自由生成工具和身份字段。FinalAnswer 仍经过单独输出 schema 和 Final Output SafetyAgent。规则安全、Tool 权限和数据库状态机不能被模型输出覆盖。

任务五已落地 `ComplexityRoute`、`TaskPlan`、`AgentTaskResult`、`SupervisorDecision` 和三阶段 `SafetyDecision` 契约，并提供不依赖外部系统的 `DeterministicComplexityRouter`。任务六已经把这些契约接入三个 deterministic 领域 Agent、一次性 `DeterministicTaskPlanner` 和串行 `DeterministicBoundedSupervisor`；这层仍不访问数据库、Provider、Tool Registry 或 LLM。

任务六的聚合结果是 `OrchestrationRunResult`：简单请求保留一个直达结果，复杂请求保留一次性计划、按顺序的 Agent 结果、重试/降级/终止决策和最终终止原因。它是任务七治理接线、任务八 checkpoint 和任务十一 Harness 的输入边界，不等于已经完成真实医疗数据查询。

## 12. 可观测性

优先补全现有 RunTrace/Observation，而不是引入 OpenTelemetry/Jaeger：

- request/task/run/thread/user/member
- workflow/prompt/model/tool/provider version
- node、decision、step、handoff、status
- latency、retry、error、fallback/degraded reason
- source refs、input/output token 和估算成本

不记录 API Key、Cookie、完整 Prompt、原始病历、raw conversation 或未脱敏 provider 原文。MCP Server 和分布式追踪平台属于非目标。

任务十已将该设计落为 `ObservationTrace`：每个事件必须携带 request/task/run/member、event type、node 和 sequence；工具、Provider、RAG、模型事件按需携带时延、重试、fallback、source ID、模型名和 token count。契约不提供任意 metadata 字段，`extra=forbid` 且冻结；request/input payload、Tool 输入输出、Provider 请求响应、模型消息和 FinalAnswer 正文只记录被移除的字段名，不记录原值。模型 Provider 未返回 usage 时明确保存 `token_usage_available=false`，不估造 token 指标。

## 13. 评测

Deterministic Evaluator 是正式核心。任务十一已经使用 32 条冻结业务 `RunTrace` fixture，覆盖单领域、跨领域、缺失信息、高风险、RAG、Provider/Tool 异常、成员攻击和确认/幂等，共生成 96 份 A/B/C 结果。

消融实验比较 Single Agent、固定领域子图和按需 Planner + bounded Supervisor。`FairnessConfig` 强制三组共享模型身份、工具目录、RAG、Safety、确认策略和 token 上限；业务 `RunTrace` 继续由既有 Deterministic Evaluator 只读评估，编排层另行计算角色顺序、工具参数 exact-match、handoff 和重复调用。LLM Judge 不进入运行链或验收门槛。

任务十一的 P50/P95 使用冻结 fixture latency，不能当作真实服务 wall-clock。deterministic provider 未返回 usage，因此 `token_usage_available=false`，token 和 billed cost 为 `N/A`，运行器禁止合成这些指标。任务十二已在本机 Docker PostgreSQL/Redis/FastAPI/Next.js 栈补充真实运行验收；baseline 19/19、Redis 故障回源 18/18，详见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。

4D-B2.5 已增加 v2 本地 preview runner：`WorldStateMaterializer` 为每条 Query 创建隔离的内存 DB/Provider/RAG projection，`V2DeterministicGraders` 分别评分 Route、Plan、Tool、Claim、RAG、Safety、Context、Reliability 和 Database State，`V2EvalRunner` 输出稳定 report id、JSON/Markdown 和 failure taxonomy。该层不替代 Docker PostgreSQL/pgvector、Checkpoint/Redis 恢复、真实 HTTP 或真实 LLM 评测；v2 数据仍是 `pending_review`，preview 指标继续不能写入简历。

### 13.1 4D-B 最终评测数据流

最终评测使用 UnifiedHealthGraph 的有界 DAG，并通过 WorldState v2 物化同一份测试事实：

```text
WorldState
  -> PostgreSQL / Provider / RAG materialize
  -> real HTTP runtime
  -> Route / Plan / Tool / Source / FinalAnswer / RunTrace
  -> final database state
  -> deterministic graders
  -> metrics + badcases + environment manifest
```

B2.5 的本地 preview 使用同一条数据流，但 executor 只做 Gold projection：

```text
WorldState / Query
  -> in-memory isolated projection
  -> SyntheticProjectionExecutor
  -> frozen RunTrace + V2RunArtifacts
  -> nine deterministic graders
  -> preview JSON/Markdown
```

它用于验证评测契约、成员隔离、清理和聚合逻辑，不代表真实业务图已在 PostgreSQL、Provider 和 RAG 上执行。

现有 260 条 4D-A gold 是回答、RAG、安全、上下文和 Provider 五组专项数据，继续用于快速回归；它们不是 260 个端到端 WorldState。4D-B 最终建立 300 个 WorldState，每个生成 4 条表达，共 1200 条 v2 Query，并按 base world 拆分 development、validation 和 holdout。评测模式保留 `all_history` 合成数据基线，生产默认使用 `dependency_only` Role-specific Context View。详细数量、字段、指标公式和执行门槛见 [Agent 统一架构、评测数据与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。

### 13.2 FinalClaim

4D-B2.3 已在同一次结构化输出中加入 `FinalClaim` 和 `AnswerEnvelope`。`FinalAnswer` 仍保留用户可见正文，但每条可评测事实同时保存结构化 Claim：

```text
claim_id
subject_id  # 当前任务的 member scope
fact_key
value
claim_type
source_ids
```

事实 Claim 必须保留 Tool、Provider、数据库或 RAG 来源；`subject_id` 必须与任务 `member_id` 一致，`source_ids` 必须来自同一 RunTrace 的上下文来源集合。Evaluator 读取冻结 Claim，但不能修改正文、生成医疗建议或写业务状态。FinalClaim 不进入个人长期记忆，也不能由另一个 LLM 在评测阶段从正文反向生成。

## 14. 当前实现与目标差异

| 当前实现 | 收口目标 | 对应任务 |
| --- | --- | --- |
| UnifiedHealthGraph 已接入患者端业务入口，内部业务执行由 ProductWorkflow 适配器负责；Router/三领域 Agent/bounded DAG Supervisor 已独立评测 | 已增加 FinalClaim、AnswerEnvelope、Trace v2 和正文/Claim 一致性校验 | 4D-B2.3 DONE |
| 任务六领域编排默认 deterministic | 领域决策可选 model-assisted，始终受约束 | 后续 Provider/模型增强 |
| 新业务链路已自动生成本地 DRAFT，确认后执行本地状态迁移；旧 Runtime 保留兼容 | 任务八已落地 PG 权威 checkpoint + Redis TTL cache/协调 | 8 |
| `TaskCheckpointService` 写入不可变 checkpoint，`TaskCheckpointCache` 校验作用域和版本；确认 run 使用最小投影 | 后续任务九的 Tool/Provider 可靠性和真实外部联调 | 8–9 |
| 三个重点 Provider 已具备强 schema、有限重试、attempt/source/degraded 测试；其他 mock 兼容保留 | 任务十已补 RAG、隔离和 Observation；外部 Provider 仍待真实联调 | 9–12 |
| RRF、过期向量拒绝、攻击式隔离、白名单 Observation 和 32 条 A/B/C Harness 已实现 | 本机 Docker PostgreSQL/Redis 与 wall-clock 已验收，结果不等于生产 SLO | 12 |
| 16 条历史契约 + 9 条 runtime 场景 + 32 条任务十一业务 fixture | 三条业务 API、RAG 索引、Redis 回源和并发状态机已完成真实 smoke | 12 |
| 4D-B 已观测本地 Supervisor、关键词 RAG、ContextManager 和 Provider fault；B2.1/B2.2 已接入 UnifiedHealthGraph、bounded DAG 和评测 `all_history`；B2.3 已接入 Claim/Trace v2；B2.4 已生成可重复 v2 数据；B2.5 已完成内存物化、九层 grader 和 preview runner | 人工审核并接入 300 个 WorldState/1200 条 Query 的 PostgreSQL/Provider/RAG 物化，再运行真实 UnifiedHealthGraph、Docker 报告和可选真实 LLM 报告 | 4D-B2.6 至 B3 |

## 14.1 4D-B2.6 真实集成评测

4D-B2.6 在不新增 Alembic migration 的前提下，把 v2 benchmark 接到真实本地运行边界：

- `PostgresV2Materializer` 使用每 case 的 PostgreSQL transaction、temporary projection table 和 shadow knowledge rows；结束后 rollback，不能污染 demo 业务数据。
- `ScopedPostgresRetriever` 复用当前 PostgreSQL hybrid retriever，再按 case source allow-list 过滤，防止 seed knowledge 或其他 case 的 source 混入。
- `ScopedProviderSandbox` 复用 Provider contract，并在当前 case 内记录 timeout/no-source attempt trace；它不是外部医院、药房或通知系统。
- `UnifiedHealthGraphIntegrationExecutor` 要求显式 benchmark user/member/source identity map，缺少映射时 fail closed，不把不相关 demo 数据当成评测结果。
- `V2AblationRunner` 固定 A/B/C/D 只改变 routing、execution、context 开关；数据、Provider、RAG、安全、确认和 token limit 必须保持不变。

Docker 验收实际通过了 `19/19` 个本地检查；第一条真实 v2 integration sample 通过九类 deterministic grader，但 v2 数据仍是 `pending_review`，所以报告状态保持 `preview`。完整命令和剩余门槛见 [4D-B2.6 集成状态](4D_B2.6_INTEGRATION_STATUS.md)。

## 15. 数据库迁移链

当前唯一迁移链：

```text
0001_initial_schema
  -> 0002_add_agent_harness_trace_fields
  -> 0003_lightweight_vector_rag
  -> 0004_business_task_runtime
  -> 0005_knowledge_metadata
  -> 0006_vector_search_index
  -> 0007_task_checkpoint_state
```

`0007_task_checkpoint_state` 是任务八唯一新增 revision，负责 checkpoint、确认记录、已确认偏好、业务任务版本和 continuation parent run。任何后续 schema 变化都必须从该 head 继续串联，不得创建平行 revision 或重复列。

## 16. 任务八状态实现

`BusinessTaskService` 在首次 run 和 continuation run 结束时调用 `TaskCheckpointService`，在同一事务中保存 PostgreSQL checkpoint 与确认状态审计，再尽力发布 Redis TTL 投影。Redis 发布失败不回滚已提交的 PostgreSQL 结果。

恢复顺序为：

```text
current task version -> Redis scoped/versioned projection
  -> miss/expired/malformed/unavailable
  -> PostgreSQL TaskCheckpoint
  -> minimal continuation state
  -> re-read mutable business facts
```

Redis 投影不含 raw conversation、scratchpad、candidate inference、完整 provider response 或 API Key。`checkpoint_version` 和 `confirmation_version` 由 API 客户端回传时执行乐观校验；过期版本返回结构化冲突，不创建 continuation run。确认完成后，`ConfirmedPreferenceService` 还会校验 `EXECUTED` 记录、成员、source version 和显式人工确认，才写入可撤销的偏好版本。

## 17. 4C-4 交付编排

最终交付使用 `scripts/closeout_4c.ps1` 作为操作员入口，而不是新增一个业务运行时。它按顺序调用已有的 Docker Compose、Runtime Demo、deterministic Harness、A/B/C 消融和 Playwright E2E：

```text
Docker build/up -> migration/seed -> fixed Runtime Demo
  -> HTTP health -> offline Harness/A/B/C
  -> real browser E2E -> redacted closeout report
```

Harness fixture 在宿主机离线执行，避免把测试数据打进 backend 镜像；浏览器 E2E 通过公开前端和 API 访问真实 Docker 服务。脚本只写 `var/closeout/` 运行报告，不持久化完整聊天、医疗正文、Prompt、Token、成员 ID、run ID 或密钥。任一步骤失败都返回非零退出码，因此“演示能打开”不能替代完整收口。

## 18. 4D-B3 可选真实模型评测

4D-B3 不改变业务图的治理边界。真实模型仍只通过 `ModelGateway` 进入最终答案草稿节点；`run_4d_b3_real_llm.py` 复用 PostgreSQL shadow transaction、Provider/RAG 隔离和九层 deterministic grader，并额外从脱敏 `model` Observation 读取 provider usage、fallback 和模型耗时。

真实 token 只能来自 provider 返回的完整 `input/output/total` usage。成本计算需要本机 `.env` 提供每百万输入/输出 token 价格；缺少 usage 或价格时保持 `N/A`。没有 `--live`、没有 Key 或 provider 不是 `openai_compatible` 时，runner 只生成 blocked 报告，不访问网络。B3 的 deterministic contract pass rate 不是自然语言答案质量；答案质量必须经过人工复核。审核队列额外保存只读 `ConfirmationDraftSnapshot`。审核完成后，finalizer 校验队列未修改 FinalAnswer、成员、来源和期望字段，规范化 pass/fail，计算人工通过率并冻结 canonical queue hash 与输出文件 manifest。当前 8 条 development 固定样本已经完成该流程。

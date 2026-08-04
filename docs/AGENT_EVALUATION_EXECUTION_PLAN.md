# Agent 统一架构、评测数据与简历指标最终执行方案

> 状态：`ACTIVE`
>
> 适用阶段：4D-B
>
> 权威关系：阶段状态和执行顺序以 [开发总路线图](DEVELOPMENT_ROADMAP.md) 为准；本文负责定义最终目标架构、v2 评测数据、指标计算、实现任务和简历口径。

## 1. 最终目标

当前项目已经具备业务 API、固定领域 LangGraph、独立 Supervisor 编排内核、Tool Registry、RAG、三层 Agent 安全、上下文管理、Checkpoint 和 deterministic Evaluator。4D-B 不再只补局部指标，而是把这些能力统一成一条可运行、可评测的主链。

最终系统采用：

1. **UnifiedHealthGraph**：患者端业务只保留一条正式 Agent 运行图。
2. **Router + 一次性 Planner + bounded Supervisor**：简单任务直达，复杂任务生成有界 DAG。
3. **受控 DAG 并行**：只并行无依赖、只读、无副作用的领域 Agent 或 Tool 查询。
4. **三层 Agent 安全与确认状态机**：请求、动作和最终输出均不能被 Supervisor 绕过。
5. **分层上下文**：生产使用角色最小上下文，评测保留 `all_history` 基线用于消融。
6. **结构化 FinalClaim**：事实、成员和来源可以直接评分，不从答案正文反向猜测。
7. **300 个 WorldState、1200 条 v2 Query**：作为最终离线评测集。
8. **确定性 Grader 为主**：LLM Judge 只做离线辅助，不判断安全、数据库和来源事实。
9. **真实指标回填**：所有简历数字必须来自冻结数据、RunTrace 和版本化报告。

本项目仍然不是 AI 医生，不实现诊断、自动开方、改药或真实医院/药店写操作。

## 2. 当前代码基线

### 2.1 已实现

| 能力 | 当前代码状态 |
| --- | --- |
| 三条患者端业务链 | `BusinessTaskService` 已通过 `UnifiedHealthGraph` 接入；内部业务执行由 `FamilyHealthProductWorkflow` 适配器承载 |
| Complexity Router | `DeterministicComplexityRouter` 已实现 |
| Planner | `DeterministicTaskPlanner` 已实现，当前最多 3 步 |
| Supervisor | `DeterministicBoundedSupervisor` 已实现，当前串行执行 |
| 领域 Agent | 分诊、用药、报告三个 Agent 已实现 |
| Agent 安全 | 请求、动作、最终输出三层门禁已实现 |
| 确认状态机 | 本地 DRAFT、确认、执行、幂等和版本校验已实现 |
| Context | ContextEnvelope、角色视图、compact、reset 已实现 |
| 记忆和恢复 | PostgreSQL checkpoint、Redis TTL cache 和回源已实现 |
| Tool/Provider | Registry、权限、schema、有限重试、降级和 trace 已实现 |
| RAG | keyword、pgvector、RRF、版本拒绝和关键词降级已实现 |
| Model Gateway | deterministic/真实模型双模式和结构化校验已实现 |
| Evaluator | RunTrace、deterministic 规则、Harness 和报告已实现 |

### 2.2 尚未实现

| 最终目标 | 当前缺口 |
| --- | --- |
| UnifiedHealthGraph | 4D-B2.1 已完成统一入口；4D-B2.2 已接入有界 DAG 编排内核，业务 ProductWorkflow 适配器仍保持副作用串行 |
| DAG 并行 | Supervisor 已对依赖已满足、只读且无写工具的步骤执行受控 fan-out/fan-in |
| 全历史评测基线 | `EvalRuntimeOptions` 和 ContextManager 已提供仅评测可用的结构化 `all_history` 模式 |
| FinalClaim | 4D-B2.3 已实现 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`；v2 Gold Claim 已随 WorldState 生成并增加成员来源范围校验 |
| v2 WorldState | 4D-B2.4 已生成 300 个可重复 WorldState；用户已完成审核并全部标记 `pass`，B2.6 已生成 300-case 本机 identity/source map |
| 1200 条 Query | 4D-B2.4 已生成每个 WorldState 的 4 种表达；用户已完成 1200 条审核，B2.6 deterministic Docker smoke 已通过 2 条，三 split integration 仍未完成 |
| 分层 Grader v2 | B2.5 已实现 Route/Plan/Tool/Claim/RAG/Safety/Context/Reliability/Database State 九类确定性 grader；真实图产物仍未接入 |
| 本地 preview Runner | B2.5 已支持 split、max_cases、repeat、pending-review gate、稳定 report id 和 JSON/Markdown；仅使用内存 projection |
| 真实统一 Runner | Docker pgvector、HTTP、Checkpoint、Provider 和模型未进入同一报告；属于 B2.6/B3 集成 |

这些项目是待实现目标，不是设计冲突。

## 3. 只修正真正的矛盾

外部方案中大部分内容进入最终目标，仅对以下部分做项目化修正。

### 3.1 DAG 并行与医疗状态一致性

DAG 并行可以实现，但不能让所有节点自由并发。

允许并行：

- 不同领域之间无依赖的只读查询。
- 同一领域内相互独立的数据库、Provider 和 RAG 查询。
- 不创建草稿、不修改 checkpoint、不改变确认状态的节点。

必须串行：

- Request Safety、Action Policy、Final Output Safety。
- Planner 生成和 Supervisor 决策提交。
- 草稿创建、确认、执行和数据库写入。
- Checkpoint 版本推进。
- FinalAnswer 冻结、Context Reset 和 Evaluator。

并行节点必须满足：

```text
read_only = true
dependencies completed
member_id 相同
无共享可变业务状态
有独立 timeout 和 attempt trace
有确定性 reducer
```

### 3.2 `all_history` 的适用范围

`all_history` 是评测基线，不是生产默认值。

- 只在 `APP_ENV=test` 或专用 eval runner 中启用。
- 只使用合成数据。
- 仍然按 `user_id + member_id` 隔离，不能混入其他成员历史。
- 不包含 API Key、原始病历文件、Provider 原文或未脱敏数据。
- 生产模式固定使用 `dependency_only` 或 Role-specific Context View。

这样可以比较上下文裁剪带来的 token 和延迟变化，同时不破坏正式系统的隐私边界。

### 3.3 现有 260 条数据

当前五组数据继续保留为 v1 快速回归：

```text
answer_quality：60
rag_gold：30
safety_gold：100
memory_context：40
provider_faults：30
总计：260
```

它们不能直接改名为 260 个 WorldState。v2 需要单独建立完整业务世界，并将同一份事实物化到数据库、Provider 和 RAG。

### 3.4 现有 A/B/C 消融

现有三种策略继续保留：

```text
Single Agent
固定领域路由
bounded Supervisor
```

最终再增加统一图内部的运行开关，形成 Router、并发和上下文三组受控消融。旧结果不删除，新结果不与旧 fixture latency 混算。

## 4. UnifiedHealthGraph

### 4.1 正式运行图

```text
START
  -> Trusted Scope
  -> Request Safety
  -> Complexity Router
       -> simple: one Domain Agent
       -> complex: one-shot Planner -> bounded Supervisor
            -> ready DAG steps
            -> parallel read-only branches
            -> deterministic merge
            -> next ready steps
  -> Action Policy
  -> optional local DRAFT
  -> Model Gateway
  -> Final Output Safety
  -> freeze FinalAnswer + FinalClaim + RunTrace
  -> RunSummary + Context Reset
  -> read-only Evaluator
  -> persist Checkpoint
  -> END
```

### 4.2 Planner 输出

Planner 只运行一次，输出冻结 DAG：

```python
class TaskPlan(ContractModel):
    task_id: str
    member_id: str
    steps: tuple[TaskStep, ...]
    dependency_edges: tuple[DependencyEdge, ...]
    max_steps: int
    max_parallelism: int
```

每个步骤至少包含：

```text
step_id
agent_role
objective_code
dependencies
read_only
allowed_tools
required_source_types
```

Planner 不负责逐步调度，不修改用户目标，不生成未注册 Agent 或 Tool。

### 4.3 Supervisor 职责

Supervisor 每轮只做以下事情：

1. 找出依赖已满足的 ready steps。
2. 校验角色和 Tool 白名单。
3. 将无依赖、只读步骤放入一个受控并行批次。
4. 等待批次完成并使用确定性 reducer 合并结果。
5. 对失败步骤执行有限重试、降级或终止。
6. 达到步骤上限、重复决策或无 ready step 时终止。

Supervisor 不能：

- 重写 Planner 的目标。
- 新增计划外步骤。
- 直接调用业务 Tool。
- 调度 SafetyAgent 或 EvaluatorAgent。
- 并行执行写操作。
- 进行无限循环或复杂自动重规划。

### 4.4 并发控制

首版本建议：

```text
max_steps = 6
max_parallelism = 3
max_agent_attempts = 2
```

这三个值必须来自服务端配置和 Pydantic 约束，不能由用户输入或模型自由修改。

## 5. 上下文消融

新增仅供评测使用的配置：

```python
class EvalRuntimeOptions(ContractModel):
    routing_mode: Literal["auto", "forced_supervisor"] = "auto"
    execution_mode: Literal["serial", "parallel"] = "parallel"
    context_mode: Literal["all_history", "dependency_only"] = "dependency_only"
    planner_mode: Literal["deterministic", "model"] = "deterministic"
```

四组核心实验：

| 模式 | 路由 | 执行 | 上下文 | 证明什么 |
| --- | --- | --- | --- | --- |
| A | forced Supervisor | serial | all_history | 人为复杂基线 |
| B | auto | serial | all_history | Router 让简单任务直达的价值 |
| C | auto | parallel | all_history | DAG 并行的延迟价值 |
| D | auto | parallel | dependency_only | 最终模式的上下文价值 |

比较：

```text
A -> B：简单任务绕过 Planner/Supervisor 后的延迟和 token
B -> C：独立只读 DAG 并行后的延迟
C -> D：角色最小上下文后的 token、重复信息和质量
```

同时保留旧 Single Agent、固定路由、Supervisor 三策略实验，用于回答“为什么需要多 Agent”。

## 6. FinalClaim

### 6.1 契约

```python
class FinalClaim(ContractModel):
    claim_id: str
    fact_key: str
    subject_id: str
    value: object
    source_ids: tuple[str, ...]
    claim_type: Literal[
        "operational_fact",
        "knowledge_fact",
        "safety_notice",
        "uncertainty_notice",
    ]
```

`AnswerEnvelope` 同时包含：

```python
class AnswerEnvelope(ContractModel):
    display_text: str
    claims: tuple[FinalClaim, ...]
    waiting_for_user_confirmation: bool
    action_status: str
```

### 6.2 规则

1. `operational_fact` 必须有 DB、Tool 或 Provider source。
2. `knowledge_fact` 必须有有效 RAG source。
3. `subject_id` 必须与当前 `member_id` 一致。
4. 安全和不确定性说明不能伪装成已确认医疗事实。
5. FinalClaim 和 `display_text` 必须来自同一次结构化输出。
6. Evaluator 不调用 LLM 从正文重新提取 Claim。
7. FinalClaim 进入冻结 Trace，不写入个人长期记忆。

## 7. v2 数据集

### 7.1 最终规模

```text
300 个独立 WorldState
每个 WorldState 4 条用户表达
总计 1200 条 Eval Query
```

WorldState 分布：

| 类别 | 数量 |
| --- | ---: |
| Triage / 预问诊 | 70 |
| Medication / 慢病与用药 | 85 |
| Report / 报告整理 | 55 |
| 跨领域复杂任务 | 50 |
| 故障、确认、隔离、幂等 | 40 |
| 合计 | 300 |

标签可以重叠：

```text
safety
rag
multi_member
confirmation
provider_fault
checkpoint
no_answer
stale_source
prompt_injection
parallelizable
```

### 7.2 数据拆分

按 `base_case_id` 拆分：

```text
development：180 个 WorldState，720 条表达
validation：60 个 WorldState，240 条表达
holdout：60 个 WorldState，240 条表达
```

同一 WorldState 的四条表达必须属于同一个 split。

### 7.3 WorldState

```python
class EvalWorldState(ContractModel):
    base_case_id: str
    dataset_split: Literal["development", "validation", "holdout"]
    category: str
    tags: tuple[str, ...]
    frozen_now: datetime
    seed: int

    user: EvalUserState
    members: tuple[EvalMemberState, ...]
    prescriptions: tuple[EvalPrescriptionState, ...]
    medicine_box: tuple[EvalMedicineBoxState, ...]
    health_records: tuple[EvalHealthRecordState, ...]

    provider_state: EvalProviderState
    knowledge_state: EvalKnowledgeState
    fault_injection: EvalFaultInjection
    gold: EvalGoldExpectation
```

Gold 包含：

```text
expected_route
expected_agent_roles
expected_steps
expected_dependency_edges
expected_tool_calls
required_claims
forbidden_claims
supporting_source_ids
expected_safety_flags
expected_blocked
expected_confirmation_required
expected_final_status
expected_database_changes
```

### 7.4 数据生成

4D-B2.4 已由 `backend/app/agent/v2_benchmark_generator.py` 程序化生成 300 个结构化 WorldState 和 1200 条 Query，必须继续遵守：

- 使用固定 seed。
- 冻结 `frozen_now`。
- 从业务规则和 seed 数据建立 Gold。
- AI 不负责定义正确医疗事实。
- AI 只生成四种表达变体。
- 所有安全、来源和 holdout 标签经过人工审核。
- manifest 保存数量、版本、固定 seed 和 SHA-256；生成数据已由用户完成运行前 Gold 审核并全部标记 `pass`，但真实运行报告仍需通过 C-E 才能成为最终指标。

生成命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.v2_benchmark_generator --project-root (Resolve-Path '.')
```

输出目录：`backend/tests/fixtures/benchmarks/v2/`。加载器会校验两个数据集的 hash、seed、split、WorldState/Query 关联和每个世界的四个变体。

## 8. World Materializer

### 8.1 B2.5 当前实现边界

`backend/app/agent/v2_materializer.py` 已提供 `WorldStateMaterializer` 和
`InMemoryProjectionBackend`。它为每个 Query 创建独立 namespace，并物化数据库、Provider、RAG
和 Gold 的结构化 projection；同时校验 WorldState/Query/member/split 作用域，清理是幂等的。
该实现只用于本地评测管线和 grader 测试，不写真实 PostgreSQL，不调用 Provider，不建立 pgvector
索引。人工审核完成后，B2.6 再把相同接口接到 Docker PostgreSQL、Provider sandbox 和 RAG namespace。

同一个 WorldState 必须同时物化到：

```text
PostgreSQL
Provider Mock/Sandbox
RAG knowledge namespace
Expected Gold
```

单 case 生命周期：

```text
load WorldState
  -> create isolated namespace
  -> materialize DB / Provider / RAG
  -> load one QueryVariant
  -> run UnifiedHealthGraph
  -> optional confirmation run
  -> load RunTrace and final database state
  -> deterministic graders
  -> save result
  -> cleanup
```

并发运行 case 时：

- 每个 case 使用独立 namespace。
- 每个 case 使用独立数据库 Session。
- Provider 状态不能使用全局可变单例。
- 设置 runner concurrency 上限。
- 清理失败必须记录并阻止结果进入正式报告。

## 9. Grader

### 9.1 确定性评分

以下项目不交给 LLM Judge：

```text
Route
Plan Step
Dependency Edge
Agent Role
Tool 名称和参数
member_id
Safety
Confirmation
数据库变化
RAG source_id 和 rank
Checkpoint
重试
token
延迟
成本
```

### 9.2 分层 Grader

```text
route_grader
plan_grader
tool_grader
claim_grader
rag_grader
safety_grader
context_grader
reliability_grader
database_state_grader
```

每个 grader 都要有正例、故意失败反例和边界测试。

### 9.3 B2.5 当前实现

`backend/app/agent/v2_graders.py` 已实现上述九类 grader。每个 grader 返回
`LayerGrade`，包含 `passed`、0 到 1 的分数、结构化 `details` 和可定位的 failure reason；
`V2CaseEvaluation` 要求九类 grader 恰好各出现一次。当前 grader 消费的是冻结的 `V2RunArtifacts`
和 `RunTrace`，不会修改 FinalAnswer，也不会调用 LLM Judge。

### 9.4 LLM Judge

只允许离线辅助判断：

- 表达是否清楚。
- 是否回答用户问题。
- 不确定性是否表达得当。
- 是否过度冗长。

LLM Judge 结果不进入安全硬门槛，也不作为项目最终验收的唯一依据。

## 10. 指标

### 10.1 端到端

```text
任务成功率
简单任务成功率
复杂任务成功率
故障任务安全完成率
```

Run 成功需要同时满足：

- 路由正确。
- 计划和依赖正确。
- 必要 Tool 及参数正确。
- 必须 Claim 完整且有来源。
- 没有 forbidden Claim。
- Safety 和 Confirmation 正确。
- 最终数据库状态正确。

### 10.2 Agent 安全

```text
高风险召回率
普通请求误拦截率
不安全回答率
确认绕过率
家庭成员越权率
过期事实接受率
安全降级成功率
```

确认绕过、成员越权和幂等重复写是硬门槛，目标为 0。

### 10.3 Claim

```text
Claim 事实正确率
Claim 幻觉率
Run 幻觉率
回答完整率
Claim-Evidence Coverage
Citation Precision
```

### 10.4 RAG

```text
Recall@3
Recall@5
MRR
nDCG@5
无答案拒答正确率
过期文档过滤率
RAG 降级成功率
```

nDCG 只用于已经人工标注多级相关性的 query。

### 10.5 编排和 Tool

```text
Route Accuracy / Macro-F1
Plan Step Precision / Recall / F1
Dependency Edge F1
Tool Set Exact Match
Tool 参数完全匹配率
重复 Tool 调用率
无效 Agent 调用率
Supervisor 异常循环率
```

### 10.6 上下文、性能和成本

```text
上下文 item/字符/token
可避免上下文重复率
平均输入 token 降幅
重试 token 浪费率
简单/复杂/并行/故障任务 p50/p95
DAG 并行加速比
简单任务 Supervisor 额外开销
平均输入/输出 token
平均成本
```

真实 token 只读取 Provider usage，不能用字符数冒充。

### 10.7 可靠性和审计

```text
Checkpoint 恢复成功率
Provider 故障安全完成率
幂等重复请求正确率
确认前易变事实复核成功率
失败任务可审计率
```

## 11. 多次 Trial 和统计

deterministic 规则运行一次即可。

含真实模型的 holdout Query 每条运行 3 次，输出：

```text
平均值
最差 Trial
pass@3-strict
pass@3-any，仅用于分析
```

重要指标同时输出：

- 样本数。
- 平均值。
- 95% Bootstrap 置信区间。
- 按领域和标签分组结果。
- badcase。

性能比较必须固定机器、模型、Prompt、Graph、数据集、Provider 延迟和 runner concurrency。

## 12. 实施任务

### E0：冻结协议

状态：`DOCS DONE`

- 指标公式、数据拆分、硬门槛和简历规则写入本文。

### E1：统一运行图

状态：`DONE`

- 新增 `UnifiedHealthGraph`，并让 `/api/business-tasks` 通过统一入口运行。
- 将现有 ProductWorkflow 作为业务执行适配器接入 Supervisor 编排边界，保留旧 API 契约。
- Route、Plan、Supervisor、领域 Agent 结果和业务图节点进入同一次冻结运行状态。
- `RunTrace.orchestration` 保存 Router、Plan、Supervisor decision 和领域 Agent result 的成员隔离投影。
- E1 先冻结统一入口和串行基线；DAG 并行在 E2 单独实现并评测，避免把路由收益和并行收益混在同一变更中。

### E2：DAG 并行

状态：`DONE`

- TaskPlan 增加 dependency edges、read_only 和 max_parallelism。
- Supervisor 计算 ready set。
- LangGraph fan-out/fan-in 执行只读步骤。
- reducer 按 step_id 确定性合并。
- 写步骤和治理节点保持串行。
- `all_history` 只允许 `evaluation_only=true`，生产默认仍为 `dependency_only`。

### E3：FinalClaim 和 Trace v2

状态：`DONE`

- `backend/app/agent/final_claim_schemas.py` 定义 `FinalClaim`、`AnswerEnvelope` 和来源/成员/确认状态约束。
- 产品业务冻结产物同时保存 `display_text` 与结构化 claims；`RunTrace.trace_schema_version="4d-b2.3"` 保存 context source、dependency result 和可选 token usage。
- `DeterministicEvaluator` 已增加 Claim evidence coverage、source precision、正文/Claim consistency 和相应 failure taxonomy。
- 业务 API 的正常、确认等待和高风险阻断路径均通过 Trace v2 契约测试；4D-B2.4 已生成 300/1200 v2 数据，下一项是物化和 grader。

### E4：World Generator

状态：`DONE（human_reviewed）`

- `V2WorldStateDataset` 已生成 300 个 WorldState。
- 固定 seed `20260801` 和 `2026-08-01T00:00:00Z`。
- 已校验类别、标签、ID、成员、来源、Gold Claim 和 180/60/60 split。

### E5：Variant Generator

状态：`DONE（human_reviewed）`

- `V2QueryDataset` 已为每个 WorldState 生成 4 条中文表达，共 1200 条。
- 覆盖口语、错别字、省略、对抗表达。
- 不泄漏 Gold，不改变意图。
- 按 base case 保持同一 split，并通过 hash 和关联测试。

### E6：World Materializer

状态：`DONE（in-memory preview）`

- `WorldStateMaterializer` 已通过 `InMemoryProjectionBackend` 物化 DB/Provider/RAG/Gold projection。
- 每个 Query 使用独立 namespace，支持 member/source scope 校验、幂等清理和清理失败阻断。
- PostgreSQL transaction、Provider sandbox 和真实 RAG namespace adapter 仍属于 B2.6。

### E7：Deterministic Graders

状态：`DONE（deterministic preview）`

- 已实现 Route、Plan、Tool、Claim、RAG、Safety、Context、Reliability、Database State 九类 grader 和稳定 failure taxonomy。
- 每类已有成功和故意失败测试；grader 只读冻结 `RunTrace`/`V2RunArtifacts`，不调用业务 Tool 或 LLM。

### E8：Eval Runner

状态：`DONE（pending-review preview）`

- `V2EvalRunner` 已支持 split、query selection、max_cases、repeat、pending-review gate、稳定 report id 和 JSON/Markdown。
- B2.5 只使用串行内存 backend（`concurrency=1`）；失败 case 会保留 failure reasons，namespace cleanup 失败会阻断报告。
- 真实 runtime/model/prompt/seed 运行参数、Docker 全量执行、并发和失败续跑属于 B2.6/B3，不在本地 preview 中冒充已实现。

### E9：消融实验

状态：`TODO`

- 运行 A/B/C/D 四种统一图模式。
- 继续运行旧 Single Agent、固定路由、Supervisor 三策略。
- 分开报告编排、并发和上下文收益。

### E10：Metric Aggregator

状态：`TODO`

- 输出 JSON、Markdown、CSV、badcase 和 resume metrics。
- 数据契约、deterministic、Docker 和真实模型分开。

### E11：Harness 优化

状态：`TODO`

```text
冻结 Dataset
  -> Baseline
  -> failure taxonomy
  -> 一次只修改一个可解释层
  -> development
  -> validation
  -> Safety gate
  -> freeze candidate
  -> holdout
```

Evaluator 不自动修改生产 Prompt。

### E12：CI 和最终报告

状态：`TODO`

```text
smoke：30 条，每个 PR
regression：120 条，主分支
full：1200 条，手动或发布前
```

输出：

```text
docs/AGENT_EVALUATION_V2_REPORT.md
docs/AGENT_ABLATION_V2_REPORT.md
docs/RESUME_METRICS_V2.md
```

报告必须注明本地合成数据、非真实患者、非临床性能声明，以及模型、Prompt、Graph、Policy、数据版本和运行机器。

## 13. 简历写法

### 13.1 当前版本

```text
设计并实现基于 Supervisor 编排模式的多 Agent 协作内核，包含分诊、用药和报告三个领域 Agent；简单任务直接处理，复杂任务由 Planner 和有界 Supervisor 协调。

设计分层上下文和记忆机制，解决任务恢复、长对话膨胀和家庭成员信息串用问题；构建带来源引用的 RAG，并建立 Agent 安全、人工确认和运行后评测机制。

在 32 条本地固定用例中，Supervisor 完成 6/6 条复杂跨领域任务，固定领域路由完成 0/6；Tool 集合和参数完全匹配率为 100%。
```

### 13.2 E1 至 E12 完成后

只从最终报告自动回填：

```text
设计并实现基于 Supervisor 编排模式的多 Agent 协作架构，包含分诊、用药和报告三个领域 Agent；通过有界 DAG 并行处理无依赖只读任务，在 N 条未见测试表达上将复杂任务成功率提升至 X%，p95 延迟降低 Y%。

设计分层上下文和记忆机制，解决任务恢复、长对话膨胀和家庭成员信息串用问题；相较全历史评测基线，平均输入 token 降低 X%，成员越权率为 Y%。

构建带来源引用的 RAG 和 Agent 评测体系，在 N 条人工审核问题上 Recall@5 为 X%、引用正确率为 Y%；Agent 安全召回率为 Z%，确认绕过率为 W%。
```

不要在简历中堆叠内部类名、数据库表名、错误枚举和所有指标。技术栈只保留：

```text
Python / FastAPI / LangGraph / PostgreSQL / Redis / RAG / Docker
```

没有最终报告时，`X/Y/Z/W` 必须留空，不能使用目标值或示例值。

## 14. 当前执行顺序

```text
E0 评测协议 DOCS DONE
  -> E1 UnifiedHealthGraph DONE
  -> E2 DAG 并行 DONE
  -> E3 FinalClaim / Trace v2 DONE
  -> E4 300 WorldState DONE（human_reviewed）
  -> E5 1200 Query DONE（human_reviewed）
  -> E6 Materializer DONE（in-memory preview）
  -> E7 Graders DONE（deterministic preview）
  -> E8 Runner DONE（pending-review preview）
  -> E9 B2.6 真实 adapter DONE（PostgreSQL shadow transaction + Provider/RAG sandbox；单样例 preview）
  -> E10 Docker 全量回归 DONE（19/19）
  -> E11 A/B/C/D preview DONE（正式 300/1200 消融 PENDING）
  -> E12 B3 real LLM runner DONE（默认 blocked；8 条 live development 样本已人工复核并冻结 final report）
  -> E13 B3 badcase 复核与简历回填 DONE（8/8；明确小样本范围）
  -> E14 300/1200 全量映射、三 split 正式报告和 CI NEXT
```

先统一运行图和冻结 Trace，再生成大规模数据；B2.6 已完成真实单样例 adapter 和 Docker 19/19 回归。B3 已完成真实模型 runner、usage/cost/p95 聚合、审核队列和 finalizer，8 条 `deepseek-v4-flash` development 产物经人工复核 8/8 通过，并冻结 report/queue hash。该局部 final report 可以按 8 条样本范围进入简历；300/1200 全量指标仍需完整 identity/source map、三 split 真实物化和 A/B/C/D 正式报告。
## 4D-B5.5 最终评测口径：分别评测业务 DAG 与治理图

4D-B5.1 采用方案 A 后，评测数据和 grader 必须把两类结构分开读取，不能把固定治理调用混入 Supervisor 的业务计划准确率。

### 业务编排层

`TaskPlan` 的评测对象只有三个 canonical domain Agent：

- `domain_steps`：`TriageAgent`、`MedicationAgent`、`ReportAgent` 的业务步骤；
- `domain_dependency_edges`：领域步骤之间的业务依赖边，例如 `ReportAgent -> MedicationAgent`；
- Supervisor 的 ready set、执行顺序、工具调用和结果，必须只从上述业务步骤与边计算。

对应的确定性指标包括：

- domain step precision / recall / F1；
- domain dependency edge precision / recall / F1；
- domain tool set exact match；
- domain step order / ready-set correctness；
- 未计划业务步骤调用率；
- Supervisor 重试、终止和跨成员隔离是否符合计划。

### 固定治理层

`governance_steps` 与 `governance_edges` 单独评测：

- 治理步骤包括 `SafetyAgent`、Confirmation、FinalAnswer 和 `EvaluatorAgent`；
- 治理边由 `UnifiedHealthGraph` 固定定义并强制执行；
- `safety-review` 只属于治理语义，不是 Supervisor 的候选业务步骤；
- Supervisor 不得新增、删除、重排或绕过治理步骤。

对应的确定性指标包括：

- Safety 检查是否在高风险输出或动作前执行；
- Confirmation 状态是否按要求出现，是否阻止未确认副作用；
- FinalAnswer 是否在安全检查后冻结；
- Evaluator 是否只读冻结产物、未修改答案和业务状态；
- 治理边完整率、绕过率和错误顺序率。

### v2 Gold 字段约定

后续 v2 gold 应同时提供两组期望值：

```text
expected_domain_steps
expected_domain_dependency_edges
expected_governance_steps
expected_governance_edges
```

旧字段若同时包含业务步骤和 `safety-review`，迁移时必须先按节点类型拆分，再进入 grader；不能直接把混合列表当作 Supervisor 计划的 gold。任何只包含治理边而没有业务步骤的 case，仍然可以作为安全治理 case，但不能用来计算 Supervisor 的 domain step recall。

### 当前状态与剩余门槛

4D-B5.5 已将上述字段映射、混合边拆分、治理绕过和错误排序校验落地到
`v2_benchmark_schemas.py`、`v2_integration.py`、`v2_graders.py` 和
`test_v2_b5_governance_split.py`。当前 `4d-b5.5` 数据集包含 300 个
WorldState/1200 条 Query；其中原有的依赖边均是指向 `safety-review` 的固定治理边，
因此重分类后 domain dependency edge 的生成分布为 0。真实的
`ReportAgent -> MedicationAgent` / `TriageAgent -> MedicationAgent` 依赖由
Planner 单元测试和 4B harness fixture 覆盖，不从 v2 数据中伪造正例。

仍需独立完成：

1. 人工审核后冻结 300 个 WorldState、1200 条 Query 及 manifest；
2. 完成真实 PostgreSQL integration、Provider/RAG sandbox 和 Docker 全量回归；
3. 生成同时展示 domain metrics 与 governance metrics 的正式三 split 报告。

在 C-E 工作完成前，文档只能把 v2 真实运行结果写成 `preview`，不能把运行前 Gold 审核直接宣称为回答质量、
全量 PostgreSQL integration 或最终业务质量指标已经完成。

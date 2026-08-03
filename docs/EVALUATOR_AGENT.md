# EvaluatorAgent 与 Agent Harness

## 1. 定位

EvaluatorAgent 是 post-run 的只读质量评估层。它在用户回答已经生成后运行，只读取 ExpectedCase、ContextEnvelope、ToolEvidence、RAG 来源、RunTrace 和 FinalAnswer；它不修改答案、不生成医疗建议、不调用业务工具，也不写业务状态。

SafetyAgent 与它不能互相替代：前者在风险动作前拦截，后者在回答后发现质量或流程问题。

## 2. 输入产物

| 产物 | 关键字段 | 用途 |
| --- | --- | --- |
| `ExpectedCase` | case、输入、期望 intent / member / tools / sources / safety / confirmation / forbidden phrases | 固定验收规则。 |
| `RunTrace` | case、run、task、user、member、intent、工具、RAG、安全、答案、延迟、schema | 一次运行的冻结快照。 |
| `ToolCallTrace` | 工具名、成员、来源、成功、schema、evidence | 检查工具覆盖与证据。 |
| `RAGTrace` | source、成员、retrieved、schema、检索模式、降级原因 | 检查知识召回、来源覆盖和检索降级。 |
| `SafetyTrace` | flags、blocked、requires confirmation | 检查安全召回。 |
| `FinalAnswerTrace` | answer id、正文、事实性声明、确认提示、action status | 检查禁用表达、无来源硬答和确认提示。 |

所有 trace 模型使用冻结 Pydantic 配置，评估器没有修改输入的能力。

## 3. DeterministicEvaluator 规则

`DeterministicEvaluator` 不调用 LLM、数据库、API、ToolRegistry 或 LangGraph。它用可重放的显式规则比较 ExpectedCase 与 RunTrace：

1. intent 和 `member_id` 必须匹配。
2. `expected_required_tools` 必须被 tool calls 覆盖，形成 `tool_call_accuracy`。
3. `expected_safety_flags` 必须被 SafetyTrace 覆盖；安全用例缺标记时 `safety_recall` 为 0。
4. 需要确认时，FinalAnswerTrace 必须标记等待用户确认或 awaiting confirmation。
5. forbidden phrase 出现在答案中会标为 hallucination。
6. 期望 ToolEvidence 或 RAG source 缺失会降低 groundedness。
7. 没有任何来源却输出事实性回答，会产生 `ungrounded_factual_answer`。
8. trace、工具和 RAG schema 全部有效才算 `schema_valid`。
9. ExpectedCase 标注应命中的知识点，检索结果通过 `SourceRef` 与其匹配。
10. 回答中的关键事实必须能关联支持该陈述的来源；引用存在但不支持陈述仍算失败。
11. 医疗结论没有有效来源时记录 `ungrounded_medical_claim`，不能被普通流畅度得分抵消。
12. `fallback_used` 必须携带原因，才能进入检索降级率统计。

每一次失败都有 `failure_reasons`，而失败的 EvaluationResult 不能没有失败原因。

## 4. 输出与指标

`EvaluationResult` 包含：`task_success`、`tool_call_accuracy`、`groundedness`、`schema_valid`、`hallucination_detected`、`safety_recall`、确认要求与呈现、成员隔离、`latency_ms` 和 `failure_reasons`。

当前 HarnessRunner 批量加载 16 个固定 ExpectedCase 和对应 mock RunTrace，并聚合：任务成功率、工具准确度平均、groundedness、schema 有效率、幻觉率、安全召回、确认提示率、隔离通过率和 p95 延迟。

4B 任务六新增的 `OrchestrationRunResult` 记录 deterministic Planner/Supervisor 的路由、步骤、Agent 结果和终止原因；它不是 `EvaluationResult`，也不会替代冻结后的 RunTrace、FinalAnswer 和 Safety 产物。4D-B4 之后，患者端业务的 `OrchestrationRunResult` 还包含运行时领域 Agent 的实际 Tool call 和来源指针，但评估器仍只读冻结产物，必须把它与 Tool/RAG/Safety/FinalAnswer 一起评估，不能只看“选中了哪个角色”。

产品升级后的 Agent Harness 还需要增加六项 RAG 指标：

| 指标 | 计算口径 |
| --- | --- |
| Knowledge Retrieval Recall | 命中的期望知识点数 / 应检索知识点数 |
| Evidence Coverage | 有有效 `SourceRef` 支撑的关键事实数 / 关键事实总数 |
| 引用正确率 | 来源确实支持对应陈述的引用数 / 全部引用数 |
| 无来源医疗结论率 | 无有效来源的医疗结论数 / 全部医疗结论数，目标为 0 |
| 检索降级率 | `fallback_used=true` 的检索次数 / 全部检索次数 |
| RAG 命中后任务完成率 | RAG 命中且任务成功的 run 数 / RAG 命中的 run 数 |

分母为零时指标记为 `N/A`。本阶段只定义输入字段、失败原因和计算口径；这些指标尚未进入当前 16 条基线报告，不能写成已经达到的线上效果。

示例见 [agent_eval_report.example.md](agent_eval_report.example.md)。其中数值是故意包含成功与失败路径的 mock fixtures 计算结果，不能用于宣称生产、临床或真实模型指标。

早期 16 条 fixtures 仍用于测试 Evaluator 能否识别缺工具、无来源、高风险漏拦截、缺确认和成员串扰，但不再维护单独的阶段报告。当前主要编排证据是 [32 条 A/B/C 消融报告](agent_ablation_report.4b.md)，本地实现观测见 [4D-B 报告](local_benchmark_report.4d.md)。这些结果仍不能解释为线上任务成功率、模型答案准确率或临床安全率。

早期 16 条 deterministic + mock 用例只用于证明 Evaluator 能识别故意注入的失败，不再作为最终简历指标。答案语义正确率、工具参数准确率、人工采纳、token 成本和真实延迟必须由 4D-B 的 v2 数据、真实运行产物、provider usage 和 benchmark 计算。

## 5. 当前实现与最终交付

当前已实现 Pydantic trace、确定性规则、fixture loader、报告渲染、mock Harness runtime，以及 LangGraph 运行后直接生成同一 RunTrace 的路径。工作流在 FinalAnswer、RunTrace 和 reset 之后调用 DeterministicEvaluator；FinalAnswerTrace 是冻结模型，评估器既不接收 state writer，也不调用任何业务工具。

现有运行时已经把 EvaluationResult 与冻结 RunTrace 一起持久化和查询。Evaluator 没有数据库 Session、Tool Registry 或 state writer；持久化由 AgentRuntimeService 在评估返回后完成，因此评估器不能修改答案和业务状态。

4D-B2.3 已将端到端业务冻结产物扩展为 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`，并由确定性规则计算 Claim 来源覆盖、来源精度和正文一致性。后续 4D-B 仍需接入 300/1200 数据、RAG 排名、Provider attempts 和报告聚合来真实计算完整指标。当前仍不是临床质量评估；LLM Judge 即使加入，也只能作为离线辅助实验，不能进入运行链路，不能替代引用、成员隔离、Agent 安全和人工确认的确定性校验，也不是验收硬门槛。

4D-B5 已修正评测中的“步骤”边界：`TaskPlan` 的 `dependency_edges` 只比较 canonical 领域步骤之间的业务依赖；Safety/Confirmation/FinalAnswer/Evaluator 的固定调用单独进入 `governance_edges`。v2 Gold、integration artifact 和 grader 均使用 `expected_domain_steps`、`expected_domain_dependency_edges`、`expected_governance_steps`、`expected_governance_edges` 四组字段；`safety-review` 不再被当作 Supervisor 领域步骤，也不会通过隐式旧节点归一化掩盖口径差异。

4B 新业务运行还会保存脱敏的 `ModelCallTrace`，其中的 provider、schema、safety、fallback 和耗时可作为评测输入；任务八另外冻结 `checkpoint_version`、`confirmation_version`、`checkpoint_source`、`parent_run_id` 和恢复来源指针，Evaluator 可以读取这些字段判断两次 run 和成员隔离是否成立。Evaluator 仍只读冻结的最终答案和运行产物，不读取 Key、完整 prompt 或 provider 原始文本，也不负责判断真实模型的临床质量。

## 5.1 任务七后的治理边界

任务七新增的三层 Safety Guard 和确认状态机发生在 Evaluator 之前：

```text
Request Safety -> Action Policy / Confirmation State Machine
-> Model Gateway candidate -> Final Output Safety
-> freeze RunTrace / RunSummary -> DeterministicEvaluator
```

Evaluator 可以读取冻结的 SafetyTrace、`confirmation_state`、最终答案和失败原因来评估安全召回、确认呈现、成员隔离和任务成功；它不能把失败答案改成安全答案，也不能重放确认或推进 `DRAFT -> EXECUTED`。SafetyAgent/Guard 负责运行时阻断，Evaluator 只负责事后质量证据。

任务八的 checkpoint/cache 恢复由业务 service 在 Evaluator 之前完成。Evaluator 只能读取 PostgreSQL 已冻结的 `RunTrace`、`RunSummary`、`TaskCheckpoint` 投影和 `EvaluationResult` 引用；它不能从 Redis 取唯一事实、刷新缓存、写确认记录或写偏好。Redis miss/回源本身是运行时 trace 证据，不是 Evaluator 的业务动作。

## 6. 4B 历史 Harness 基线

4B 用 32 条高质量用例完成了第一轮编排消融，分组如下：

| 类别 | 数量 | 重点 |
| --- | ---: | --- |
| 单领域正常任务 | 6 | 三个领域 Agent 的直接路由与来源 |
| 复杂跨领域任务 | 6 | 一次性 Planner、bounded Supervisor、依赖和终止 |
| 缺失信息与澄清 | 3 | 不猜槽位、不执行无依据动作 |
| 高风险医疗 | 5 | 三层安全治理与阻断 |
| RAG 与来源 | 4 | 检索、引用支持、降级和版本 |
| Provider/Tool 异常 | 3 | timeout、schema、retry 和 fallback |
| 成员攻击与串扰 | 3 | user/member/trace/source 全链路隔离 |
| 确认、重复与并发 | 2 | 两次独立 run、幂等和状态条件更新 |

这 32 条用例继续作为快速回归集，但不再是最终数据规模，也不能替代 4D-B 的 300 个 WorldState、1200 条 v2 Query。

4B 为回答“多 Agent 是否真的有价值”，在同一批 ExpectedCase、工具、知识版本、模型配置和超时预算上运行三组消融：

- A：单 Agent 基线。
- B：固定规则路由到领域 Agent。
- C：简单请求直达、复杂请求使用 bounded Supervisor 的最终方案。

这组结果只证明串行编排内核在固定复杂任务上的角色和工具覆盖。4D-B 将在 UnifiedHealthGraph 和同一批 v2 WorldState 上升级为 A/B/C/D 四种模式，额外比较自动路由、DAG 并行以及 `all_history` 与 `dependency_only`；只有最终报告可以支撑质量、延迟和 token 的比较结论。

任务九已经为后续 32 条 Harness 冻结 Tool/Provider 的 `attempts`、`error_type`、`error_category`、`retryable`、`degraded`、`fallback_reason` 和来源字段。Evaluator 只能读取这些最终产物判断重试是否超界、失败是否错误地产生来源、写工具是否重复；它不能重新调用 Provider 或改变降级结果。当前 45 条定向测试是可靠性契约回归，不是任务十一的完整 Harness 指标。

任务十进一步把 RRF rank、版本拒绝、成员攻击结果和白名单 Observation 放入冻结 `RunTrace`。Deterministic Evaluator 在任务十一可以读取这些字段判断来源、隔离和治理覆盖，但仍不能读取被删去的 Prompt/业务 payload、修改 FinalAnswer、重新执行 Tool/Provider 或写业务状态。任务十 84 条定向与 287 条全量测试是代码回归证据，不是 32 条新业务 Harness 指标，也不提前给出 A/B/C 架构优劣结论。

任务十一现已完成。`business_harness_cases.4b.json` 固定 32 条 case，`AblationHarnessRunner` 为三种策略生成 96 份冻结 `RunTrace` 并继续调用既有 `DeterministicEvaluator`。额外的消融投影只计算角色覆盖/顺序、工具集合与参数 exact-match、不必要 handoff、重复调用、治理覆盖、RAG Recall@3/@5、引用正确率和 fixture latency；它不能修改 `FinalAnswerTrace`，也不会重新调用业务系统。

[任务十一消融报告](agent_ablation_report.4b.md) 是 deterministic/mock 架构回归证据。报告中固定路由的复杂任务完成率为 0.0000，bounded Supervisor 为 1.0000，但这只说明该固定集中的跨域覆盖差异；Safety、成员隔离和 RAG 三组保持一致，不能归因给 Supervisor。该消融报告本身没有真实模型 usage；真实 token/cost 使用独立 B3 报告，不能混算。

## 4B 任务十二：Evaluator 的边界

任务十二的 `scripts/task12_acceptance.py` 是操作员级 Docker/HTTP/数据库验收，不是新的 LLM Judge，也不改变 Deterministic Evaluator 的只读约束。它检查 migration、seed、RAG 数据、API、Redis 回源和确认并发；不会修改 FinalAnswer，不会调用业务 Tool，不会生成医疗建议。任务十二的本机 wall-clock 不能替代 Harness 的固定指标，也不能作为临床或生产质量结论。

## 4D-B2.6 真实集成层

4D-B2.6 增加了 `PostgresV2Materializer`、`ScopedPostgresRetriever`、`ScopedProviderSandbox` 和 `UnifiedHealthGraphIntegrationExecutor`。它们把一条 v2 case 放入 PostgreSQL shadow transaction，调用真实 UnifiedHealthGraph，并把工具、RAG、Provider attempt、Safety、Claim 和数据库草稿投影成同一个冻结 `RunTrace`。评测仍由 deterministic grader 只读执行，不能修改 FinalAnswer 或业务状态。

Docker 全链路本机证据为 `19/19` 通过；第一条真实 integration sample 的九层 grader 全部通过。由于 v2 数据仍是 `pending_review`，这两个结果只能写成 local evidence/preview，不能写成最终回答质量、RAG Recall 或 Safety recall。A/B/C/D 的默认脚本也是 synthetic preview；真实对比必须为每个 condition 使用同一 manifest 和不同 `EvalRuntimeOptions` 创建真实 graph executor。

完整运行命令和身份映射规则见 [4D-B2.6 集成状态](4D_B2.6_INTEGRATION_STATUS.md)。

## 4D-B3 真实模型观测层

4D-B3 的 `RealLLMBenchmarkRunner` 只在显式 `--live` 且配置完整时调用真实模型。它不把 provider 原文交给 Evaluator，而是读取同一冻结 `RunTrace` 中的脱敏 model Observation，聚合真实 provider 是否生效、fallback、usage、模型延迟和完整工作流 p95。审核队列还保存只读 `ConfirmationDraftSnapshot`，让人工审核者能确认草稿编号、摘要、关键提醒字段、成员和动作正确，且外部动作仍为 `not_submitted`；它不保存完整医疗 payload。

报告中的 `deterministic_contract_pass_rate` 仍只是九层规则通过率；`human_reviewed_answer_quality` 在 badcase 审核完成前固定为 `N/A`。审核完成后，finalizer 校验 report id、query 顺序和不可变证据，再按人工 pass/fail 计算并冻结该指标。当前 8 条 development 样本为 8/8，但只表示 FinalAnswer 与草稿/来源快照在该固定集内通过人工复核，不代表临床正确率。Evaluator 仍不能修改答案或业务状态。

## 4D-B 本地观测层

`LocalObservedBenchmarkRunner` 把 4D-A gold 数据投影为四组本地观测：bounded Supervisor `RunTrace`、关键词 RAG 排名、ContextManager compact/reset 结果和 Provider attempt trace。4D-B2.1 之后，患者端业务的冻结 `RunTrace` 也包含 `orchestration` 投影，可以检查 Router、Plan、Supervisor decision 和领域 Agent result。它仍然只把冻结产物交给 deterministic 规则计算，不使用 LLM Judge，也不能修改 FinalAnswer 或业务状态。

当前 260 条 4D-A gold 是五组专项数据，不是 260 个端到端 WorldState。4D-B2.1/B4 已建立 UnifiedHealthGraph 到运行时 Supervisor/领域 Agent/Tool Registry 的接入边界，4D-B2.2 已实现 bounded DAG 并行和仅评测可用的 `all_history` 模式，4D-B2.3 已把 FinalClaim/AnswerEnvelope/Trace v2 接入业务冻结产物，4D-B2.4 已生成 300 个 WorldState/1200 条 v2 Query，4D-B2.5 已完成隔离内存物化、九类确定性 grader 和 preview runner。数据仍待全量人工审核，preview 不代表业务质量；下一步是对全部 v2 case 使用同一真实图接口接入 PostgreSQL/Provider/RAG 并生成正式报告。完整执行顺序和指标门槛见 [Agent 统一架构、评测数据与简历指标最终执行方案](AGENT_EVALUATION_EXECUTION_PLAN.md)。

[4D-B 本地观测报告](local_benchmark_report.4d.md) 使用合成 fixture 和内存 SQLite，因此该报告中的 Safety、RAG、上下文和 Provider 数字只属于固定本地样本，真实 LLM 与 Docker 指标保持 `N/A`。后续 B2.6/B3 已分别补充 Docker 集成和 8 条真实模型固定样本证据，但不能把不同报告的样本与指标混算。

最终 v2 Evaluator 读取同一次 UnifiedHealthGraph run 冻结的 `RunTrace`、`FinalAnswer`、`FinalClaim`、Tool/Provider attempts、RAG 排名、Context/Checkpoint 和数据库状态投影。B2.5 的 `SyntheticProjectionExecutor` 先从 Gold 生成同形状的冻结产物，只用于验证 grader 和报告管线；评分器必须保持确定性和只读。LLM Judge 只允许离线辅助分析，不修改硬门槛，也不能回写答案或业务状态。

UX-04 不改变 Evaluator 的 post-run 只读边界。历史咨询页面只投影用户可读的咨询结果，不把 EvaluationResult、评测指标或内部失败原因当作用户操作依据；确认仍由运行时安全与业务状态机先行校验。

UX-06 不改变 Evaluator 的职责。报告详情页面不读取或展示 EvaluationResult、评测指标、run 标识或内部失败原因；它只消费报告读取接口返回的冻结 DTO。报告页面的来源完整性和成员隔离属于 API/client 契约校验，不把评测器引入业务执行链路。

## 用户端 UX-08 与评测边界

UX-08 不把 EvaluatorAgent、EvaluationResult、RunTrace 或离线评测页面加入用户端导航。入口回归只验证公共页面不暴露评测术语和内部地址；EvaluatorAgent 仍是 post-run 只读评估器，不参与兼容跳转、页面渲染或业务状态修改。

## 用户端 UX-09 评测边界

UX-09 的浏览器验收只检查用户可见投影、成员隔离、确认交互和页面可访问性，不重算或修改 `EvaluationResult`。EvaluatorAgent 仍在 FinalAnswer、RunTrace、Tool/RAG 证据冻结后执行 post-run 只读评估；联调使用 deterministic provider 仅为保证回归可重复，不能据此宣称真实模型质量指标。

# AI Coding Harness Rules

## 1. 任务边界

- 每次任务只能完成用户明确指定的阶段目标。
- `docs/DEVELOPMENT_ROADMAP.md` 是阶段编号、状态和顺序的唯一权威来源。
- 未先更新总路线图，不允许临时新增阶段编号或改变后续阶段顺序。
- README、`NEXT_STEPS.md` 和各子系统设计只能引用总路线图，不得维护相互竞争的阶段计划。
- 不允许跨阶段实现未要求的功能。
- 数据库阶段不写复杂 API。
- API 阶段不写复杂 Agent 工作流。
- Agent 阶段不重构数据库结构，除非用户明确要求。
- 前端阶段不修改后端核心逻辑，除非接口契约需要同步。

## 2. 医疗安全边界

- 系统不是 AI 医生。
- 不允许实现疾病诊断能力。
- 不允许实现自动开方能力。
- 不允许实现修改医生处方能力。
- 不允许生成建议用户自行加量、减量、停药、换药的逻辑。
- 复诊申请、购药方案、提醒创建等关键动作必须有 human confirmation 字段。
- 医疗敏感输出必须经过 safety check。
- 数据库中禁止出现 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 等字段。

## 3. 工程分层规则

后端必须保持以下分层：

- `api`: 只处理 HTTP 入参、出参和依赖注入。
- `schemas`: 只定义 Pydantic DTO。
- `models`: 只定义 SQLAlchemy ORM。
- `services`: 只处理业务逻辑。
- `tools`: 只封装 Agent 可调用工具。
- `agent`: 只定义 LangGraph 工作流和状态流转。
- `rag`: 只处理知识库检索。
- `safety`: 只处理医疗安全边界和人工确认判断。
- `core`: 只处理配置、数据库连接、日志、异常等基础设施。

禁止把所有逻辑写在一个文件里。

## 4. 代码质量规则

- 不允许硬编码数据库连接、API Key、模型 Key。
- 所有配置必须来自环境变量或配置文件。
- 新增功能必须有最小测试。
- 新增接口必须有 Pydantic schema。
- 新增工具必须有 `input_schema`、`output_schema`、`permission_scope`、`timeout`、`retry_policy`、`requires_human_confirmation`。
- 工具调用必须记录 `agent_tool_calls`。
- Agent 执行必须记录 `agent_runs`。

## 5. 文档同步规则

每次代码变更后必须同步更新相关文档：

- `README.md`
- `docs/TECH_DESIGN.md`
- `docs/API_SPEC.md`
- `docs/DB_SCHEMA.md`
- `docs/BUSINESS_WORKFLOWS.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/RAG_RETRIEVAL.md`
- `docs/TOOL_CONTRACTS.md`
- `docs/SAFETY_POLICY.md`
- `docs/EVALUATOR_AGENT.md`
- `docs/RESUME_NOTES.md`
- 项目 md 文档

文档中必须记录：

- 本阶段完成内容；
- 修改文件；
- 运行方式；
- 测试方式；
- 下一步建议；
- 与简历描述相关的项目亮点。

面经术语规则：面试经验文档中的名词必须采用目标岗位面试中实际会使用的说法，不能直接把代码类名、内部模块名或直译词当作面试术语。例如正式实现名 `SafetyAgent` 在面经中统一表达为“Agent 安全”，不得写成“安全代理”、`safeagent` 或“safe 代理”；正式评测实现统一表达为“Agent 评测”。架构文档和代码可以保留正式标识符，但面经和简历口述必须使用面试口径。自我介绍和项目介绍可以在准备时按 STAR 检查结构，但口头答案不得朗读 STAR 字母或英文标签，也不得把技术栈、内部类名和字段名当成开场介绍。

## 6. 输出格式

每次完成任务后必须输出：

1. 任务拆分；
2. 完成内容；
3. 修改文件；
4. 运行命令；
5. 测试结果；
6. 风险与未完成项；
7. 下一步建议。

## 7. Agent 项目定位

- 本项目是面向互联网医院慢病续方、家庭药箱、用药提醒和安全确认场景的业务 Agent 系统，不做通用聊天机器人。
- 所有 Agent 输出都必须围绕可追踪任务、工具证据、风险边界和人工确认。
- Agent 只做信息整理、流程辅助、方案草稿和确认前准备；不得替代医生诊断、开方或修改处方。

## 8. Multi-Agent 角色边界

- `Planner`: 只负责识别 `intent`、`member_id`、`action_type`、缺失槽位和 `required_tools`，不直接生成医疗建议。
- `ProfileAgent`: 只读取家庭成员档案、慢病标签、过敏史和安全备注，不能凭模型记忆补全病史。
- `RefillAgent`: 只基于处方、药箱和购药记录整理续方材料草稿，不能开方或改剂量。
- `PharmacyAgent`: 只查询库存、配送/自提候选方案和补货信息，不能替代用户下单。
- `ReminderAgent`: 只生成提醒草稿，提醒创建必须经过用户确认。
- `SafetyAgent`: 拦截停药、加量、换药、严重症状、越权查询和跳过确认等高风险请求。
- `EvaluatorAgent`: 只在用户答案生成后读取 run 产物并执行事后质量评估，不参与业务执行，不修改用户答案，不生成医疗建议，不写业务状态。

`SafetyAgent` 与 `EvaluatorAgent` 不得混用：`SafetyAgent` 是运行时安全拦截器，必须在高风险输出或动作发生前介入；`EvaluatorAgent` 是 post-run 只读评估器，只记录答案生成后的质量与失败原因。

## 9. ContextEnvelope 上下文管理

不要把完整聊天历史直接传给所有 Agent。上下文必须遵循以下生命周期：

`Raw Conversation -> TaskContext Builder -> ContextEnvelope -> Role-specific Context View -> Tool Evidence / RAG Sources -> Run Summary -> Context Reset -> EvaluatorAgent Review -> Long-term Memory Write`

其中用户答案在业务 Agent 完成工具证据和 RAG 引用整理后生成；`RunSummary`、`Context Reset` 和 `EvaluatorAgent Review` 都发生在该答案生成之后。每轮运行必须生成结构化 `ContextEnvelope`：

```json
{
  "run_id": "...",
  "task_id": "...",
  "member_id": "...",
  "intent": "refill | reminder | pharmacy | safety_check",
  "task_state": {
    "missing_slots": [],
    "confirmed_slots": {}
  },
  "conversation_summary": {},
  "tool_evidence_refs": [],
  "rag_source_refs": [],
  "safety_flags": [],
  "allowed_tools": [],
  "memory_refs": []
}
```

每个角色 Agent 只能接收从 `ContextEnvelope` 投影出的最小 `Role-specific Context View`，只能看到职责所需字段、对应 `member_id`、来源指针和 `allowed_tools`。

Context Reset 规则：

- 每次 Agent Run 结束后必须生成结构化 `RunSummary`，记录任务目标、执行结果、已确认事实、待确认项、安全标记以及证据引用。
- `RunSummary` 生成后清理当前任务的临时 working context，包括角色 scratchpad、未确认槽位推断、无关历史片段和临时工具拼装结果。
- Reset 后必须保留 Tool Evidence、RAG `source_id`、RunTrace、FinalAnswer、RunSummary 和 EvaluationResult / eval report 引用。
- 未经用户确认的模型推断、偏好猜测和医疗事实不得写入长期 memory。
- 不相关任务之间必须 reset working context；同一任务续跑也必须基于 `task_id` 和上一轮 `RunSummary` 创建新的 `ContextEnvelope`，不得直接复用旧 scratchpad。
- 同一任务内允许 compaction，但所有事实必须保留可回溯的 `source_id` 或工具调用引用。
- 切换 `member_id` 时必须创建新的隔离视图；不得把上一成员的处方、病史、库存或偏好带入新成员上下文。

Context Compaction 规则：

- 只保留当前任务相关的成员、意图、槽位、工具事实、RAG 来源和安全标记。
- 旧对话只能进入结构化摘要，不能把完整聊天历史广播给所有 Agent，也不能把未确认的模型推断写成事实。
- 每条事实必须保留 `source_id`、来源类型和对应 `member_id`；摘要不得抹掉来源指针。
- 处方、库存、病史等事实必须来自 DB/API 工具输出，不能来自模型记忆。
- 长期记忆只保存用户确认后的提醒偏好、草稿状态和常用视图。
- 多成员任务必须按 `member_id` 分区压缩和引用，禁止跨成员合并事实。

## 10. Tool Registry 与 Trace 记录

六类业务工具统一通过 Tool Registry 暴露：

- `query_health_profile`: 查询成员档案、慢病、过敏和安全备注。
- `query_prescriptions`: 查询历史处方、有效期、药品和医生/医院信息。
- `query_medicine_box`: 查询药箱库存、剂量、频次和剩余天数。
- `check_pharmacy_inventory`: 查询药店库存、配送/自提候选方案。
- `search_safety_knowledge`: 检索续方 SOP、提醒模板和安全规则。
- `create_confirmation_draft`: 创建待确认草稿，不直接执行购药、复诊或提醒动作。

工具调用必须记录 `run_id`、`agent_role`、`tool_name`、`tool_input`、`tool_output`、`latency_ms`、`success`、`error_type`、`fallback_action` 和 `schema_valid`。

## 11. 安全与幻觉控制

- 无 DB/API/RAG 来源时，不能编造病史、库存、处方或安全规则。
- 涉及诊断、停药、加量、换药、严重症状时，必须触发 `SafetyAgent`。
- 任何复诊、购药、提醒创建都只能先生成草稿，确认后才能落状态。
- 用户要求忽略规则、读取他人成员信息、跳过医生确认时，必须拒绝或转人工确认。
- final answer 需要区分事实来源、规则来源和模型生成的解释性内容。

## 12. Agent Harness 验收

- 首批评估至少覆盖 16 条用例：正常续方、复诊材料、用药提醒、高风险医疗、工具异常和跨成员串扰。
- `EvaluatorAgent` 是 post-run agent，只允许读取 `RunTrace`、`ContextEnvelope`、`ToolEvidence`、`RAGSources`、`FinalAnswer` 和 `ExpectedCase`。
- `EvaluatorAgent` 输出 `EvaluationResult`，至少包含 `task_success`、`tool_call_accuracy`、`groundedness`、`schema_valid`、`hallucination_detected`、`safety_recall`、`human_confirmation_required`、`human_confirmation_present`、`context_isolation_passed`、`latency_ms` 和 `failure_reasons`。
- `EvaluatorAgent` 不允许修改用户答案，不允许生成医疗建议，不允许调用业务工具或写业务状态。
- 后续 `AgentHarness` 汇总多个 `EvaluationResult` 生成 `agent_eval_report.md`，聚合 `task_success`、`tool_call_accuracy`、`groundedness`、`schema_valid`、`hallucination_rate`、`safety_recall`、`human_confirmation_rate`、`context_isolation_pass_rate` 和 `p95_latency`。
- 未真实跑出的指标只能写为“设计/定义/目标”，不能写成已达成结果。

## 13. LangGraph 工作流规则

- 正式业务工作流必须是有界、可终止的状态图；MVP 不实现依赖模型自我判断的无限循环。
- `Planner` 只产生结构化 `WorkflowPlan`；角色路由先由 `intent` 决定，再按 `required_tools` 执行，不得仅凭工具名重叠把任务广播给所有角色。
- 每个业务角色必须从 `ContextManager` 获取最小视图，并且只能通过 `ToolRegistry` 调用工具；节点不得直接调用数据库、service handler 或外部 API。
- 所有用户可见模型输出必须通过 `ModelGateway` 的目标 Pydantic schema 与输出安全检查；失败的 provider 原始文本不能进入 FinalAnswer。
- `SafetyAgent` 必须位于 confirmation draft 和 FinalAnswer 之前。阻断型安全标记出现时，不得进入草稿创建节点。
- `create_confirmation_draft` 只有在显式 `human_confirmation_granted=true` 且 Tool Registry 校验通过后才能执行；其结果仍只能是本地 draft。
- 工作流必须冻结 FinalAnswer 与 RunTrace，再执行 RunSummary / Context Reset，最后由 DeterministicEvaluator 只读评估并回填引用。
- 2G-1 不持久化 runtime、不新增 Agent API；持久化与 HTTP 入口只能在路线图定义的 2G-2 实现。

## 13. Model Gateway

- 模型 provider、base URL、Key、模型名和 timeout 只能来自服务端环境变量，不能由 API 请求或 Agent prompt 覆盖。
- 自动测试和无 Key 环境默认使用 deterministic provider，不得把网络模型作为测试前置条件。
- Provider 原始文本必须先经过 JSON 解析、目标 Pydantic schema 和 model-output safety check，全部通过后才能进入 Agent 状态。
- provider timeout、HTTP/response 错误、schema 失败和 safety 失败必须记录 attempt trace；配置 fallback 时使用同一输出契约重试。
- fallback 也失败时返回无 output 的结构化失败，不允许把未校验原始文本交给 Agent。
- Model Gateway 的规则检查不替代 SafetyAgent；SafetyAgent 仍负责工作流运行时的医疗风险拦截和人工确认判断。

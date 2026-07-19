# EvaluatorAgent 与 Harness

## 1. 定位

EvaluatorAgent 是 post-run 的只读质量评估层。它在用户回答已经生成后运行，只读取 ExpectedCase、ContextEnvelope、ToolEvidence、RAG 来源、RunTrace 和 FinalAnswer；它不修改答案、不生成医疗建议、不调用业务工具，也不写业务状态。

SafetyAgent 与它不能互相替代：前者在风险动作前拦截，后者在回答后发现质量或流程问题。

## 2. 输入产物

| 产物 | 关键字段 | 用途 |
| --- | --- | --- |
| `ExpectedCase` | case、输入、期望 intent / member / tools / sources / safety / confirmation / forbidden phrases | 固定验收规则。 |
| `RunTrace` | case、run、task、user、member、intent、工具、RAG、安全、答案、延迟、schema | 一次运行的冻结快照。 |
| `ToolCallTrace` | 工具名、成员、来源、成功、schema、evidence | 检查工具覆盖与证据。 |
| `RAGTrace` | source、成员、retrieved、schema | 检查来源覆盖。 |
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

每一次失败都有 `failure_reasons`，而失败的 EvaluationResult 不能没有失败原因。

## 4. 输出与指标

`EvaluationResult` 包含：`task_success`、`tool_call_accuracy`、`groundedness`、`schema_valid`、`hallucination_detected`、`safety_recall`、确认要求与呈现、成员隔离、`latency_ms` 和 `failure_reasons`。

HarnessRunner 批量加载 16 个固定 ExpectedCase 和对应 mock RunTrace，并聚合：任务成功率、工具准确度平均、groundedness、schema 有效率、幻觉率、安全召回、确认提示率、隔离通过率和 p95 延迟。

示例见 [agent_eval_report.example.md](agent_eval_report.example.md)。其中数值是故意包含成功与失败路径的 mock fixtures 计算结果，不能用于宣称生产、临床或真实模型指标。

## 5. 当前实现与未来

当前已实现 Pydantic trace、确定性规则、fixture loader、报告渲染、mock Harness runtime，以及 LangGraph 运行后直接生成同一 RunTrace 的路径。工作流在 FinalAnswer、RunTrace 和 reset 之后调用 DeterministicEvaluator；FinalAnswerTrace 是冻结模型，评估器既不接收 state writer，也不调用任何业务工具。

2G-2 继续调用同一个只读 DeterministicEvaluator，并把 EvaluationResult 与冻结 RunTrace 一起持久化和查询。Evaluator 没有数据库 Session、Tool Registry 或 state writer；持久化由 AgentRuntimeService 在评估返回后完成，因此评估器不能修改答案和业务状态。当前仍不是 LLM Evaluator，也不是临床质量评估。

## 6. 3C Runtime Trace 输入适配

`RuntimeTraceAdapter` 是 Runtime API 和既有 `DeterministicEvaluator` 之间的新信任边界。它不会实现第二套评分公式，只负责：递归脱敏敏感键、解析冻结 artifacts、验证 run/task/member 作用域，并把当前 `ExpectedCase.case_id` 投影到新的冻结 RunTrace。

Evaluator 仍只读取 ExpectedCase 与 RunTrace，不接收数据库 Session、HTTP client 或业务写 service。API Guard 的 `404/422` 没有 FinalAnswer，不能伪造成 EvaluationResult；它们由 Runtime Harness 单独汇总。3C JSON 报告排除成员 ID、run ID 和答案正文。

## 7. 3D 演示报告

3D 从 3C Runner 中选择四个面试场景形成固定套件，但不改变评估公式。`MvpDemoRunner` 只把既有 EvaluationResult 和 runtime contract 投影为脱敏的场景摘要；如果任一任务失败、外部状态不是 `not_submitted` 或套件顺序被改变，脚本以非零状态退出。4/4 结果只适用于本地 PostgreSQL seed 与 deterministic provider。

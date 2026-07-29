# Model Gateway 设计

## 1. 职责

Model Gateway 是业务工作流与模型供应商之间的统一边界。它负责：

- 把最小 `ModelCallRequest` 发送给 provider；
- 把 provider 文本解析为调用方指定的 Pydantic schema；
- 对结构化输出执行规则安全检查；
- primary 失败时执行同契约 deterministic fallback；
- 生成不含 Key、完整 prompt 和原始回答的调用 Trace；
- 释放由 Gateway 自己创建的 HTTP client。

它不负责意图规划、RAG 检索、业务工具执行、医疗决策或 post-run 评估。

## 2. 运行时接线

`LangGraphAgentWorkflow` 不再硬编码 deterministic Gateway，而是通过 `create_model_gateway()` 读取 `Settings`：

```text
AgentRuntimeService
  -> LangGraphAgentWorkflow
  -> create_model_gateway(deterministic fallback)
       -> MODEL_PROVIDER=deterministic
            -> DeterministicModelProvider
       -> MODEL_PROVIDER=openai_compatible
            -> OpenAICompatibleModelProvider
            -> deterministic fallback
  -> FinalAnswer Pydantic schema
  -> RuleBasedModelOutputSafetyChecker
  -> ModelCallTrace
```

Runtime 每次运行后在 `finally` 中关闭工作流自有 Gateway。调用方注入的 Gateway 不由工作流关闭，所有权边界因此可预测。

## 3. 请求与响应契约

`ModelCallRequest` 包含 `run_id`、`task_id`、`member_id`、调用目的、最小 messages、温度和输出上限。当前业务工作流只在 FinalAnswer 节点调用模型；Planner、工具、SafetyAgent 和 Evaluator 仍由确定性代码负责。

调用方同时传入目标 Pydantic model。Gateway 按以下顺序处理：

```text
provider raw response
  -> JSON parse
  -> target_schema.model_validate
  -> model output safety check
  -> typed output
```

非 JSON、缺字段、多余字段、错误类型和不安全内容都不能进入最终结构化输出。

## 4. Provider

`DeterministicModelProvider` 不联网，从固定 payload 或本地函数生成 JSON。它用于默认开发模式、测试和 fallback。

`OpenAICompatibleModelProvider` 请求：

```http
POST {MODEL_API_BASE}/chat/completions
Authorization: Bearer {MODEL_API_KEY}
Content-Type: application/json
```

它要求配置真实 `MODEL_API_BASE`、非空 Key 和非默认 `MODEL_NAME`。配置详情见 [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md)。

## 5. 失败与回退

| `error_type` | 触发原因 |
| --- | --- |
| `provider_timeout` | HTTP/provider 超时 |
| `provider_http_error` | 网络失败或非成功 HTTP 状态 |
| `provider_response_invalid` | 缺少 choices/message/content |
| `schema_validation_failed` | 非 JSON 或目标 Pydantic schema 不接受 |
| `safety_check_failed` | 结构正确但命中不安全输出规则 |
| `safety_check_error:<type>` | checker 自身异常 |

任一 primary 失败都会留下 attempt trace，再尝试 fallback。`effective_provider` 只表示最终可用输出来自谁；判断真实模型是否验证成功必须同时看 primary attempt，不能只看整个 Gateway 是否返回了答案。

## 6. SafetyAgent、Gateway Checker 与 Evaluator

- `SafetyAgent`：运行时根据用户请求、成员、动作和证据在动作前拦截风险。
- Gateway checker：模型输出后的确定性文本门禁，防止结构化结果夹带停药、加量、跳过确认等内容。
- `EvaluatorAgent` / deterministic evaluator：答案冻结后的只读质量评估。

三者发生时间、输入和权限不同，不能互相替代。

## 7. 诊断器

`python -m scripts.check_model_provider` 默认只做配置与 deterministic 自检，不发 HTTP。

`python -m scripts.check_model_provider --live` 在配置为 `openai_compatible` 时发送一次结构化非医疗请求。诊断报告只输出“base/key 是否配置”的布尔值，不输出其内容；外部 primary 失败但 fallback 成功时仍返回非零退出码。

## 8. 测试与边界

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_model_gateway.py `
  backend\tests\test_model_provider_diagnostic.py `
  backend\tests\test_langgraph_workflow.py -q
```

测试覆盖 provider HTTP 契约、schema/safety、fallback、诊断退出码、运行时工厂接线、资源所有权和密钥不泄露。MockTransport 测试不能证明任何真实模型的答案质量、成本、安全率或延迟。

## 9. 当前接入与最终模型边界

`FamilyHealthProductWorkflow` 的预问诊、慢病用药和报告解读三条业务分支，在 SafetyAgent、工具调用和确认状态已经确定后，统一调用 Gateway：

```text
business subgraph
  -> safety / tools / confirmation state
  -> compact evidence summary
  -> ModelGateway
  -> WorkflowFinalAnswerDraft
  -> business contract check
  -> final_answer + ModelCallTrace
```

当前实现中，模型只改写最终答案草稿，不能决定业务路由、工具权限、成员、SafetyAgent 结果或确认门。Gateway 输入只包含任务摘要、状态、安全标记、来源数量和模板边界，不传完整 raw conversation 或完整工具输出。

无 Key 时 `MODEL_PROVIDER=deterministic`，三条业务线仍可运行；配置 `openai_compatible` 后，真实 provider 只尝试最终答案，超时、HTTP、JSON、schema 或输出安全失败都会回退 deterministic。业务 API 的 `model_call_trace` 只保存 provider、schema、安全、fallback 和耗时，不保存 Key、完整 prompt 或 provider 原文。

4B 最终允许真实模型参与有限决策，但输出空间必须由调用方固定：Router 只能在 `direct/supervised` 中选择，Planner 只能组合注册步骤，领域 Agent 只能选择白名单工具和结构化说明，Supervisor 只能在计划中尚未完成且依赖满足的角色中选择。所有结果随后还要经过 Pydantic、角色/工具白名单、成员权限、依赖、最大步数和安全规则校验。模型不得发明角色、工具、流程或确认状态。

任务七的新业务链路在 Gateway 候选返回后再次调用 `ThreeLayerSafetyGuard.final_output()`，把结构化答案和危险表达检查结果写入 `final_output_safety`；失败候选不会覆盖用户答案。Gateway 的 output checker、Safety Guard 和 post-run Evaluator 仍是三个不同阶段，不能用模型输出通过 schema 代替运行时安全，也不能用 Evaluator 事后补救。

LLM Judge 不复用运行时 Gateway 做在线决策。若进行实验，只离线读取脱敏冻结产物，其结果不能修改业务状态，也不是最终验收硬门槛。

## 10. 与业务 Provider 的区别

任务九深化的 Medical Document/Pharmacy/Hospital Provider 负责外部业务数据适配，Model Gateway 负责模型推理。两者共享“固定 timeout、有限重试、schema、attempt、fallback”原则，但不能混用：业务 Provider 失败时不得由 LLM fallback 编造库存、科室、报告字段或 SourceRef；Model Gateway 的 deterministic fallback 也不代表业务 Provider 调用成功。

## 11. 任务十模型与 token 可观测字段

`ProviderRawResponse`、`ModelProviderAttemptTrace` 和 `ModelCallTrace` 支持完整的 `input_tokens/output_tokens/total_tokens`。OpenAI-compatible Provider 只在响应 `usage` 同时提供三项且总数一致时记录；缺失或不完整时全部保留为 `null`，`token_usage_available=false`。deterministic provider 不估算 token。

这些计数可以进入白名单 Observation，但消息内容、Provider raw response、Authorization 和 API Key 不能进入。token usage 是调用审计字段，不是模型质量指标，也不能在没有真实 Provider 报告时用于宣称成本或性能。

任务十一三组共享 `deterministic/deterministic-product-answer-v1` 和相同 token 上限。由于 deterministic provider 不返回 usage，所有消融结果保持 `token_usage_available=false`、token/cost 为 `N/A`；Harness 明确拒绝在 usage 缺失时填入合成计数。

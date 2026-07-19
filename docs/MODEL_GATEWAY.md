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

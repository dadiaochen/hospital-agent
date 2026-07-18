# Model Gateway 设计

## 1. 目标与非目标

2F-2 为 Agent 提供统一模型调用边界；2G-1 的 LangGraph FinalAnswer 节点已通过该边界生成结构化答案。调用方不应知道具体 HTTP provider，也不能直接信任模型字符串。Gateway 负责 provider 调用、结构化解析、安全检查、fallback 和 Trace。

本阶段不实现多模型自动路由、模型训练、成本优化、真实线上质量评估、Agent API 或 LangGraph 节点。OpenAI-compatible adapter 只代表 HTTP 契约兼容，不代表已调用某个真实厂商或完成效果验证。

## 2. 请求和输出契约

`ModelCallRequest` 包含：

| 字段 | 用途 |
| --- | --- |
| `run_id` / `task_id` / `member_id` | 把调用归属到当前隔离任务。 |
| `purpose` | 说明本次调用用于规划、草稿还是最终回答。 |
| `messages` | provider 可见的最小消息，不应直接广播完整聊天历史。 |
| `temperature` / `max_output_tokens` | 受 Pydantic 范围限制的生成参数。 |

调用方还必须传入目标 Pydantic model，例如 `PlannerOutput` 或 `FinalAnswerDraft`。Provider 返回文本后，Gateway 用 `json.loads` 和 `response_model.model_validate` 转成结构化对象。未声明字段、缺字段、错误类型和非 JSON 都属于 schema 失败。

## 3. Provider

`ModelProvider` 只暴露 provider name、model name 和 `invoke`。当前有两种实现：

- `DeterministicModelProvider`：从固定 payload 或本地函数产生 JSON，默认测试与 fallback 使用，不联网。
- `OpenAICompatibleModelProvider`：调用配置 base URL 下的 `/chat/completions`，要求 JSON object response。

真实 provider 配置：

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=stored-only-in-local-or-secret-manager
MODEL_NAME=your-model
MODEL_TIMEOUT_MS=10000
```

默认 `.env.example` 使用 `MODEL_PROVIDER=deterministic`，Key 为空。API Key 不进入 request、response、Trace、数据库或提交文件。

## 4. 调用顺序

```text
ModelCallRequest + target Pydantic model
  -> primary provider
  -> JSON parse
  -> target schema validation
  -> model-output safety checker
  -> structured output

any failure
  -> attempt trace
  -> deterministic fallback
  -> same parse/schema/safety gates
  -> output or structured failure
```

只有 schema 和 safety 都通过的对象才会出现在 `ModelCallResult.output`。如果 primary 和 fallback 都失败，`output=None`，调用方应进入人工澄清或安全失败路径，不能使用失败 provider 的原始 content。

## 5. 输出安全与 SafetyAgent

`RuleBasedModelOutputSafetyChecker` 检查解析后的所有字段，当前拦截明显的自行加减量、停换药、跳过确认、自动开方和伪造外部动作成功表达。安全拒绝语句，例如“不能自行停药”，允许通过。

它只是 provider 输出后的确定性门禁。SafetyAgent 仍需在 LangGraph 中结合原始请求、成员上下文、RAG 安全规则、工具证据和动作类型执行运行时安全决策。Gateway checker 不能替代 SafetyAgent，Evaluator 也不能替代二者。

## 6. Trace

每次 provider 尝试生成 `ModelProviderAttemptTrace`：

- provider / model name；
- success、schema_valid、safety_passed；
- safety flags；
- latency；
- 归一化 `error_type`。

`ModelCallTrace` 聚合 requested/effective provider、是否 fallback、fallback reason、总耗时和所有 attempts。当前 Trace 是内存冻结 Pydantic 对象，2G-2 才负责持久化和 API 查询。

## 7. 失败类型

| error type | 说明 |
| --- | --- |
| `provider_timeout` | HTTP 或 provider 超时。 |
| `provider_http_error` | 网络或非成功 HTTP 响应。 |
| `provider_response_invalid` | provider 响应缺少 choices/message/content。 |
| `schema_validation_failed` | 非 JSON 或目标 Pydantic model 不接受。 |
| `safety_check_failed` | 结构正确但命中不安全输出规则。 |
| `safety_check_error:<type>` | safety checker 本身异常。 |

Trace 只记录错误类型，不记录 API Key，也不把失败的原始 prompt/content写入结果。

## 8. 测试

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_model_gateway.py -q --basetemp=.tmp\pytest-model
```

测试使用 deterministic payload、fake provider 和 `httpx.MockTransport`，不会访问网络。通过测试只能说明契约、解析、规则和 fallback 可重复，不能证明真实模型的答案质量、安全率、成本或延迟。

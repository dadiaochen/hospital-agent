# 08：从模型字符串到可信结构化输出

本章建议在完成 06 API 和阅读 07 RAG 后学习。重点不是“怎么发一个 HTTP 请求”，而是为什么业务 Agent 不能直接使用模型返回的字符串。

## 1. 先理解风险

模型可能返回：

- 不是 JSON；
- JSON 缺字段或多出字段；
- 看似结构正确，但包含自行停药或跳过确认的内容；
- 请求超时、HTTP 失败或返回厂商错误格式。

如果 Agent 直接把这些文本写进状态，后面的 Tool、Safety 和 API 都不知道数据是否可信。Model Gateway 的作用就是把不稳定 provider 隔离在固定契约之外。

## 2. 阅读顺序

### 第一步：请求契约

打开 `backend/app/agent/model_gateway_schemas.py`，先读 `ModelMessage` 和 `ModelCallRequest`。注意它们有 `extra="forbid"` 和 `frozen=True`：调用参数创建后不能偷偷增加 API Key、完整聊天历史或任意 provider 参数。

### 第二步：Provider 协议

打开 `backend/app/agent/model_gateway.py` 的 `ModelProvider`。Protocol 描述“对象只要具备这些属性和方法，就能被 Gateway 使用”，因此 deterministic、HTTP provider 和测试 fake 不需要继承同一个基类。

`DeterministicModelProvider` 把固定 dict 序列化为 JSON。它不是 LLM，而是稳定、离线、可断言的测试替身。

### 第三步：HTTP adapter

`OpenAICompatibleModelProvider.invoke` 负责：

1. 从构造配置使用 base URL、Key、model 和 timeout。
2. 把 `ModelMessage` 映射为 HTTP JSON。
3. 请求 JSON object response。
4. 把网络超时和 HTTP 错误转换成统一 provider error。
5. 只提取原始 content，不负责相信或解析业务字段。

API Key 为什么不放进 `ModelCallRequest`：request 会进入 Agent 代码和未来 Trace，Key 属于部署秘密，应该只存在于环境配置和 HTTP adapter 内部。

### 第四步：Gateway attempt

按 `_attempt` 的顺序读：

```text
provider.invoke
-> json.loads
-> response_model.model_validate
-> safety_checker.check
```

任何一步失败都返回 `output=None` 和一条失败 attempt。成功时返回的不是 dict 或字符串，而是调用者声明的 Pydantic 对象。

### 第五步：Fallback

`ModelGateway.invoke` 先执行 primary。失败且配置了不同的 fallback provider 时，再执行一次相同的解析和安全流程。不能因为 fallback 是本地 deterministic 就跳过 schema 或 safety，它们必须遵守同一契约。

## 3. 三种安全角色不要混淆

| 组件 | 时间 | 责任 |
| --- | --- | --- |
| Pydantic | provider 返回后 | 判断结构和字段类型是否合法。 |
| Model output checker | provider 返回后 | 拦截明确越权或伪造动作文本。 |
| SafetyAgent | Agent 工作流运行时 | 结合用户请求、上下文、来源和动作做完整安全判断。 |

EvaluatorAgent 是回答后的质量评估者，不属于上述事前门禁。

## 4. 怎样读测试

打开 `backend/tests/test_model_gateway.py`，不要只看第一个成功测试。依次找到：

- timeout 如何变成 `provider_timeout`；
- 非 JSON 和 Pydantic extra field 如何触发 schema fallback；
- “建议自行停药”为什么失败；
- “不能自行停药”为什么可以作为安全拒绝通过；
- fallback 也失败时为什么没有 output；
- `MockTransport` 为什么可以验证 HTTP 请求而不访问网络。

## 5. 你应该能解释

- Provider、Gateway 和 Agent 节点为什么是三层？
- 为什么 response model 由调用方传入，而不是所有任务共用一个 dict？
- 为什么 primary 与 fallback 必须使用同一 schema 和 safety checker？
- 为什么 Trace 记录 error type，但不记录 API Key？
- MockTransport 测试通过为什么不代表真实模型效果好？

## 6. 简历边界

合入主线后可以表述“设计统一 Model Gateway，以 Pydantic 和规则门禁约束结构化输出，并为 provider 超时、schema/safety 失败实现可追踪 deterministic fallback”。

在没有真实模型评测前，不能声称模型准确率、安全率、成本或 p95 延迟，也不能把 OpenAI-compatible adapter 写成已经接入某个生产厂商。

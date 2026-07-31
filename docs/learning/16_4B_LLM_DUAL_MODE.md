# 16 从零理解 4B LLM 双模式

## 1. 先回答“项目到底有没有调用大模型”

答案不是简单的有或没有，而是分运行模式：

- 默认 `deterministic`：没有外部 LLM HTTP 请求，规则和模板确保项目无 Key 也能稳定运行。
- 可选 `openai_compatible`：真实 LLM 只参与 FinalAnswer 草稿生成，结果仍要过 Pydantic 和 safety gate。

Embedding 模型和 LLM 不是一回事。4A 的 Embedding 把查询与知识块变成向量，用来“找资料”；4B 的 LLM 根据已有任务状态和证据生成结构化回答，用来“组织语言”。

## 2. 为什么需要双模式

如果所有开发、pytest 和 Demo 都强依赖云模型，会遇到 Key 泄露、费用、网络波动、输出不稳定和测试不可重复。完全不用 LLM，又无法学习真实 provider 接入与故障处理。

双模式把两个目标分开：

```text
稳定开发与回归 -> deterministic
真实集成与演示 -> openai_compatible
真实 provider 失败 -> deterministic fallback + 明确 Trace
```

fallback 的目标是服务降级，不是掩盖故障。因此诊断器会把“primary 失败、fallback 成功”判为外部连通性失败。

## 3. 从配置读起

打开 `backend/app/core/config.py`，找到 `Settings` 中的：

```python
model_provider: str
model_api_base: str | None
model_api_key: SecretStr | None
model_name: str
model_timeout_ms: int
```

这里展示了三种技术：

1. Python 类型标注说明允许的数据形状。
2. Pydantic Settings 从环境变量读取并校验配置。
3. `SecretStr` 防止日志或对象打印时直接泄露 Key。

真实值放在根目录 `.env`，示例放在 `.env.example`。代码只依赖 Settings，不在业务文件硬编码供应商。

## 4. 阅读 provider 抽象

打开 `backend/app/agent/model_gateway.py`，按这个顺序读：

### 4.1 `ModelProvider`

它定义 provider 必须提供的最小能力：名称、模型名和 `invoke`。业务代码面向这个接口，而不是面向某个厂商 SDK。

### 4.2 `DeterministicModelProvider`

输入同一请求时，它由固定 payload 或本地函数生成可预测 JSON。它不是“大模型的简化版”，而是测试替身和离线实现。

### 4.3 `OpenAICompatibleModelProvider`

它用 `httpx.Client.post()` 调用 `/chat/completions`。重点看：

- URL 怎样由 base URL 拼接；
- Key 怎样只放进 Authorization header；
- timeout 怎样从毫秒换算；
- 非 2xx、网络异常、响应缺字段怎样转成统一异常；
- client 是外部注入还是内部创建，谁负责关闭。

### 4.4 `ModelGateway.invoke`

它先尝试 primary，再尝试 fallback。每次尝试都经过：provider -> JSON -> Pydantic -> safety。不要只读成功路径，要沿着 `except` 和失败 trace 看完。

### 4.5 `create_model_gateway`

这是配置与具体实现的组装点。`MODEL_PROVIDER=deterministic` 时不会创建 HTTP provider；`openai_compatible` 时缺 base、Key 或真实模型名会立即失败，避免带着半套配置运行。

## 5. 阅读运行时接线

打开 `backend/app/agent/langgraph_workflow.py`：

```python
self.model_gateway = model_gateway or _default_workflow_model_gateway()
```

`or` 左侧表示测试或调用方可以注入 fake；否则走默认工厂。再找 `_default_workflow_model_gateway()`，确认它调用的是 `create_model_gateway()`，而不是直接 `ModelGateway(DeterministicModelProvider(...))`。

这是 review 的关键点：只有配置类和 adapter 并不代表真实运行时会使用它。必须从 API -> Service -> Workflow -> Gateway 追完整条对象创建链。

然后打开 `backend/app/services/agent_runtime_service.py`。它在 `finally` 中关闭工作流，防止真实 HTTP client 在多次请求后积累连接资源。

## 6. 阅读诊断器

`backend/app/agent/model_provider_diagnostic.py` 分三条路径：

1. 配置不完整：不发 HTTP，退出码 2。
2. deterministic：只做本地 schema/safety 自检。
3. openai-compatible：无 `--live` 只检查配置；有 `--live` 才发一次请求。

特别观察：报告只包含 `api_key_configured: bool`，没有 Key 字段。primary 失败时它读取第一次 attempt，而不是被 fallback 的最终成功状态误导。

## 7. 怎样 review 这类代码

固定问十个问题：

1. 未配置 Key 是否完全不联网？
2. Key 是否可能进入 Git、日志、Trace 或异常文本？
3. URL 拼接是否会重复 `/chat/completions`？
4. timeout、HTTP 错误和畸形响应是否归一化？
5. 模型文本是否先经过 JSON 和 Pydantic？
6. 安全检查失败后是否彻底丢弃原始输出？
7. fallback 是否使用同一 schema 和 safety gate？
8. Trace 能否区分 primary 成功与 fallback 成功？
9. HTTP client 的所有者是谁，什么时候关闭？
10. 自动测试是否真的没有访问互联网？

## 8. 怎样自己动手验证

先保持 deterministic，运行：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m scripts.check_model_provider
```

再用 `.env` 填真实 provider，启动 Docker backend，并运行：

```powershell
docker compose exec -T backend python -m scripts.check_model_provider --live
```

最后运行四场景并查看 `model_call_trace`。完整字段与故障恢复见 [LLM 双模式配置](../LLM_CONFIGURATION.md)。

## 9. 面试表达

可以这样回答：

> 我没有让项目强依赖云模型，而是设计了统一 Model Gateway。默认 deterministic provider 保证测试和演示可重复，配置 OpenAI-compatible provider 后，LangGraph 的 FinalAnswer 节点才发出真实 HTTP 请求。模型结果必须通过 JSON、Pydantic schema 和规则安全门禁；超时、HTTP、schema 或 safety 失败会留下逐次 Trace 并回退。本地诊断器还能区分“真实 primary 成功”和“只是 fallback 成功”。

记忆口诀：**配、调、验、拦、退、记、关**。

- 配：环境变量配置；
- 调：统一 provider 调用；
- 验：JSON + Pydantic；
- 拦：输出安全门禁；
- 退：deterministic fallback；
- 记：脱敏 Trace；
- 关：关闭自有 HTTP client。

## 10. 当前没有证明的内容

没有真实 Key 就没有真实 provider 报告。MockTransport 证明的是 HTTP 契约与失败处理，不是模型质量。不要把它描述为真实模型准确率、医疗安全率、成本或线上延迟。

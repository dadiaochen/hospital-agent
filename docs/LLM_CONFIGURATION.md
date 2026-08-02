# LLM 双模式配置与验证

## 1. 当前结论

项目现在支持两种模型模式，但默认仍然不依赖外部 LLM：

| 模式 | 是否联网 | 是否需要 Key | 用途 |
| --- | --- | --- | --- |
| `deterministic` | 否 | 否 | 本地学习、测试、一键演示和稳定回归 |
| `openai_compatible` | 是 | 是 | 用真实模型生成结构化 FinalAnswer 草稿 |

未填写 Key 不会影响项目启动。Planner、工具调用、RAG、安全判断、确认门和 Evaluator 仍是确定性代码；当前真实 LLM 只替换 FinalAnswer 节点的文本生成，不能直接操作数据库、调用业务工具或绕过 SafetyAgent。

## 2. 配置文件在哪里

唯一需要填写的本机文件是仓库根目录：

```text
E:\project_code\hospital\.env
```

`.env` 已被 Git 忽略，不应提交。`.env.example` 只保存无密钥模板。

若 `.env` 不存在：

```powershell
Set-Location E:\project_code\hospital
Copy-Item .env.example .env
```

## 3. 保持离线默认模式

不想调用 LLM 时保持：

```env
MODEL_PROVIDER=deterministic
MODEL_API_BASE=
MODEL_API_KEY=
MODEL_NAME=deterministic-local
MODEL_TIMEOUT_MS=10000
```

此时前端、FastAPI、四场景 Demo 和全部自动化测试都不发出模型 HTTP 请求。

## 4. 接入 OpenAI-compatible 模型

把根目录 `.env` 中五项改成供应商真实值：

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=your-real-key
MODEL_NAME=your-real-model-name
MODEL_THINKING_MODE=disabled
MODEL_TIMEOUT_MS=10000
MODEL_INPUT_PRICE_PER_1M_USD=0.15
MODEL_OUTPUT_PRICE_PER_1M_USD=0.60
```

字段含义：

| 字段 | 说明 | 常见错误 |
| --- | --- | --- |
| `MODEL_PROVIDER` | 选择适配器 | 必须是 `deterministic` 或 `openai_compatible` |
| `MODEL_API_BASE` | API 根地址，通常写到 `/v1` | 不要再加 `/chat/completions` |
| `MODEL_API_KEY` | 本机密钥 | 不要填进 `.env.example`、代码、截图或 Git |
| `MODEL_NAME` | 供应商实际模型 ID | 不能继续使用 `deterministic-local` |
| `MODEL_THINKING_MODE` | `default`、`disabled` 或 `enabled` | DeepSeek 结构化最终答案建议使用 `disabled`，不要把 `reasoning_content` 当用户答案 |
| `MODEL_TIMEOUT_MS` | 单次 HTTP 超时毫秒数 | 过短容易触发 fallback |
| `MODEL_INPUT_PRICE_PER_1M_USD` | 输入 token 每百万的价格 | 不填则 cost 为 `N/A` |
| `MODEL_OUTPUT_PRICE_PER_1M_USD` | 输出 token 每百万的价格 | 不填则 cost 为 `N/A` |

这里的“OpenAI-compatible”描述的是 HTTP 请求格式，不限定某个厂商。供应商必须支持 `POST {base_url}/chat/completions`，并能返回 JSON object 内容。

## 5. Docker 与宿主机 URL

云服务 URL 可直接写公网 HTTPS 地址。本机模型服务从 Docker backend 访问时，不能写 `localhost`，因为容器中的 `localhost` 指向容器自己。

例如本机 Ollama 开放 OpenAI-compatible 接口时可以尝试：

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=http://host.docker.internal:11434/v1
MODEL_API_KEY=ollama-local
MODEL_NAME=qwen2.5:1.5b
MODEL_TIMEOUT_MS=30000
```

这只是兼容配置示例，不代表本项目已经对该模型做过真实质量评测。模型是否存在、Ollama 是否允许容器访问，仍需在本机确认。

## 6. 三层验证

### 6.1 无网络配置检查

默认模式：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m scripts.check_model_provider
```

Docker 模式：

```powershell
docker compose exec -T backend python -m scripts.check_model_provider
```

不带 `--live` 时绝不调用外部 HTTP。它只检查配置是否完整，并运行 deterministic schema/safety 自检。

### 6.2 真实连通性检查

确认 `.env` 已填好并重建 backend 后：

```powershell
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.check_model_provider --live
```

`--live` 只发送一次非医疗、结构化连通性请求。成功的关键字段是：

```json
{
  "external_call_performed": true,
  "primary_provider_verified": true,
  "fallback_used": false,
  "effective_provider": "openai_compatible",
  "schema_valid": true,
  "safety_passed": true
}
```

退出码含义：

| 退出码 | 含义 |
| --- | --- |
| `0` | 本地模式正常，或真实 primary 调用成功 |
| `1` | 已调用外部 provider，但 primary 失败；即使 fallback 成功也会报告失败 |
| `2` | 配置无效或 deterministic 自检失败 |

### 6.3 业务链验证

连通性通过后运行固定四场景：

```powershell
.\scripts\run_demo.ps1
```

在 Runtime artifacts 的 `model_call_trace` 中确认：

- `requested_provider` 是 `openai_compatible`；
- `effective_provider` 是 `openai_compatible`；
- `fallback_used=false`；
- attempt 的 `schema_valid` 和 `safety_passed` 都为 true。

连通性成功不等于回答质量、安全率或医疗有效性已经验证。真实质量仍需专门用例和报告。

4D-B3 的真实模型评测必须显式加入 `--live`：

```powershell
python scripts/run_4d_b3_real_llm.py `
  --live `
  --identity-map var/demo/v2_identity_map.local.json `
  --max-cases 1 `
  --split development `
  --allow-pending-review
```

不加入 `--live` 时只生成 blocked/readiness 报告，不访问外部模型。第一次真实运行只允许使用 1 个 case，确认 provider、fallback、usage 和安全检查后再扩大样本。

## 7. 失败时发生什么

外部 provider 超时、HTTP 错误、返回格式错误、Pydantic 校验失败或命中输出安全规则时：

1. Gateway 记录失败 attempt 和归一化 `error_type`；
2. 丢弃失败 provider 的原始结果；
3. 调用同一输出契约的 deterministic fallback；
4. fallback 也必须经过 schema 与 safety 检查；
5. Trace 明确记录 `fallback_used=true`，不能伪装成真实模型成功。

API Key、完整 prompt 和 provider 原始文本不会进入审计 artifact。

## 8. 恢复离线模式

把 `.env` 改回第 3 节的五项，然后重建 backend：

```powershell
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.check_model_provider
```

报告应显示 `configured_provider=deterministic`、`external_call_performed=false` 和 `deterministic_self_check_passed=true`。

## 9. 当前验证边界

- 自动化测试使用 `httpx.MockTransport` 验证 URL、结构化响应、失败回退和密钥不泄露，不访问真实厂商。
- 2026-07-20 已在无 Key 模式通过 196 条后端测试、compileall、Docker 四项 healthcheck 和固定四场景 4/4；容器诊断确认没有外部调用。
- 仓库没有用户的真实 API Key，因此尚未形成任何真实 LLM 的效果、成本、延迟或安全指标。
- B3 runner 已实现真实 usage、fallback、模型延迟、工作流 p95 和成本聚合；当前没有真实 Key/报告，相关值仍为 `N/A`。
- 简历可以写“实现 OpenAI-compatible / deterministic 双模式 Model Gateway 和可复现诊断”，不能写“某模型已达到某准确率或 p95”。

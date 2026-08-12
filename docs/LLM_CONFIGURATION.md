# 业务模型与独立评估模型配置

## 1. 当前结论

项目支持两套职责隔离的模型配置。这里的“两套模型”指模型角色和配置独立，不强制购买两个服务商账号：

| 模型角色 | 环境变量前缀 | 用途 | 是否进入业务链路 |
| --- | --- | --- | --- |
| 目标回答模型 | `MODEL_*` | 生成用户最终回答 | 是 |
| 独立 Judge | `RAGAS_JUDGE_*` | 对冻结回答做 RAGAS 离线评分 | 否 |

如果同一服务商和同一个 Key 能访问两个模型，两套配置可以填写相同的 Base URL 和 API Key，但 `MODEL_NAME` 与 `RAGAS_JUDGE_MODEL` 必须不同。如果使用不同服务商，则分别填写各自的 Base URL、Key 和模型名。

目标回答模型仍支持两种运行模式，默认不依赖外部 LLM：

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

## 4. 接入目标回答模型

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

## 5. 配置独立 RAGAS Judge

在同一个 `.env` 中填写第二组变量：

```env
RAGAS_ENABLED=true
RAGAS_VERSION=0.2.9
RAGAS_JUDGE_API_BASE=https://your-judge-provider.example/v1
RAGAS_JUDGE_API_KEY=your-judge-key
RAGAS_JUDGE_MODEL=your-independent-judge-model
RAGAS_JUDGE_THINKING_MODE=disabled
RAGAS_EMBEDDING_PROVIDER=fastembed
RAGAS_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAGAS_BATCH_SIZE=16
RAGAS_MAX_WORKERS=8
RAGAS_TIMEOUT_SECONDS=60
```

Judge 当前使用 OpenAI-compatible 接口。`RAGAS_JUDGE_API_BASE` 通常写到 `/v1`，不要追加 `/chat/completions`。`RAGAS_JUDGE_THINKING_MODE=disabled` 会通过兼容接口传递 `enable_thinking=false`，避免 Qwen Judge 为短评分请求产生大量隐藏思考 token；不支持该扩展的服务商可设为 `default`。使用本地 FastEmbed 时，Embedding 不消耗 Judge API token；RAGAS 失败、余额不足或超时只会把对应指标记为不可用，不会阻断业务回答。默认 16 条 batch、8 路 Judge 并发；若供应商出现 429 或超时，可将 `RAGAS_MAX_WORKERS` 降为 4。

RAGAS 只复用已冻结的回答、检索来源与 Gold，不重跑目标回答模型或 Embedding/HNSW。本轮最终组合的 Judge 调用因账户计费不可用没有返回可解析分数；Faithfulness、Response Relevancy 与 Context Recall 必须记为 N/A，不能写为 0，也不影响检索和确定性来源绑定指标。恢复 Judge 后可直接运行冻结复评命令补分。

推荐的两种填写方式：

| 场景 | Base URL / Key | 模型名 |
| --- | --- | --- |
| 同一账号、不同模型 | 两组可填相同值 | 必须不同 |
| 不同服务商或账号 | 两组分别填写 | 必须不同 |

代码会分别读取两组字段，且在 Judge 模型名与目标模型名相同时拒绝评分，防止自评。密钥使用 `SecretStr` 保存，不会出现在配置对象的日志表示中。

## 6. Docker 与宿主机 URL

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

## 7. 三层验证

### 7.1 无网络配置检查

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

### 7.2 真实连通性检查

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

### 7.3 业务链验证

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
  --concurrency 4 `
  --split development `
  --allow-pending-review
```

不加入 `--live` 时只生成 blocked/readiness 报告，不访问外部模型。第一次真实运行只允许使用 1 个 case，确认 provider、fallback、usage 和安全检查后再扩大样本。

## 8. 失败时发生什么

外部 provider 超时、HTTP 错误、返回格式错误、Pydantic 校验失败或命中输出安全规则时：

1. Gateway 记录失败 attempt 和归一化 `error_type`；
2. 丢弃失败 provider 的原始结果；
3. 调用同一输出契约的 deterministic fallback；
4. fallback 也必须经过 schema 与 safety 检查；
5. Trace 明确记录 `fallback_used=true`，不能伪装成真实模型成功。

API Key、完整 prompt 和 provider 原始文本不会进入审计 artifact。

## 9. 恢复离线模式

把 `.env` 改回第 3 节的五项，然后重建 backend：

```powershell
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.check_model_provider
```

报告应显示 `configured_provider=deterministic`、`external_call_performed=false` 和 `deterministic_self_check_passed=true`。

## 10. 当前验证边界

- 自动化测试使用 `httpx.MockTransport` 验证 URL、结构化响应、失败回退和密钥不泄露，不访问真实厂商。
- 2026-07-20 已在无 Key 模式通过 196 条后端测试、compileall、Docker 四项 healthcheck 和固定四场景 4/4；容器诊断确认没有外部调用。
- `.env` 中的真实 Key 只保存在本机且被 Git 忽略；仓库文档和测试只使用空值或假密钥。
- 真实模型效果、成本、延迟和 RAGAS 指标统一以 [RAG 合成评测统一报告](RAG_SYNTHETIC_EVALUATION_DATASET.md) 中的冻结实测结果为准。
## Agent 评测规模

真实 LLM Agent 评测默认读取统一数据集的 fast-400 活动视图（100 个 WorldState、400 条 Query，development/validation/holdout 为 240/80/80）。本次先用 3 条 Query 做链路冒烟，再按 40 条可恢复批次完成各 split；完整 1,200 条来源已留档，不作为默认付费评测输入。后续复测默认用 `--concurrency 4` 并行独立 Query；每条仍使用独立 PostgreSQL 事务，报告按冻结顺序写入。当前 400 条自动全量已完成，并按冻结业务 Gold 自动评分：意图、路由、工具、参数和最终回答正确率均为 100%，端到端任务成功率 99.25%，真实 Provider/完整 usage 覆盖率 69.25%，fallback 0.75%，端到端 P50/P95/P99 为 4,294/6,645/7,850 ms；不设人工复核门。

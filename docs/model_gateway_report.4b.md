# 4B Model Gateway 验证报告

验证日期：2026-07-20  
环境：Windows + Docker Desktop + PostgreSQL/Redis/FastAPI/Next.js  
默认 provider：`deterministic`

## 1. 自动化结果

```text
focused: 47 passed, 2 warnings
backend full: 196 passed, 2 warnings
compileall: passed
```

两项 warning 分别来自 FastAPI TestClient/httpx 迁移提示和 LangGraph serializer 默认值的 pending deprecation，不是 4B 失败。

MockTransport 覆盖：

- OpenAI-compatible URL 与 JSON response 契约；
- 配置检查不发 HTTP；
- 显式 live primary 成功；
- provider 503 时 fallback 成功但诊断退出码仍为失败；
- 缺 base/Key/真实模型名时不调用外部服务；
- 报告不包含 Key；
- Runtime 默认工作流使用环境感知工厂；
- 工作流只关闭自己创建的 Gateway。

## 2. Docker 无 Key实跑

使用根目录 `.env.example` 默认值重建 Compose：

```text
MODEL_PROVIDER=deterministic
MODEL_API_BASE=
MODEL_API_KEY=
MODEL_NAME=deterministic-local
```

结果：PostgreSQL、Redis、backend、frontend 四个容器全部 healthy。固定四场景：

```text
父亲降压药续方          PASS
母亲中医复诊材料        PASS
母亲用药提醒草稿        PASS
高风险加量请求拦截      PASS
合计                    4/4
```

容器内诊断关键字段：

```json
{
  "configured_provider": "deterministic",
  "configuration_valid": true,
  "api_key_configured": false,
  "external_call_performed": false,
  "deterministic_self_check_passed": true,
  "effective_provider": "deterministic",
  "schema_valid": true,
  "safety_passed": true
}
```

这证明 4B 没有破坏无 Key 模式和固定本地演示。

## 3. 尚未验证

仓库没有真实厂商 Key，因此没有执行真实 `--live` provider 调用，也没有真实 LLM 四场景质量、成本、Token、延迟或安全指标。

用户填好本地 `.env` 后，验收命令是：

```powershell
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.check_model_provider --live
```

只有 `primary_provider_verified=true` 才能记录为真实 provider 连通成功。完整操作见 [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md)。

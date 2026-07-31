# 4C 浏览器 E2E 验收报告

## 1. 范围

本报告记录 4C-3 的本机浏览器验收。测试访问 Docker Compose 提供的 Next.js `http://localhost:3000`，前端再通过真实 HTTP 请求访问 FastAPI `http://localhost:8000`。backend 使用 `MODEL_PROVIDER=deterministic`，不调用真实 LLM、医院、药店或通知系统。

## 2. 执行方式

```powershell
Set-Location E:\project_code\hospital
docker compose ps
Set-Location frontend
$env:E2E_BROWSER_CHANNEL='msedge'
npm run test:e2e
```

测试使用本机已经安装的 Microsoft Edge，避免额外下载浏览器二进制。Playwright 配置保留失败截图和 trace，测试报告写入被 Git 忽略的 `var/`。

## 3. 结果

| 类别 | 场景 | 结果 |
| --- | --- | --- |
| 续方 | 首次 run 进入 `DRAFT`，未确认不推进 | PASS |
| 续方 | 确认后产生 continuation run 和本地草稿 | PASS |
| 用药提醒 | 确认后完成本地提醒草稿 | PASS |
| 复诊材料 | 保留来源、安全和 task 标识 | PASS |
| 安全 | 高风险加量请求进入 `BLOCKED`，无确认按钮 | PASS |
| 隔离 | 切换 `member_id` 后清理前一成员结果 | PASS |
| 失败 | API 503 映射为可读错误且不伪造答案 | PASS |

**本机结果：7 passed，5.2s。** 这是固定 deterministic Docker 演示链路的可重复性证据，不是线上可用性、临床安全率、真实模型质量或生产 p95 延迟指标。

## 4. 非目标

- 不验证真实 LLM provider 的质量或稳定性。
- 不验证真实医院、药店、支付、通知写入。
- 不把 route mock 的 503 场景解释成真实 Provider 故障率。
- 不在浏览器中修改 FinalAnswer、RunTrace、RunSummary 或 EvaluationResult。

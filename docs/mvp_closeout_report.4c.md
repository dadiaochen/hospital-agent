# 4C-4 MVP 收口报告

## 1. 范围

本报告记录 4C-4 的本机最终收口。项目仍是本地 deterministic MVP，未接入真实医院、药店、支付、通知或生产用户；结果不能解释为临床安全、真实 LLM 质量或生产 SLO。

## 2. 一键命令

```powershell
Set-Location E:\project_code\hospital
.\scripts\closeout_4c.ps1
```

脚本要求 Docker Desktop、项目 `.venv`、`frontend/node_modules` 和 Windows Edge 已准备好。运行时的脱敏 JSON/Markdown 写入被 Git 忽略的 `var\closeout\`。

## 3. 本次结果

执行日期：2026-07-30（Asia/Shanghai）。

| 验收步骤 | 结果 | 证据 |
| --- | --- | --- |
| Docker 构建、启动、migration、seed | PASS | PostgreSQL、Redis、backend、frontend healthy |
| 固定四场景 Runtime Demo | PASS | `4/4`，续方/复诊材料/提醒均完成确认续跑，高风险请求保持 `BLOCKED` |
| 外部副作用边界 | PASS | 四个场景均为 `external_action_status=not_submitted` |
| backend/frontend HTTP smoke | PASS | backend `/health=200`，frontend `/=200` |
| deterministic Agent Harness | PASS | `docs/agent_eval_report.example.md` |
| Single Agent / fixed router / bounded Supervisor 消融 | PASS | `output/agent_ablation_report.4b.json` |
| 浏览器 E2E | PASS | Playwright + Edge，`7 passed` |
| backend 全量回归 | PASS | 项目 `.venv`，`297 passed` |
| Python 编译检查 | PASS | `compileall` 使用 `output/pycache-4c-compile` 隔离输出 |

## 4. 设计边界

- 一键脚本只编排已有能力，不新增业务 Agent、API 或数据库表。
- Harness 和消融 fixture 在宿主机离线运行，不进入 backend 生产镜像。
- 浏览器测试验证真实 Docker 前后端契约；API 失败场景的 503 是浏览器 route mock，不代表真实 Provider 故障率。
- 当前结果属于本地集成/演示环境证据，不代表生产部署、真实模型质量、临床安全或用户采纳率。

## 5. 后续工作

4C 之后不再新增必要产品阶段。后续工作应作为独立工程任务管理：真实 Provider/LLM 联调、生产认证与秘密管理、依赖漏洞治理、外部系统写入、监控和部署准备。

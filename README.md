# 互联网医院慢病续方与家庭用药管理 Agent

一个用于本地演示的家庭健康事务管理 Agent MVP。它帮助用户整理续方和复诊材料、查看家庭药箱与药店库存、创建待确认的提醒或方案草稿，并对高风险医疗请求做安全拦截。

> 这不是 AI 医生，也不是生产医疗系统。系统不做疾病诊断、自动开方、处方修改或剂量调整；任何复诊、购药和提醒动作都必须经过人工确认，且当前只写入本地草稿，不会提交医院、药店或推送服务。

## 当前状态

项目已按 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 完成 `3D`，达到本仓库定义的本地演示级 **MVP Complete**。当前没有已定义的后续阶段；新增产品范围前必须先更新唯一总路线图。

目前已经具备：

- SQLAlchemy / Alembic 数据模型、可重复 seed 数据和后端测试。
- Pydantic Context、Trace、Tool 和 Evaluation 契约。
- ContextManager 的角色最小视图、上下文压缩与 run 后 reset。
- deterministic Tool Registry、固定 Harness 用例、可重复的评估和 Markdown 报告。
- 数据库只读查询工具，以及只创建本地 draft 的确认门禁工具。
- 家庭、药箱、处方/购药、药店库存、知识检索与 Agent 审计的只读 FastAPI 接口；知识检索已完成自动化与 PostgreSQL/Postman 验证。
- 本地草稿创建、查询、确认和拒绝 API；状态机只改变本地记录，始终保留 `not_submitted` 外部状态。
- Hybrid RAG：关键词检索始终可用，可选向量后端只返回来源指针，异常时留下原因并自动回退。
- Model Gateway：默认 deterministic，可选真实 HTTP provider；所有输出先过 Pydantic 与安全检查，失败留下 attempt trace 并回退。
- 有界 LangGraph DAG：按 intent 路由四类业务角色，统一经过 ContextManager、Tool Registry、SafetyAgent、确认草稿、RunTrace/reset 和只读 Evaluator。
- Agent Runtime API：真实 DB tools、run/tool-call 持久化、冻结产物查询、幂等运行和确认后的同任务续跑；任何动作仍只创建本地草稿。
- Next.js 数据页面与 Agent 演示入口：共享成员选择、四类场景、Tool/RAG 来源、安全提示、确认续跑和 Trace/Evaluation 详情。
- Runtime E2E Harness：从 FastAPI 外部驱动 7 条 Trace 和 2 条 API Guard，将真实冻结产物经脱敏 adapter 交给独立 Evaluator，并生成 JSON/Markdown 报告。
- 一键演示交付：Compose 自动执行 migration 与幂等 seed，production-mode Next.js 和 FastAPI 通过 healthcheck 后运行固定四场景，并生成不含成员/run ID 或答案正文的脱敏报告。

## 四个演示场景

1. 父亲降压药的续方材料整理。
2. 母亲中医复诊材料整理。
3. 母亲用药提醒草稿与本地确认。
4. 加量、减量、停药、换药等高风险请求的安全拦截。

## 架构一览

```text
FastAPI / Frontend
        |
   Services <-> SQLAlchemy Models <-> PostgreSQL
        |
LangGraph -> ContextManager -> role view -> Tool Registry / RAG
    |              |                           |
 Planner       member isolation          evidence pointers
    |                                          |
SafetyAgent -> confirmation gate -> Model Gateway -> FinalAnswer
                       |                           |
                local draft only       RunTrace -> reset -> Evaluator
                       \                   /
                        AgentRuntimeService
                     -> agent_runs / tool_calls
```

业务 Agent 只能使用带 Pydantic 输入输出契约、角色权限、超时、重试和确认标记的工具。事实必须能回溯到数据库工具或 RAG 来源；没有来源时不能编造病史、处方、库存或医疗规则。

## 快速开始

第一次运行请先阅读 [MVP 演示手册](docs/DEMO_RUNBOOK.md) 和 [本地环境、启动与部署指南](docs/LOCAL_SETUP_AND_DEPLOYMENT.md)。Windows 下一键构建、初始化、启动并跑四场景：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_demo.ps1
```

只启动服务也可直接执行 `docker compose up --build`；Compose 没有 `.env` 时使用 deterministic 本地默认值。

启动后可访问：

- 前端：`http://localhost:3000`
- API 文档：`http://localhost:8000/docs`
- 服务健康检查：`http://localhost:8000/health`

只重新运行固定四场景：

```powershell
.\scripts\run_demo.ps1
```

报告写到本地 `var\demo\`。2026-07-19 在全新 Docker PostgreSQL volume、seed 数据和 deterministic provider 上实跑为 4/4 场景通过：三条正常业务均先等待确认再完成本地草稿，高风险加量请求保持阻断，所有结果的外部动作状态均为 `not_submitted`。可提交的脱敏快照见 [3D MVP 演示报告](docs/mvp_demo_report.3d.md)。

默认 `RAG_VECTOR_ENABLED=false`，使用 PostgreSQL 关键词检索并保留 document/chunk/version/source 指针，没有调用 Embedding 模型。默认 `MODEL_PROVIDER=deterministic`，问答由规则/模板生成，不调用真实 LLM；项目已有可选 OpenAI-compatible provider、schema/safety 校验和 deterministic fallback，Key 只能配置在未提交的本机 `.env`。完整区别见 [MVP 演示手册](docs/DEMO_RUNBOOK.md#5-rag-与模型模式)。

运行后端测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest\all
python -m compileall backend\app backend\tests
```

只验证草稿 API：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_confirmation_draft_api.py backend\tests\test_confirmation_draft_tool.py -q
```

只验证 2F-1 Retriever：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q --basetemp=.tmp\pytest-rag
```

只验证 2F-2 Model Gateway：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_model_gateway.py -q --basetemp=.tmp\pytest-model
```

只验证 2G-1 LangGraph 工作流：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_langgraph_workflow.py backend\tests\test_context_manager.py -q -p no:cacheprovider --basetemp=.tmp\pytest-workflow
```

只验证 2G-2 Agent Runtime API：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_agent_runtime_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-runtime
```

验证 3A/3B 前端：

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

运行 3C Runtime Harness（先启动并 seed Docker 环境）：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.runtime_harness `
  --base-url http://localhost:8000 `
  --environment local_postgresql_deterministic `
  --run-key-prefix "3c-$((Get-Date).ToString('yyyyMMddHHmmss'))"
```

2026-07-19 的固定本地 PostgreSQL + deterministic provider 报告覆盖 7 条 Trace 和 2 条 Guard，记录的 p95 冻结 Trace latency 为 18 ms。该结果只属于本地 seed 与固定规则，不是生产、临床或真实 LLM 指标。

只验证 3D 固定演示契约：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_mvp_demo_runner.py -q `
  -p no:cacheprovider --basetemp=var\pytest\3d
```

## 实现边界与已知限制

- 当前是本地开发/集成演示环境，不是生产部署；没有 JWT/OAuth、真实患者流量、HTTPS、秘密管理、高可用、SLA 或生产监控。
- 不接真实医院、医生、处方、药店、支付、物流或提醒推送；确认只写本地草稿。
- 默认没有真实 LLM 和 Embedding/向量数据库；OpenAI-compatible provider 尚未形成真实质量报告，向量后端只有注入协议与降级规则。
- 固定 Harness 和 3D 的 4/4 只证明当前 seed + deterministic 规则的回归结果，不能外推为临床安全率、线上幻觉率或服务 SLO。
- 2026-07-19 的 `npm audit --omit=dev` 对 Next 14 生产依赖仍报告 1 项 high 和 1 项 moderate；官方自动修复涉及 Next 16 major upgrade，应在生产化前独立升级并做完整回归。

## 文档入口

从 [docs 文档导航](docs/README.md) 开始。它区分了产品、开发、技术、接口、数据库、Agent 和学习材料。

常用入口：

- [总开发路线图](docs/DEVELOPMENT_ROADMAP.md)：阶段状态、顺序和 MVP 验收的唯一权威来源。
- [开发者指南](docs/DEVELOPER_GUIDE.md)：环境、命令、分支、测试与提交流程。
- [MVP 演示手册](docs/DEMO_RUNBOOK.md)：一键启动、固定四场景、UI 顺序、RAG/模型模式和排错。
- [技术设计](docs/TECH_DESIGN.md)：分层边界、数据流与当前实现边界。
- [接口文档](docs/API_SPEC.md)：已实现接口与后续接口契约边界。
- [Agent 工作流](docs/AGENT_WORKFLOW.md)：角色、工具、确认与安全流程。
- [RAG 检索设计](docs/RAG_RETRIEVAL.md)：Retriever 契约、来源回填、混合检索和降级规则。
- [Model Gateway 设计](docs/MODEL_GATEWAY.md)：provider 契约、结构化输出、安全检查和 fallback trace。
- [LangGraph 工作流](docs/LANGGRAPH_WORKFLOW.md)：图节点、条件路由、状态、确认门和运行产物。
- [Agent Runtime API](docs/AGENT_RUNTIME_API.md)：运行入口、持久化、冻结回放、幂等与确认续跑。
- [前端架构](docs/FRONTEND_ARCHITECTURE.md)：成员切换、API 客户端、页面状态和跨成员防线。
- [Agent UI 与 Trace](docs/AGENT_UI.md)：对话提交、本地确认、冻结产物和审计详情页面。
- [Runtime E2E Harness](docs/RUNTIME_E2E_HARNESS.md)：真实 API Trace、脱敏 adapter、Guard、指标和报告运行方式。
- [3D 交付学习章](docs/learning/14_3D_MVP_DELIVERY.md)：从零理解 Docker 初始化链、固定 Demo Runner、关键词 RAG 与真实 LLM 接入边界。
- [从零学习路线](docs/learning/README.md)：需求拆解、代码设计、review 和简历表达。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、services、tools、agent 与测试
frontend/      Next.js 页面与组件
docs/          面向协作者的项目文档和学习材料
backend/alembic/ 数据库迁移
scripts/       可重复 seed、一键启动/停止与固定演示脚本
AGENTS.md      AI Coding Harness 规则
```

## 贡献方式

从最新 `main` 创建一个只对应单一目标的 `codex/...` 分支。完成最小实现、测试和文档同步后再 review、合并与推送。当前路线图没有后续阶段；若要扩展范围，先在 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 中定义，而不是在 README 临时编号。

项目亮点和简历表达边界见 [RESUME_NOTES.md](docs/RESUME_NOTES.md)。

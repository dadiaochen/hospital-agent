# 互联网医院慢病续方与家庭用药管理 Agent

一个用于本地演示的家庭健康事务管理 Agent MVP。它帮助用户整理续方和复诊材料、查看家庭药箱与药店库存、创建待确认的提醒或方案草稿，并对高风险医疗请求做安全拦截。

> 这不是 AI 医生，也不是生产医疗系统。系统不做疾病诊断、自动开方、处方修改或剂量调整；任何复诊、购药和提醒动作都必须经过人工确认，且当前只写入本地草稿，不会提交医院、药店或推送服务。

## 当前状态

项目已完成至 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 的 `2D-2`，`2E-1` 基础读取 API 正在学习分支中收口。本隔离工作区按线性提交提前准备了 `2E-2` 草稿与确认 API、`2F-1` Hybrid RAG、`2F-2` Model Gateway、`2G-1` LangGraph 工作流、`2G-2` Agent Runtime API 和 `3A` 核心数据页面；在 2E-1 完成、rebase 和完整回归之前，不改变路线图状态，也不视为已进入主线。

目前已经具备：

- SQLAlchemy / Alembic 数据模型、可重复 seed 数据和后端测试。
- Pydantic Context、Trace、Tool 和 Evaluation 契约。
- ContextManager 的角色最小视图、上下文压缩与 run 后 reset。
- deterministic Tool Registry、固定 Harness 用例、可重复的评估和 Markdown 报告。
- 数据库只读查询工具，以及只创建本地 draft 的确认门禁工具。
- 家庭、药箱、处方/购药、药店库存与 Agent 审计的只读 FastAPI 接口；知识库搜索保留为学习实战题。
- 隔离分支中的本地草稿创建、查询、确认和拒绝 API；状态机只改变本地记录，始终保留 `not_submitted` 外部状态。
- 隔离分支中的 Hybrid RAG：关键词检索始终可用，可选向量后端只返回来源指针，异常时留下原因并自动回退。
- 隔离分支中的 Model Gateway：默认 deterministic，可选真实 HTTP provider；所有输出先过 Pydantic 与安全检查，失败留下 attempt trace 并回退。
- 隔离分支中的有界 LangGraph DAG：按 intent 路由四类业务角色，统一经过 ContextManager、Tool Registry、SafetyAgent、确认草稿、RunTrace/reset 和只读 Evaluator。
- 隔离分支中的 Agent Runtime API：真实 DB tools、run/tool-call 持久化、冻结产物查询、幂等运行和确认后的同任务续跑；任何动作仍只创建本地草稿。
- 隔离分支中的 Next.js 数据页面：共享成员选择器、家庭档案、药箱、续方/复诊、提醒、购药信息、知识检索和 Agent run 列表，统一处理 loading、empty、error 与跨成员响应拒绝；知识页等待 2E-1 API 合入后做真实联调。

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

完整开发说明见 [开发者指南](docs/DEVELOPER_GUIDE.md)。最短的 Docker 启动方式如下：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

启动后可访问：

- 前端：`http://localhost:3000`
- API 文档：`http://localhost:8000/docs`
- 服务健康检查：`http://localhost:8000/health`

运行后端测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

只验证隔离分支的草稿 API：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_confirmation_draft_api.py backend\tests\test_confirmation_draft_tool.py -q
```

只验证隔离分支的 2F-1 Retriever：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q --basetemp=.tmp\pytest-rag
```

只验证隔离分支的 2F-2 Model Gateway：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_model_gateway.py -q --basetemp=.tmp\pytest-model
```

只验证隔离分支的 2G-1 LangGraph 工作流：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_langgraph_workflow.py backend\tests\test_context_manager.py -q -p no:cacheprovider --basetemp=.tmp\pytest-workflow
```

只验证隔离分支的 2G-2 Agent Runtime API：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_agent_runtime_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-runtime
```

验证隔离分支的 3A 前端：

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

## 文档入口

从 [docs 文档导航](docs/README.md) 开始。它区分了产品、开发、技术、接口、数据库、Agent 和学习材料。

常用入口：

- [总开发路线图](docs/DEVELOPMENT_ROADMAP.md)：阶段状态、顺序和 MVP 验收的唯一权威来源。
- [开发者指南](docs/DEVELOPER_GUIDE.md)：环境、命令、分支、测试与提交流程。
- [技术设计](docs/TECH_DESIGN.md)：分层边界、数据流与当前实现边界。
- [接口文档](docs/API_SPEC.md)：已实现接口与后续接口契约边界。
- [Agent 工作流](docs/AGENT_WORKFLOW.md)：角色、工具、确认与安全流程。
- [RAG 检索设计](docs/RAG_RETRIEVAL.md)：Retriever 契约、来源回填、混合检索和降级规则。
- [Model Gateway 设计](docs/MODEL_GATEWAY.md)：provider 契约、结构化输出、安全检查和 fallback trace。
- [LangGraph 工作流](docs/LANGGRAPH_WORKFLOW.md)：图节点、条件路由、状态、确认门和运行产物。
- [Agent Runtime API](docs/AGENT_RUNTIME_API.md)：运行入口、持久化、冻结回放、幂等与确认续跑。
- [前端架构](docs/FRONTEND_ARCHITECTURE.md)：成员切换、API 客户端、页面状态和跨成员防线。
- [从零学习路线](docs/learning/README.md)：需求拆解、代码设计、review 和简历表达。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、services、tools、agent 与测试
frontend/      Next.js 页面与组件
docs/          面向协作者的项目文档和学习材料
alembic/        数据库迁移
scripts/       可重复 seed 等辅助脚本
AGENTS.md      AI Coding Harness 规则
```

## 贡献方式

从最新 `main` 创建一个只对应单一阶段目标的 `codex/...` 分支。完成最小实现、测试和文档同步后再 review、合并与推送。不要在 README 中新建阶段编号；阶段状态只在 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 中维护。

项目亮点和简历表达边界见 [RESUME_NOTES.md](docs/RESUME_NOTES.md)。

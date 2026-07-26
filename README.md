# 家庭健康服务 Multi-Agent

一个面向互联网医院患者端的家庭健康服务 Agent 项目。最终产品覆盖智能预问诊与分级导诊、家庭医生与慢病用药履约、报告解读与长期健康档案三条业务线，并通过工具证据、RAG 引用、Agent 安全和人工确认形成可追踪的业务闭环。

> 这不是 AI 医生，也不是生产医疗系统。系统不做疾病诊断、自动开方、处方修改或剂量调整；任何复诊、购药和提醒动作都必须经过人工确认，且当前只写入本地草稿，不会提交医院、药店或推送服务。

## 当前状态

项目已按 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 完成 `4A` 产品重定与共享契约。后续只保留两个集中阶段：

- `4B`：一次性完成三条业务线所需的后端 Agent、Provider Adapter、向量优先 RAG、API、持久化、安全与评测。
- `4C`：完成成熟患者端、前后端全链路、E2E、Docker 部署、可观测性和交付收口。`4C` 完成即代表当前产品范围全部完成，不再把必要能力留作后续展望。

当前正在推进 `4B` 后端闭环：任务一、二已完成；任务三的统一向量 RAG 和任务四的新业务 Model Gateway 已完成代码与离线回归，任务五至八仍未完成，因此 `4B` 尚未宣称完成。

目前已经具备：

- SQLAlchemy / Alembic 数据模型、可重复 seed 数据和后端测试。
- Pydantic Context、Trace、Tool 和 Evaluation 契约。
- ContextManager 的角色最小视图、上下文压缩与 run 后 reset。
- deterministic Tool Registry、固定 Harness 用例、可重复的评估和 Markdown 报告。
- 数据库只读查询工具，以及只创建本地 draft 的确认门禁工具。
- 家庭、药箱、处方/购药、药店库存、知识检索与 Agent 审计的只读 FastAPI 接口；知识检索已完成自动化与 PostgreSQL/Postman 验证。
- 本地草稿创建、查询、确认和拒绝 API；状态机只改变本地记录，始终保留 `not_submitted` 外部状态。
- `4B` 业务任务闭环：预问诊/导诊、慢病履约和健康档案三类有界 LangGraph 入口；首次请求等待确认，确认后只写本地 draft；可通过 artifacts 接口回放 `RunTrace`、`RunSummary` 和 `EvaluationResult`。
- RAG：运行时统一使用 canonical embedding provider、PostgreSQL pgvector HNSW 索引和关键词降级；`FastEmbed` 负责真实 CPU/ONNX 语义向量，deterministic provider 负责无模型环境，模型、维度、hash/schema 和来源信息都会进入索引/检索校验。
- Provider Adapter：所有 mock provider 都标记 `provider_mode=mock` 和 `simulation=true`；未配置的 `sandbox/real` 返回结构化 degraded 结果，不伪造医院、药店或通知服务数据。
- Model Gateway：默认 deterministic，可选真实 HTTP provider；旧 Agent 和新的三条业务子图都通过统一 Gateway 生成结构化 FinalAnswer，所有输出先过 Pydantic 与安全检查，失败留下 attempt trace 并回退。
- 有界 LangGraph DAG：按 intent 路由四类业务角色，统一经过 ContextManager、Tool Registry、SafetyAgent、确认草稿、RunTrace/reset 和只读 Evaluator。
- Agent Runtime API：真实 DB tools、run/tool-call 持久化、冻结产物查询、幂等运行和确认后的同任务续跑；任何动作仍只创建本地草稿。
- Next.js 数据页面与 Agent 演示入口：共享成员选择、四类场景、Tool/RAG 来源、安全提示、确认续跑和 Trace/Evaluation 详情。

## 当前可运行场景

1. 父亲降压药的续方材料整理。
2. 母亲中医复诊材料整理。
3. 母亲用药提醒草稿与本地确认。
4. 加量、减量、停药、换药等高风险请求的安全拦截。

这些能力是新产品三条业务线的已有基础，不等同于三条完整业务线已经交付。目标业务流程见 [BUSINESS_WORKFLOWS.md](docs/BUSINESS_WORKFLOWS.md)。

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

第一次运行请先阅读 [本地环境、启动与部署指南](docs/LOCAL_SETUP_AND_DEPLOYMENT.md)，日常开发流程见 [开发者指南](docs/DEVELOPER_GUIDE.md)。最短的 Docker 启动方式如下：

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

只验证 4B 业务任务、Provider 和 embedding：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_business_task_api.py backend\tests\test_provider_and_embedding.py -q -p no:cacheprovider --basetemp=$env:TEMP\hospital-pytest-4b
```

只验证 4B 任务三/四：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_vector_rag.py `
  backend\tests\test_hybrid_rag.py `
  backend\tests\test_model_gateway.py `
  backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-4b-rag-model
```

生成知识向量索引前，先确认 `.env` 中的 provider 和维度；无模型环境可使用 deterministic provider，真实语义检索使用 FastEmbed：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.rag.indexer
```

索引命令只写入 `knowledge_chunks` 的向量及版本元数据，不生成医疗结论；模型下载失败或向量检索不可用时，业务检索会保留 `fallback_reason` 并降级到关键词。

只验证 Provider Adapter 契约和七个离线 mock provider：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_provider_adapters.py -q -p no:cacheprovider --basetemp=.tmp\pytest-provider
```

启用可选语义 embedding 前先安装 `backend\requirements.txt` 中的 `fastembed`，然后把 `.env` 改为：

```text
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_PROVIDER=fastembed
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_DIMENSIONS=512
FASTEMBED_CACHE_PATH=E:\\project_code\\hospital\\var\\fastembed
```

模型第一次使用时会下载到 `FASTEMBED_CACHE_PATH`；无网络、未安装依赖或模型不可用时，Retriever 仍返回可审计的关键词降级结果。使用确定性 provider 的测试不需要下载模型。

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

## 文档入口

从 [docs 文档导航](docs/README.md) 开始。它区分了产品、开发、技术、接口、数据库、Agent 和学习材料。

常用入口：

- [总开发路线图](docs/DEVELOPMENT_ROADMAP.md)：阶段状态、顺序和最终产品验收的唯一权威来源。
- [当前实现审计](docs/CURRENT_STATE_AUDIT.md)：已经实现、部分实现和尚未实现的边界。
- [目标业务流程](docs/BUSINESS_WORKFLOWS.md)：三条患者端业务线、输入输出和人工确认点。
- [开发者指南](docs/DEVELOPER_GUIDE.md)：环境、命令、分支、测试与提交流程。
- [技术设计](docs/TECH_DESIGN.md)：分层边界、数据流与当前实现边界。
- [接口文档](docs/API_SPEC.md)：已实现接口与后续接口契约边界。
- [Agent 架构](docs/AGENT_ARCHITECTURE.md)：业务子图、角色边界、上下文、工具和运行顺序。
- [RAG 检索设计](docs/RAG_RETRIEVAL.md)：向量优先目标、混合召回、来源回填、重排和降级规则。
- [工具契约](docs/TOOL_CONTRACTS.md)：Provider 模式、工具版本、证据和审计字段。
- [Agent 安全](docs/SAFETY_POLICY.md)：医疗边界、风险分级和人工确认门。
- [Agent 评测](docs/EVALUATOR_AGENT.md)：运行后评测、RAG 指标和最终报告。
- [固定用例指标报告](docs/AGENT_EVAL_REPORT.md)：16 条 deterministic + mock 回放结果、可测指标和简历使用边界。
- [Model Gateway 设计](docs/MODEL_GATEWAY.md)：provider 契约、结构化输出、安全检查和 fallback trace。
- [Agent Runtime API](docs/AGENT_RUNTIME_API.md)：运行入口、持久化、冻结回放、幂等与确认续跑。
- [前端架构](docs/FRONTEND_ARCHITECTURE.md)：最终患者端、成员切换、业务状态和审计展示。
- [本阶段业务 API](docs/API_SPEC.md#9-4b-业务任务-api)：三条业务线的任务创建、确认、来源和冻结产物查询。
- [从零学习路线](docs/learning/README.md)：需求拆解、代码设计、review 和简历表达。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、services、tools、agent 与测试
frontend/      Next.js 页面与组件
docs/          面向协作者的项目文档和学习材料
backend/alembic/ 数据库迁移
scripts/       可重复 seed 等辅助脚本
AGENTS.md      AI Coding Harness 规则
```

## 贡献方式

从最新 `main` 创建一个只对应单一阶段目标的 `codex/...` 分支。完成最小实现、测试和文档同步后再 review、合并与推送。不要在 README 中新建阶段编号；阶段状态只在 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 中维护。

项目亮点和简历表达边界见 [RESUME_NOTES.md](docs/RESUME_NOTES.md)。

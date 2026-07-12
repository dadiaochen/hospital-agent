# 互联网医院慢病续方与家庭用药管理 Agent 系统

这是一个面向互联网医院业务链路的家庭健康事务管理 Agent 项目。系统定位是长期健康管家，不是 AI 医生：不诊断、不自动开方、不修改医生处方，所有复诊、购药、提醒创建等关键动作都必须经过用户或医生确认。

当前完成到阶段 2C-2：已实现 Tool Registry 契约层、6 个 deterministic mock 工具，以及最小 Agent Harness Runtime，可将 ContextManager、ToolRegistry、RunTrace 和 DeterministicEvaluator 串联起来回放 16 条固定 fixture；仍未实现真实数据库查询工具、FastAPI 业务 API、LangGraph 工作流或真实在线 EvaluatorAgent。

## 技术栈

- Backend: Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Redis, Pydantic, LangGraph, pytest
- Frontend: TypeScript, Next.js App Router, Tailwind CSS
- Infra: Docker, docker-compose, `.env.example`

## 本地运行

### 1. 准备环境变量

```bash
cp .env.example .env
```

### 2. 启动 PostgreSQL 与 Redis

```bash
docker compose up -d postgres redis
```

### 3. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端地址：

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:3000`

### 5. 使用 Docker 启动全栈

```bash
docker compose up --build
```

## 数据库迁移与 Seed

安装后端依赖并执行迁移：

```bash
cd backend
pip install -r requirements.txt
cd ..
python -m alembic upgrade head
```

阶段 2A.1 新增迁移 `backend/alembic/versions/0002_add_agent_harness_trace_fields.py`，只补充 `agent_runs` 和 `agent_tool_calls` 的 trace / harness 字段，不改写 `0001_initial_schema`。

写入 seed 数据：

```bash
python scripts/seed.py
```

seed 会创建或更新用户、家庭成员、健康档案、处方、购药记录、药箱、药店库存、知识库规则，以及示例 `agent_runs` / `agent_tool_calls` 审计记录。

运行后端测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

## 当前文件结构

```text
.
├── docs/
│   ├── AGENT_WORKFLOW.md
│   ├── API_SPEC.md
│   ├── CONTEXT_MANAGEMENT.md
│   ├── DB_SCHEMA.md
│   ├── EVALUATOR_AGENT.md
│   ├── HOSPITAL_LANGFLOW_HARNESS_PLAN.md
│   ├── PRD.md
│   ├── RESUME_NOTES.md
│   └── TECH_DESIGN.md
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── context_schemas.py
│   │   │   ├── context_manager.py
│   │   │   ├── eval_schemas.py
│   │   │   ├── evaluator.py
│   │   │   ├── harness_runtime.py
│   │   │   ├── harness_runner.py
│   │   │   └── run_trace_schemas.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── rag/
│   │   ├── safety/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── tools/
│   │       ├── mock_tools.py
│   │       ├── registry.py
│   │       ├── tool_registry.py
│   │       └── tool_schemas.py
│   └── tests/
│       ├── fixtures/agent_harness_cases.json
│       ├── fixtures/mock_run_traces.json
│       ├── test_agent_contract_schemas.py
│       ├── test_context_manager.py
│       ├── test_deterministic_evaluator.py
│       ├── test_harness_runner.py
│       └── test_harness_runtime.py
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
├── scripts/
│   └── seed.py
├── .env.example
├── AGENTS.md
├── alembic.ini
├── docker-compose.yml
├── family_health_agent_project_prompt.md
└── README.md
```

## 第一阶段已完成

- 创建产品、技术、API、数据库、Agent 工作流和恢复说明文档。
- 创建 FastAPI 最小可启动服务。
- 创建后端分层目录：`api/services/models/schemas/tools/agent/rag/safety/core`。
- 创建 MCP-like Tool Registry 的最小契约骨架。
- 创建 FamilyHealthAgent 占位类，保留 LangGraph 工作流节点设计。
- 创建 Next.js App Router 最小可启动前端和主要业务路由占位。
- 创建 Dockerfile、docker-compose、`.env.example`。
- 创建最小健康检查测试。

## 第二阶段 2A 已完成

- 新增 `app.core.database`，提供 `Base`、`engine`、`SessionLocal`、`get_db`。
- 新增 18 张 SQLAlchemy ORM 模型，对齐用户、家庭成员、药箱、处方、购药、药店、复诊方案、提醒、知识库和 Agent 日志。
- 新增 Alembic 配置和首个迁移 `0001_initial_schema`。
- 新增 `scripts/seed.py`，可重复写入 MVP 模拟数据。
- 新增模型测试，覆盖 metadata、关键字段、医疗安全禁用字段和 seed 幂等性。

## 第二阶段 2A.1 已完成

- 合并 Multi-Agent 角色边界、ContextEnvelope、Tool Registry、安全与幻觉控制、Agent Harness 验收规则到根目录 `AGENTS.md`。
- 新增 `docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`，整理 Langflow-like trace / harness 落地计划。
- 为 `AgentRun` 补充 `started_at`、`ended_at`、`duration_ms`、`step_count`、`task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate`。
- 为 `AgentToolCall` 补充 `agent_role`、`error_type`、`fallback_action`、`schema_valid`。
- 新增 Alembic 迁移 `0002_add_agent_harness_trace_fields.py`，不改写 `0001_initial_schema`。
- 更新 seed 示例和测试，保留人工确认与医疗安全边界。

阶段 2A.1 运行方式：

```powershell
python -m alembic upgrade head
python scripts/seed.py
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

## 第二阶段 2A.2 已完成

- 新增 `docs/CONTEXT_MANAGEMENT.md`，定义 Context Lifecycle、TaskContext Builder、Role-specific Context View、RunSummary、Context Reset / Compaction 和长期记忆写入门槛。
- 新增 `docs/EVALUATOR_AGENT.md`，定义独立 post-run EvaluatorAgent、ExpectedCase、EvaluationResult 和 AgentHarness 报告聚合方式。
- 更新 Multi-Agent 角色边界，明确 SafetyAgent 负责运行时安全拦截，EvaluatorAgent 负责事后质量评估。
- 更新 Harness、工作流、技术设计、简历说明、项目提示词和项目规则。
- 修复“当前文件结构”区域混入代码审查文本和代码片段的格式污染。
- 未修改后端模型、Alembic migration、`scripts/seed.py`、ToolRegistry 业务工具、Multi-Agent 运行代码、EvaluatorAgent 代码或前端。

阶段 2A.2 文档检查：

```powershell
rg -n "Context Reset|Context Compaction|EvaluatorAgent|EvaluationResult" AGENTS.md README.md family_health_agent_project_prompt.md docs
```

## 阶段 2B-1 已完成

- 新增 `backend/app/agent/context_schemas.py`：`TaskState`、`ToolEvidenceRef`、`RAGSourceRef`、`ContextEnvelope`、`RoleSpecificContextView`、`RunSummary` 等上下文契约。
- 新增 `backend/app/agent/eval_schemas.py`：`ExpectedCase`、`ExpectedSource` 和 `EvaluationResult` 评估契约。
- 所有契约默认 `extra="forbid"`，角色视图不能携带 `raw_conversation` 等未声明字段。
- ContextEnvelope、角色视图和 RunSummary 校验 tool/RAG 引用的 `run_id` 与 `member_id` 隔离。
- `memory_refs` 只允许用户确认的内容，拒绝未经确认的模型推断。
- 新增 16 条固定 Harness fixture：3 条续方、3 条复诊材料、3 条提醒、4 条高风险医疗、3 条工具异常/隔离/无来源。
- 新增契约测试，覆盖实例化、非法 intent/role、raw conversation、fixture 加载、failure reasons、memory 门槛、成员隔离和安全 flag。
- 本阶段未新增 API、数据库表或迁移，也未实现真实 AgentHarness 或 EvaluatorAgent。

阶段 2B-1 验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

## Context 与评估架构

```text
Raw Conversation
  -> TaskContext Builder
  -> ContextEnvelope
  -> Role-specific Context View
  -> Tool Evidence / RAG Sources
  -> FinalAnswer
  -> Run Summary
  -> Context Reset
  -> EvaluatorAgent Review
  -> Long-term Memory Write
```

- 每次 run 结束后生成 RunSummary 并清理临时 working context。
- Tool Evidence、RAG source id、trace、FinalAnswer 和 eval 引用必须保留。
- 同一任务允许 compaction，但事实保留 source pointer；不相关任务和成员切换必须 reset。
- 未经用户确认的模型推断不得写入长期 memory。
- EvaluatorAgent 只读 run 产物，不修改用户答案，不生成医疗建议，不写业务状态。

## 阶段 2B-2 已完成

- 新增冻结的 `RunTrace`、`ToolCallTrace`、`FinalAnswerTrace`、`SafetyTrace` 和 `RAGTrace`。
- 新增 `DeterministicEvaluator`，以明确规则计算 intent/member、工具覆盖、来源、schema、安全召回、人工确认、上下文隔离和延迟结果。
- 新增 `HarnessRunner`，加载 16 条 ExpectedCase 与 16 条 mock RunTrace，输出 EvaluationResult 列表和聚合指标。
- 新增 `mock_run_traces.json`，包含成功路径以及缺工具、缺安全标记、禁用短语、成员串扰、无来源硬答和缺确认提示等故意失败路径。
- 新增 `docs/agent_eval_report.example.md`。报告中的数值来自 deterministic mock fixtures，不是生产或临床效果指标。
- Evaluator 只读冻结 trace，不调用 LLM、数据库、API、ToolRegistry 或 LangGraph，也不修改 FinalAnswer。

运行 deterministic Harness：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.harness_runner
```

运行完整验证：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

Harness 报告测试直接校验内存中的 Markdown 渲染结果及已提交示例报告，不依赖 pytest `tmp_path` 或 Windows 用户临时目录。这样文件系统权限问题不会被误判为 evaluator / runner 逻辑失败。

## 阶段 2B-3 已完成

- 新增 `backend/app/agent/context_manager.py`，实现纯内存 ContextManager。
- `build_envelope` 根据用户输入摘要、任务信息、工具证据引用、RAG 来源引用和安全标记构造 `ContextEnvelope`。
- `build_role_view` 按角色裁剪 `RoleSpecificContextView`，不暴露完整 raw conversation；EvaluatorAgent 不能获取业务执行上下文。
- `compact` 支持同一 `task_id` / `member_id` 的上下文压缩，并保留 `source_id`、`tool_call_id` 和 `member_id`。
- `create_run_summary` 基于 `ContextEnvelope`、`RunTrace`、`FinalAnswerTrace` 和 `EvaluationResult` 生成 `RunSummary`。
- `reset_after_run` 清理临时 working context，只保留 RunSummary、ToolEvidence refs、RAG refs、FinalAnswer ref 和 EvaluationResult ref。
- 新增 `backend/tests/test_context_manager.py`，覆盖构造、角色裁剪、成员隔离、compact、reset 和 EvaluatorAgent 拒绝进入业务上下文。
- 本阶段不调用 LLM、数据库、API、ToolRegistry 或 LangGraph。

阶段 2B-3 验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

## 阶段 2C-1 已完成

- 新增 `backend/app/tools/tool_schemas.py`，定义 `ToolSpec`、`ToolExecutionContext`、`ToolResult`、`RetryPolicy` 和 `ToolPermissionScope`。
- 新增 `backend/app/tools/tool_registry.py`，实现工具注册、查询、角色可用工具列表和 `ToolRegistry.call`。
- 新增 `backend/app/tools/mock_tools.py`，提供 6 个 deterministic mock 工具：健康档案、处方、药箱、药店库存、安全知识和确认草稿。
- `ToolRegistry.call` 统一校验工具存在性、`allowed_tools`、角色权限、输入/输出 schema、handler 异常和人工确认门。
- `ToolResult` 可映射为 `ToolCallTrace` 所需字段。
- mock 工具不访问数据库、不调用 API、不调用 LLM，不返回诊断、自动开方或剂量调整建议。

## 阶段 2C-2 已完成

- 新增 `backend/app/agent/harness_runtime.py`，实现最小 `AgentHarnessRuntime`。
- 新增 `HarnessRuntimeResult` 和 `HarnessRuntimeBatchResult`，保存 `ContextEnvelope`、角色视图、`ToolResult`、`RunTrace` 和 `EvaluationResult`。
- Runtime 默认通过 `ContextManager.build_envelope` 构造上下文，通过 `ContextManager.build_role_view` 构造角色视图。
- Runtime 根据 `ExpectedCase.expected_required_tools` 调用 mock `ToolRegistry.call`，不直接调用 mock handler。
- Runtime 将 `ToolResult` 转成 `ToolCallTrace`，并构造 `RAGTrace`、`SafetyTrace` 和 mock `FinalAnswerTrace`。
- Runtime 使用 `DeterministicEvaluator.evaluate` 生成 `EvaluationResult`，不是手写成功结果。
- `run_all` 可运行 16 条 fixture，并复用 `HarnessRunner.aggregate` 聚合指标。
- 新增 `backend/tests/test_harness_runtime.py`，覆盖正常续方、高风险安全、权限失败、缺工具失败、确认门、成员隔离、trace 来源、批量运行和无外部依赖。

聚合指标中文解释：

- `task_success_rate`：任务成功率。
- `tool_call_accuracy_avg`：预期工具调用覆盖率平均值。
- `groundedness_rate`：答案依据覆盖率。
- `schema_valid_rate`：结构化契约合法率。
- `hallucination_rate`：幻觉或禁用表达触发率。
- `safety_recall_rate`：安全标记召回率。
- `human_confirmation_rate`：需要人工确认时确认提示覆盖率。
- `context_isolation_pass_rate`：成员上下文隔离通过率。
- `p95_latency_ms`：mock 运行延迟的 95 分位值。

阶段 2C-2 验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

本阶段 runtime 指标只代表 deterministic mock fixtures 的回放结果，不代表真实线上、生产或临床效果。

## 项目亮点与简历描述

项目描述：基于互联网医院问诊、处方、药店审核、购药履约链路，设计家庭健康管家 Agent，帮助用户整理慢病续方、复诊材料、家庭药箱、用药提醒和 Agent 执行记录。

技术栈：FastAPI、SQLAlchemy、PostgreSQL、Redis、Pydantic、LangGraph、Next.js、TypeScript、Tailwind CSS、Docker。

核心职责：负责后端分层架构、Multi-Agent 角色边界、医疗安全策略、ContextManager、Context Reset / Compaction、Tool Registry 契约层，以及 Agent Harness 的强类型契约、mock runtime、确定性评估规则和固定用例回放。

面试讲解稿：项目重点不是让模型替代医生，而是把模型放在可审计、可确认、可回放、可评估的业务流程中。SafetyAgent 在运行时拦截高风险请求，EvaluatorAgent 在答案生成后检查证据、确认和成员隔离，两者职责分离。

简历表达边界：可以写“设计了 Context Reset / Context Compaction / EvaluatorAgent / Agent Harness”。当前没有真实 eval report，因此不能声称达到 100% safety recall、0 hallucination、100% groundedness 或任何 p95 latency 数值；这些只能写为目标指标或评估维度。

## 下一阶段建议

下一步可实现 ToolResult 到持久化 `agent_tool_calls` 的 adapter，并把 mock runtime 产物导出为 JSON/Markdown 双格式报告；真实数据库工具和 LangGraph 编排仍放在后续阶段。

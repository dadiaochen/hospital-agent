# 开发者指南

本指南面向要在本仓库写代码、跑测试和提交改动的协作者。项目当前是本地演示级 MVP；不要把示例数据、默认配置或 mock Harness 误认为生产能力。

## 1. 开发前先确认范围

1. 打开 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)，只选择其中 `NEXT` 的阶段或用户明确指定的范围。
2. 阅读根目录 [AGENTS.md](../AGENTS.md)，尤其是医疗安全边界、分层规则和文档同步要求。
3. 为一个单一目标创建 `codex/<stage>-<short-name>` 分支；不要把 API、LangGraph、前端和数据库重构混进同一个小阶段。

## 2. 本地环境

推荐 Python 3.11+、Docker Desktop、Node.js 20+ 和 GitHub Desktop。PowerShell 示例均从仓库根目录执行。

首次安装、WSL 2、Docker 数据迁移到 E 盘、PostgreSQL 初始化、前后端启动和常见故障见 [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md)。下面保留日常开发所需的最短命令。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

`.env` 只放本地配置，不能提交密钥。服务依赖可单独启动：

`RAG_VECTOR_ENABLED` 默认是 `false`，此时只使用数据库关键词检索且不加载模型。4A 已实现 FastEmbed + pgvector；开发者可运行 `.\scripts\start_vector_rag.ps1` 自动启动、索引和验证，模型缓存位于项目 `var\models`，不提交 Git。

`MODEL_PROVIDER` 默认是 `deterministic`，不需要 Key，也不会联网。只有准备好兼容 `/chat/completions` 的服务后才配置 `openai_compatible`、`MODEL_API_BASE`、`MODEL_API_KEY`、`MODEL_NAME` 和 `MODEL_TIMEOUT_MS`。Key 只能保存在未提交的 `.env` 或部署密钥系统中。

```powershell
docker compose up postgres redis -d
```

初始化数据库与 demo 数据：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
```

启动后端：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m uvicorn app.main:app --reload --app-dir backend
```

启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

前端通过 `NEXT_PUBLIC_API_BASE_URL` 访问后端，默认是 `http://localhost:8000`。这是公开的浏览器配置，不能放数据库密码、模型 Key 或其他秘密。

也可以直接用 `docker compose up --build` 启动完整演示环境。3D 的 backend 容器会自动执行 migration 与幂等 seed；需要同时验证固定四场景时运行 `.\scripts\start_demo.ps1`，详见 [MVP 演示手册](DEMO_RUNBOOK.md)。

## 3. 日常验证

后端完整测试与静态编译检查：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest\all
python -m compileall backend\app backend\tests
```

生成并验证 4B 任务十一 deterministic 消融报告：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.ablation_harness
python -m pytest backend\tests\test_ablation_harness.py -q -p no:cacheprovider --basetemp=output\pytest-task11
```

运行器把完整 JSON/Markdown 写到 `output/`。早期消融中的 latency 是 fixture 字段，token/cost 为 `N/A`，不能替代 Docker wall-clock 验收；历史摘要见 [项目执行历史](EXECUTION_HISTORY.md)。

运行任务十二的后端验收：

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
docker compose up -d --build --wait --wait-timeout 300
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

该命令证明本机数据库、缓存、API 和索引链路，不代表生产部署、真实 Provider 或医疗效果。

Windows 某些环境会拒绝访问默认 pytest 临时目录。上面的 `--basetemp` 把临时文件固定到仓库内的 `.tmp`，避免把环境权限问题误判为业务测试失败。

只验证 2F-1 RAG：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q --basetemp=.tmp\pytest-rag
```

只验证 4A 真实向量适配与索引规则：

```powershell
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests\test_vector_rag.py backend\tests\test_hybrid_rag.py -q `
  --basetemp=var\pytest\vector-rag
```

只验证 2F-2 Model Gateway：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_model_gateway.py -q --basetemp=.tmp\pytest-model
```

只验证 2G-1 LangGraph 工作流和上下文生命周期：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_langgraph_workflow.py backend\tests\test_context_manager.py -q -p no:cacheprovider --basetemp=.tmp\pytest-workflow
```

这些测试不会调用外部 LLM、数据库或 HTTP API。默认 workflow 使用 mock Tool Registry 与 deterministic Model Gateway，适合离线 review 兼容图的节点路由和安全边界；它们不覆盖任务六的独立编排内核，也不等于三层安全确认已经实现。

4B 任务五的最终契约与 deterministic Router：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_orchestration_contracts.py backend\tests\test_complexity_router.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task5
```

这组任务五测试只验证身份作用域、固定角色/动作候选、复杂度路由和计划边界；任务六的独立测试才启动 deterministic Supervisor，仍不会调用业务工具。

4B 任务六的三个领域 Agent、一次性 Planner 和串行 bounded Supervisor：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_domain_orchestration.py backend\tests\test_orchestration_contracts.py backend\tests\test_complexity_router.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task6
```

这组实现和测试仍是 deterministic、无数据库、无 LLM、无业务工具副作用的编排内核。简单请求不创建计划；复杂请求只创建一次计划，Supervisor 只能串行执行白名单角色，最多 3 次总调用，并记录重试、降级、澄清、失败或终止决策。任务七的三层 Safety/Confirmation 已接入新业务任务链路；任务八已在业务 task service 外围接入 PostgreSQL 权威 checkpoint 与 Redis 回源，未把数据库查询塞回 Agent 编排内核。

4B 任务七的安全和确认状态机：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_safety_confirmation.py backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task7
```

重点检查 `backend/app/agent/safety_confirmation.py`：请求层必须在业务工具前阻断；动作层只允许同 user/member/task/version/fingerprint/idempotency scope 的迁移；最终答案必须在冻结前通过输出安全检查。首轮响应应为 `confirmation_state=DRAFT`，确认续跑才推进到 `EXECUTED`，且外部状态始终 `not_submitted`。旧 `/api/agent-runs` 的兼容确认语义不要与新 `/api/business-tasks` 混淆。

4B 任务八的状态、缓存和偏好回归：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_business_task_api.py backend\tests\test_task_checkpoint_cache.py backend\tests\test_migration_chain.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task8
```

重点检查 `TaskCheckpointService` 是否只把 allow-listed RunSummary/冻结产物跨 run；`TaskCheckpointCache` 是否按 user/member/task/thread/version 校验并在 Redis miss 时回源；确认请求是否拒绝陈旧版本；`ConfirmedPreferenceService` 是否要求已执行的人工确认和匹配来源版本。Redis 不能成为唯一事实来源，确认后的 `EXECUTED` 仍不是外部医疗系统提交。

只验证 2G-2 Agent Runtime API：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_agent_runtime_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-runtime
```

这组测试通过 FastAPI TestClient 和测试数据库执行真实 DB tools，但仍使用 deterministic Model Gateway，不访问外部模型、医院或药店。

验证 3A/3B 前端类型、成员隔离、确认/Trace 契约和生产构建：

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

页面联调时要分别切换本人、父亲和母亲，观察浏览器 Network 面板中的 `member_id`。3B 还要核对首次 Agent POST 固定为 false、确认续跑为 true、高风险结果没有确认按钮，以及 Trace 三个 GET 属于同一 run/member。知识检索页使用已完成的 `/api/knowledge/search` 契约，可通过 Swagger 或 Postman 与页面结果交叉核对。

3C Runtime Harness 在 Docker PostgreSQL/FastAPI 启动并 seed 后运行：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.runtime_harness `
  --base-url http://localhost:8000 `
  --environment local_postgresql_deterministic `
  --run-key-prefix "3c-$((Get-Date).ToString('yyyyMMddHHmmss'))"
```

报告写入被 Git 忽略的 `output/benchmarks/runtime_harness_report.json` 和 `.md`。报告不含 member/run ID 或答案正文；每次新测量使用新的前缀，复用前缀会命中 Runtime 幂等 replay。阶段报告不再写入 `docs/`，避免生成文件和当前设计文档混在一起。

3D 固定 MVP 演示：

```powershell
.\scripts\start_demo.ps1
# 服务已健康时只重跑四场景
.\scripts\run_demo.ps1
```

自动化契约位于 `test_mvp_demo_runner.py`；本地报告位于被忽略的 `var/demo/`。历史交付证据摘要见 [项目执行历史](EXECUTION_HISTORY.md)。四场景通过只属于本地 PostgreSQL seed 和 deterministic provider。

确认当前 API：访问 `http://localhost:8000/docs`、`/health` 和 `/api/health`。读取 API 与知识检索已集成；固定 demo user 由 `DEMO_USER_PHONE` 配置，默认匹配 seed 的示例手机号。

## 4. 分层与改动位置

| 目录 | 应放内容 | 不应放内容 |
| --- | --- | --- |
| `backend/app/api` | HTTP 入参、出参、依赖注入、路由 | 数据库查询和 Agent 推理 |
| `backend/app/schemas` | API Pydantic DTO | SQLAlchemy ORM |
| `backend/app/models` | ORM 表与关系 | 业务流程 |
| `backend/app/services` | 查询、草稿、状态机等业务逻辑 | HTTP 处理 |
| `backend/app/tools` | Agent 可调用的受约束工具 | 绕过权限的直接查询 |
| `backend/app/agent` | Context、Trace、Harness、Model Gateway、复杂度路由和 LangGraph 图工作流 | 数据库业务实现 |
| `backend/app/safety` | 医疗安全规则和人工确认判断 | 业务写入 |
| `backend/app/rag` | 检索与来源返回 | 无来源事实生成 |
| `frontend/lib/api` | 浏览器 API 类型、路径、错误和成员响应检查 | 数据库访问或医疗业务规则 |
| `frontend/app` | 页面组合与展示状态 | 直接拼接数据库查询或绕过 API client |

## 5. GitHub Desktop 工作流

1. 在 GitHub Desktop 切到最新 `main`，点击 `Fetch origin`，必要时 `Pull origin`。
2. 点击 `Current branch` -> `New branch`，命名为 `codex/<stage>-<short-name>`。
3. 完成一组可验证的改动后，填写清晰的 Summary，Commit 到当前分支，再点击 `Publish branch` 或 `Push origin`。
4. review 时看 diff、运行测试，并检查文档和阶段范围。
5. 合并后切回 `main` 并同步远端；下一阶段一定从已同步的 `main` 新建分支。

本项目优先保持线性历史：功能分支应基于最新 `main`，可以快进时不制造无意义 merge commit。不要删除未核对的 stash 或备份分支。

## 6. 每次提交前的最小清单

- 改动只覆盖当前阶段目标。
- 新 DTO、工具或状态转移有最小测试。
- 未新增诊断、开方、剂量调整或外部医疗提交逻辑。
- 用户和 `member_id` 的边界已经验证。
- 工具经过 Tool Registry；本地 DRAFT 无外部副作用，受保护动作经过人工确认。
- 只读 Tool/Provider 只对 timeout、rate-limit、临时不可用有限重试；参数、权限、schema、业务冲突、内部错误和写操作不自动重试；失败响应没有 data/SourceRef。
- 简单任务直接路由，复杂任务才使用一次性 Planner 与 bounded Supervisor；当前内核只允许对依赖已满足、只读且无副作用的 DAG 步骤有界并行。所有条件边必须有明确终点，不允许依赖模型输出无限循环。
- 请求、动作和最终输出三层安全均不可由 Supervisor 绕过；Evaluator 位于回答与 reset 之后且只读。
- 最终 Runtime 的确认是同一 task 下的新 run；PostgreSQL 是 checkpoint 权威源，Redis 故障能回源，重复或并发确认不会重复执行。
- 前端成员页面在切换时取消旧请求，并区分 loading、empty、error；成员响应通过 `member_id` 二次检查。
- 当前 Agent UI 使用兼容确认字段；最终 UI 展示自动生成的本地 DRAFT，用户只确认执行。高风险不能续跑，Trace/Evaluation 始终只读。
- 更新了对应的技术、接口、数据库、Agent 或测试文档。
- README 只更新对 GitHub 访客有价值的当前状态，不追加阶段流水账。
- `.env`、API Key、Token、真实成员数据、identity/source map、人工审核队列、`output/` 和 `var/` 没有进入 Changes。
- 合成 fixture 可以提交，但必须使用合成 ID，并明确标记为测试数据；不得把本机 PostgreSQL 导出或真实模型原始输出伪装成 fixture。

本项目明确不以 MCP Server、OpenTelemetry/Jaeger 或复杂自动重规划作为目标。当前 bounded Supervisor 已支持有界 DAG，只并行相互独立、依赖已满足、只读且无副作用的领域步骤。确认、写操作、Checkpoint、安全治理和评测保持串行，任务状态和副作用仍由 PostgreSQL 事务、幂等键和状态条件更新保证一致性。

## UX-06 报告详情验证

报告详情契约冻结后，前端使用 `/reports` 和 `/reports/[reportId]` 读取报告列表与详情，后端使用现有 `medical_documents` 数据。增量验证命令为：

```powershell
Set-Location E:\project_code\hospital
$env:PYTHONPATH=(Resolve-Path 'backend').Path
.\.venv\Scripts\python.exe -m pytest backend\tests\test_read_api.py -q -p no:cacheprovider --basetemp=var\pytest\ux06-read-api
Set-Location frontend
npm run test
npm run typecheck
npm run build
```

本次验证结果为报告接口测试 6 个通过、后端全量 361 个通过、前端 34 个测试通过、类型检查通过和生产构建通过；UX-08 之前不新增上传写入或内部入口清理。

## UX-08 用户端入口清理

在 `frontend` 目录验证：

```powershell
npm run typecheck
npm run test
npm run build
npm run test:e2e -- e2e/portal-entry-cleanup.spec.ts
```

UX-08 的兼容跳转配置位于 `frontend/next.config.mjs`；公共导航只由 `frontend/lib/navigation.ts` 提供。本次类型检查、35 个前端测试、生产构建和 2 个公共入口 E2E 均通过；E2E 使用明确的 `127.0.0.1` 基址，避免命中机器上的其他 `localhost:3000` 服务。下一步按路线图进入 UX-09。

## UX-09 开发者验收边界

UX-09 的联调只允许修正既有接口契约，不新增页面背后的业务动作。检查顺序为：启动 Docker 前后端 → 验证成员切换和确认续跑 → 验证历史、家庭、报告的成员隔离 → 验证兼容路由 → 执行桌面/移动视觉与可访问性检查 → 执行前端全量测试、类型检查、构建和真实 E2E。低库存工具输入缺少药品名时，只能从当前成员已成功读取的药箱/处方事实补齐；没有事实不得猜测。

本次收口使用 deterministic provider，前端 36 个测试、9 条真实 Playwright E2E、类型检查、生产构建和后端 1 条契约单测均通过。UX-09 完成后不再自动新增 UX 子阶段，后续需求须先更新 `docs/DEVELOPMENT_ROADMAP.md`。

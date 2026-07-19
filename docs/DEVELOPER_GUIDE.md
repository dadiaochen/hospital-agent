# 开发者指南

本指南面向要在本仓库写代码、跑测试和提交改动的协作者。项目当前是本地演示级 MVP；不要把示例数据、默认配置或 mock Harness 误认为生产能力。

## 1. 开发前先确认范围

1. 打开 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)，只选择其中 `NEXT` 的阶段或用户明确指定的范围。
2. 阅读根目录 [AGENTS.md](../AGENTS.md)，尤其是医疗安全边界、分层规则和文档同步要求。
3. 为一个单一目标创建 `codex/<stage>-<short-name>` 分支；不要把 API、LangGraph、前端和数据库重构混进同一个小阶段。

## 2. 本地环境

推荐 Python 3.11+、Docker Desktop、Node.js 20+ 和 GitHub Desktop。PowerShell 示例均从仓库根目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

`.env` 只放本地配置，不能提交密钥。服务依赖可单独启动：

`RAG_VECTOR_ENABLED` 默认是 `false`，此时只使用数据库关键词检索。不要仅把它改为 `true` 就假设向量检索可用；2F-1 只定义向量后端协议，真实 Embedding provider 和向量数据库尚未接入。

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

也可以直接用 `docker compose up --build` 启动完整演示环境。

## 3. 日常验证

后端完整测试与静态编译检查：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

Windows 某些环境会拒绝访问默认 pytest 临时目录。上面的 `--basetemp` 把临时文件固定到仓库内的 `.tmp`，避免把环境权限问题误判为业务测试失败。

只验证 2F-1 RAG：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_hybrid_rag.py backend\tests\test_db_backed_tools.py -q --basetemp=.tmp\pytest-rag
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

这些测试不会调用 LLM、数据库或 HTTP API。默认 workflow 使用 mock Tool Registry 与 deterministic Model Gateway，适合离线 review 节点路由和安全边界。

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

页面联调时要分别切换本人、父亲和母亲，观察浏览器 Network 面板中的 `member_id`。3B 还要核对首次 Agent POST 固定为 false、确认续跑为 true、高风险结果没有确认按钮，以及 Trace 三个 GET 属于同一 run/member。知识检索页依赖 2E-1 学习题的 `/api/knowledge/search`；该接口合入前出现可解释错误是当前分支的真实状态。

确认当前 API：访问 `http://localhost:8000/docs`、`/health` 和 `/api/health`。2E-1 分支中的读取 API 需要先运行迁移和 seed；固定 demo user 由 `DEMO_USER_PHONE` 配置，默认匹配 seed 的示例手机号。知识库搜索接口是学习实战题，在完成前不要假设它已经上线。

## 4. 分层与改动位置

| 目录 | 应放内容 | 不应放内容 |
| --- | --- | --- |
| `backend/app/api` | HTTP 入参、出参、依赖注入、路由 | 数据库查询和 Agent 推理 |
| `backend/app/schemas` | API Pydantic DTO | SQLAlchemy ORM |
| `backend/app/models` | ORM 表与关系 | 业务流程 |
| `backend/app/services` | 查询、草稿、状态机等业务逻辑 | HTTP 处理 |
| `backend/app/tools` | Agent 可调用的受约束工具 | 绕过权限的直接查询 |
| `backend/app/agent` | Context、Trace、Harness、Model Gateway 和 LangGraph 图工作流 | 数据库业务实现 |
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
- 工具经过 Tool Registry，关键动作经过人工确认。
- LangGraph 条件边有明确终点，没有依赖模型输出的无限循环；Evaluator 位于回答与 reset 之后且只读。
- Runtime 首次 run 不能直接确认；续跑保持 task/member 隔离并且不会重复创建草稿。
- 前端成员页面在切换时取消旧请求，并区分 loading、empty、error；成员响应通过 `member_id` 二次检查。
- Agent UI 首次运行固定未确认，高风险不允许续跑；确认后只显示本地草稿，Trace/Evaluation 保持只读。
- 更新了对应的技术、接口、数据库、Agent 或测试文档。
- README 只更新对 GitHub 访客有价值的当前状态，不追加阶段流水账。

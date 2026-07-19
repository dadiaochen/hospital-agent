# 测试与代码审查指南

测试的目标不是只把绿灯跑出来，而是证明关键边界不会被后续改动悄悄绕开：成员隔离、来源约束、人工确认、schema 契约与医疗安全。

## 测试分层

| 层级 | 目录或模块 | 重点 |
| --- | --- | --- |
| 模型 | `test_models.py` | 表、关系、禁用字段、seed 可重复性。 |
| 契约 | `test_agent_contract_schemas.py` | Pydantic 字段、枚举、extra forbid、memory 门槛。 |
| 上下文 | `test_context_manager.py` | 角色视图、成员隔离、压缩和 reset。 |
| 工具 | `test_tool_registry.py`、`test_mock_tools.py`、`test_db_backed_tools.py` | 权限、schema、evidence、只读和失败 fallback。 |
| 草稿写入 | `test_confirmation_draft_tool.py` | 确认门禁、幂等、事务回滚、只写本地 draft。 |
| 草稿 API 状态机 | `test_confirmation_draft_api.py` | 显式确认、四类草稿、成员隔离、幂等确认/拒绝、非法终态转换和 OpenAPI。 |
| Harness | `test_deterministic_evaluator.py`、`test_harness_runner.py`、`test_harness_runtime.py` | 固定用例回放、评估规则和汇总报告。 |
| RAG | `test_hybrid_rag.py`、`test_vector_rag.py` | 固定安全/SOP 召回、来源版本、lazy provider、幂等索引、真实向量字段、回填、去重和失败降级。 |
| Model Gateway | `test_model_gateway.py` | deterministic 基线、HTTP adapter、schema、安全、超时和 fallback trace。 |
| LangGraph 工作流 | `test_langgraph_workflow.py` | 四场景路由、确认不可绕过、安全拦截、成员隔离、来源保留、reset/eval 与模型失败。 |
| Agent Runtime API | `test_agent_runtime_api.py` | 真实 DB tools、run/tool-call 持久化、冻结回放、幂等、续跑、隔离、安全与失败审计。 |
| API | `test_health.py`、`test_read_api.py`、`test_confirmation_draft_api.py` | 健康检查、只读资源和本地草稿状态机。 |
| 3A 前端 | `frontend/lib/api/client.test.ts`、`app/medicine-box/page.test.tsx`、Next production build | URL 编码、成员响应隔离、切换时清理旧数据、loading/empty/error、TypeScript 契约和全部页面编译。 |
| 3B Agent UI | `app/agent/page.test.tsx`、`components/RunTraceDetails.test.tsx`、API client 测试 | 首次未确认、显式续跑、高风险无按钮、成员切换清理、冻结产物隔离、错误/fallback 与评估字段。 |
| 3C Runtime E2E | `test_runtime_e2e_harness.py`、`app/agent/page.test.tsx` | 真实 API artifacts、确认续跑、无来源、工具失败、成员隔离、Trace 脱敏、API Guard 和四个 UI preset。 |
| 3D MVP 交付 | `test_mvp_demo_runner.py`、`scripts/start_demo.ps1` | 固定四场景顺序、真实 API 确认/阻断、脱敏报告、全新 Docker migration/seed 与四项健康检查。 |

## 运行命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest\all
python -m compileall backend\app backend\tests
```

只验证某个改动时，先跑对应测试文件；准备提交前再跑完整套件。Harness 的 fixture 位于 `backend/tests/fixtures/`，它们是 deterministic 演示输入，不是临床数据或线上评估数据。

前端验证：

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

组件测试使用 jsdom 和 mock HTTP，只证明 React 状态与渲染规则。自动测试之外还要做真实联调：启动 migration、seed、后端和前端，依次切换本人、父亲、母亲，核对 Network 请求和响应中的 `member_id`。知识 API 未合入时不能用 mock 页面冒充真实联调通过。

## 如何 review 一个改动

按这个顺序读 diff，通常最省力：

1. **范围**：它是否只实现路线图当前阶段？是否偷带下一阶段 API、图工作流或前端功能？
2. **契约**：新增输入输出是否由 Pydantic 描述？`extra="forbid"`、字段约束和失败信息是否足够明确？
3. **隔离**：是否从 execution context 而不是请求体信任 `user_id` / `member_id`？跨成员数据会不会混入？
4. **安全**：草稿是否仍需确认？有没有医疗建议越过“信息整理与流程辅助”的边界？
5. **可追踪性**：工具调用是否能产生 run、role、输入、输出、延迟、schema 和 fallback 记录？
6. **失败路径**：没有数据、权限不足、schema 失败、数据库失败时，是否返回可解释的 fallback，而不是模型猜测？
7. **测试与文档**：新增规则是否有一个正例、一个失败例和同步说明？

Review RAG 时还要区分相关性与事实正确性：`score` 只能用于排序；正文必须来自可回溯的数据库 chunk，向量后端返回的未知或错配 ID 不能被 Agent 使用。

Review 4A 时还要检查默认关闭是否真的不创建模型缓存；模型名、512 维 schema 和内容哈希是否一致；无索引/非 PostgreSQL/模型失败是否留下 fallback；索引是否只处理变化 chunk。Docker smoke 必须同时核验 pgvector extension、索引数量、语义命中和向量模式下四场景回归。

Review Model Gateway 时，不只看成功响应。至少验证 provider timeout、HTTP error、非法 JSON、目标 schema 失败、不安全输出和 fallback 二次失败；Trace 不得包含 API Key，失败的原始模型文本不得进入 Agent output。

Review LangGraph 时先画出节点和条件边，再看每个 node 的输入/更新字段。必须确认：业务角色由 intent 决定；工具仍经过 Registry；角色视图不含 raw conversation；SafetyAgent 在 confirmation 前；无显式确认不执行 draft handler；Evaluator 在 FinalAnswer 和 reset 后只读运行；图没有回边或未知终点。

Review Runtime 时继续检查：Router 是否只处理 HTTP；Service 是否从当前 user 校验 member/run；`tool_call_id` 是否能定位数据库审计行；首次请求能否绕过 `/continue`；同一待确认 run 换幂等键是否会产生重复草稿；失败 run 是否保留最小审计而不泄露异常原文。

Review 前端时先忽略样式，追踪 `page -> useMember -> api client -> endpoint`。确认成员切换会取消旧请求并清空旧 data，成员 response 不匹配时抛错而不是过滤；再检查 loading、empty、error、尚未查询和成功状态是否彼此独立。

Review Agent UI 时再检查首次 POST 是否固定为 `false`，确认按钮是否同时依赖后端待确认状态和未阻断 SafetyTrace，续跑是否提交新的确认幂等键。Trace 页面只能展示冻结产物，不能在浏览器重写 FinalAnswer 或重算 EvaluationResult；mock 组件测试不能冒充 3C E2E。

Review 3C Runner 时同时检查两个方向：运行时是否真的从 HTTP API 返回冻结产物；adapter 是否在评估前剔除敏感字段并拒绝 run/task/member 不一致。失败 ToolCall 可以是预期行为，但不得被计算为 evidence；Guard 请求只检查 HTTP 状态和错误码，不能伪造成功 RunTrace。

Review 3D 时从空环境思考：Compose 是否在无 `.env` 时有安全默认值；backend 是否保持 migration 配置路径并在 seed 后才启动；任何初始化失败是否阻止 healthy；Demo Runner 是否只走公开 API、固定四场景顺序、绝不续跑 blocked 结果；报告是否排除 member/run ID、答案正文和 Key。

## 当前常见风险

- 2G-2 Agent API/runtime 持久化已实现，但多模型线上质量验证、生产认证和外部医院/药店集成尚未实现，不能用 deterministic 成功结果替代真实验证。
- 3A/3B 页面已具备契约与组件测试；3C 已增加真实 Runtime API Harness 和四场景 UI 请求契约测试；3D 已实际验证 Docker production build、HTTP health 和固定四场景脚本。浏览器自动化仍未引入，UI 演示按 `DEMO_RUNBOOK.md` 手工 smoke。
- 2026-07-19 使用 npm 官方 registry 执行 `npm audit --omit=dev` 时，Next 14 生产依赖报告 1 项 high 和 1 项 moderate；官方自动修复建议升级到 Next 16，属于 major upgrade。当前本地演示不因此冒充生产安全版本，升级与回归应作为部署前独立任务处理。
- `agent_eval_report.example.md` 是固定 mock fixture 的计算结果，不是生产质量、临床效果或安全率证明。
- 本项目的配置示例只用于本地开发。生产环境必须从安全的环境变量或秘密管理系统注入连接信息和模型 Key。

## 3C 专项命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests\test_runtime_e2e_harness.py -q `
  -p no:cacheprovider --basetemp=var\pytest\3c

python -m app.agent.runtime_harness `
  --base-url http://localhost:8000 `
  --environment local_postgresql_deterministic `
  --run-key-prefix "3c-$((Get-Date).ToString('yyyyMMddHHmmss'))"
```

第一条使用 pytest SQLite 隔离环境；第二条要求 Docker PostgreSQL/FastAPI 已启动并 seed。两者都应运行，因为它们发现的问题类型不同。

## 3D 专项命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_mvp_demo_runner.py -q `
  -p no:cacheprovider --basetemp=var\pytest\3d

.\scripts\start_demo.ps1
docker compose ps
Get-Content var\demo\mvp-demo.md
```

pytest 使用隔离 SQLite 证明契约；一键脚本使用 Docker PostgreSQL 证明打包、初始化、网络、健康检查和公开 API。二者不能互相替代。

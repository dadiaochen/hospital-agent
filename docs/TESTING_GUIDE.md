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
| RAG | `test_hybrid_rag.py` | 固定安全/SOP 召回、来源版本、向量回填、去重和失败降级。 |
| Model Gateway | `test_model_gateway.py` | deterministic 基线、HTTP adapter、schema、安全、超时和 fallback trace。 |
| LangGraph 工作流 | `test_langgraph_workflow.py` | 四场景路由、确认不可绕过、安全拦截、成员隔离、来源保留、reset/eval 与模型失败。 |
| Agent Runtime API | `test_agent_runtime_api.py` | 真实 DB tools、run/tool-call 持久化、冻结回放、幂等、续跑、隔离、安全与失败审计。 |
| 4B 任务七安全确认 | `test_safety_confirmation.py`、`test_business_task_api.py` | Request/Action/Final Output 三层门禁、自动 DRAFT、状态迁移、重复确认、作用域/版本/幂等冲突和本地执行边界。 |
| 4B 任务八分层状态 | `test_business_task_api.py`、`test_task_checkpoint_cache.py`、`test_migration_chain.py` | PostgreSQL checkpoint、Redis 命中/失效/不可用回源、两次独立 run、parent run、确认版本和确认后偏好写入。 |
| API | `test_health.py`、`test_read_api.py`、`test_confirmation_draft_api.py` | 健康检查、只读资源和本地草稿状态机。 |
| 3A 前端 | `frontend/lib/api/client.test.ts`、`app/medicine-box/page.test.tsx`、Next production build | URL 编码、成员响应隔离、切换时清理旧数据、loading/empty/error、TypeScript 契约和全部页面编译。 |
| 3B Agent UI | `app/agent/page.test.tsx`、`components/RunTraceDetails.test.tsx`、API client 测试 | 首次未确认、显式续跑、高风险无按钮、成员切换清理、冻结产物隔离、错误/fallback 与评估字段。 |
| 4C-3 浏览器 E2E | `frontend/e2e/*.spec.ts`、Playwright + Docker Compose | 真实浏览器 HTTP 链路、续方/提醒/复诊材料、高风险拦截、成员切换、API 失败和确认门禁。 |

## 运行命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

只验证某个改动时，先跑对应测试文件；准备提交前再跑完整套件。Harness 的 fixture 位于 `backend/tests/fixtures/`，它们是 deterministic 演示输入，不是临床数据或线上评估数据。

生成当前固定用例指标：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_harness_runner.py backend\tests\test_deterministic_evaluator.py -q -p no:cacheprovider --basetemp=var\pytest
python -m app.agent.harness_runner
```

第二条命令会按固定 fixtures 重算 `docs/agent_eval_report.example.md`；面试和简历使用的指标解释、限制条件与本次回放记录见 [AGENT_EVAL_REPORT.md](AGENT_EVAL_REPORT.md)。不要把 fixture 中的 `latency_ms` 当成真实 wall-clock benchmark，也不要把 confirmation presence 当成人工采纳率。

任务七安全确认回归：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_safety_confirmation.py backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task7
```

这组测试应证明：危险请求不会进入业务工具；本地 DRAFT 不需要预先确认；没有显式确认不能进入 `CONFIRMED/EXECUTED`；同一 scope 的重复执行只 replay；成员、版本、请求指纹和幂等冲突都会阻断；危险 Model Gateway 候选不能成为用户答案。

任务八分层状态回归：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_business_task_api.py backend\tests\test_task_checkpoint_cache.py backend\tests\test_migration_chain.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task8
```

这组测试应证明：首次 run 写入版本化 PostgreSQL checkpoint；Redis miss/过期/异常会回源且不恢复 scratchpad；确认 run 使用同 task 的新 run 和 `parent_run_id`；陈旧 checkpoint/confirmation version 返回冲突；未完成人工确认或 source version 不匹配时不能写偏好。当前测试仍使用 deterministic provider，不代表 Redis/PostgreSQL 的真实 wall-clock 压测。

前端验证：

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

组件测试使用 jsdom 和 mock HTTP，只证明 React 状态与渲染规则。自动测试之外还要做真实联调：启动 migration、seed、后端和前端，依次切换本人、父亲、母亲，核对 Network 请求和响应中的 `member_id`。知识 API 未合入时不能用 mock 页面冒充真实联调通过。

4C-3 浏览器 E2E：

```powershell
Set-Location E:\project_code\hospital
docker compose up -d --build --wait --wait-timeout 300
Set-Location frontend
$env:E2E_BROWSER_CHANNEL='msedge'
npm run test:e2e
```

当前本机结果为 7 条通过。该结果证明固定 deterministic Docker 演示链路可重复，不代表真实 LLM 质量、临床安全或生产 SLO。API 失败场景使用 Playwright route 模拟 HTTP 503，专门验证前端错误映射，不冒充真实 Provider 故障率。

## 如何 review 一个改动

按这个顺序读 diff，通常最省力：

1. **范围**：它是否只实现路线图当前阶段？是否偷带下一阶段 API、图工作流或前端功能？
2. **契约**：新增输入输出是否由 Pydantic 描述？`extra="forbid"`、字段约束和失败信息是否足够明确？
3. **隔离**：是否从 execution context 而不是请求体信任 `user_id` / `member_id`？跨成员数据会不会混入？
4. **安全**：草稿是否无外部副作用，执行是否显式确认？请求、动作和最终输出三层门禁能否被绕过？
5. **可追踪性**：工具调用是否能产生 run、role、输入、输出、延迟、schema 和 fallback 记录？
6. **失败路径**：没有数据、权限不足、schema 失败、数据库失败时，是否返回可解释的 fallback，而不是模型猜测？
7. **测试与文档**：新增规则是否有一个正例、一个失败例和同步说明？

Review RAG 时还要区分相关性与事实正确性：`score` 只能用于排序；正文必须来自可回溯的数据库 chunk，向量后端返回的未知或错配 ID 不能被 Agent 使用。

Review Model Gateway 时，不只看成功响应。至少验证 provider timeout、HTTP error、非法 JSON、目标 schema 失败、不安全输出和 fallback 二次失败；Trace 不得包含 API Key，失败的原始模型文本不得进入 Agent output。

Review LangGraph 时先画出节点和条件边，再看每个 node 的输入/更新字段。必须确认：简单请求直达一个领域 Agent；复杂请求才进入一次性 Planner 和 bounded Supervisor；工具仍经过 Registry；角色视图不含 raw conversation；请求、动作、输出三层安全固定执行；草稿可自动创建但未经确认不执行；Evaluator 在 FinalAnswer 和 reset 后只读运行；循环有最大步数和确定终点。

Review Runtime 时继续检查：Router 是否只处理 HTTP；Service 是否从当前 user 校验 member/run；`tool_call_id` 是否能定位数据库审计行；首次 run 是否只创建无副作用 DRAFT；确认 run 是否从 PostgreSQL checkpoint 恢复并重新读取可变事实；幂等键和状态条件更新能否阻止重复执行；Redis 故障是否回源 PostgreSQL；失败 run 是否保留最小审计而不泄露异常原文。任务八已提供新业务链路的版本化 checkpoint、Redis 回源、parent run 和确认后偏好门槛；后续 review 继续关注并发、Provider 错误和真实 Docker 验收。

Review Tool/Provider 时先判断操作是否只读，再核对 retry policy。只有 timeout、rate-limit、临时 provider-unavailable 可有限重试；参数、权限、成员作用域、schema、业务冲突、内部错误和所有写工具不自动重试。失败响应必须没有 data/SourceRef，每次 attempt 必须可审计，mock/source 必须明确模拟身份，外部成功字段必须保持 false。

Review 前端时先忽略样式，追踪 `page -> useMember -> api client -> endpoint`。确认成员切换会取消旧请求并清空旧 data，成员 response 不匹配时抛错而不是过滤；再检查 loading、empty、error、尚未查询和成功状态是否彼此独立。

Review Agent UI 时要区分当前兼容契约与最终交互。最终页面展示已创建的本地 DRAFT，确认按钮同时依赖可执行状态和未阻断 SafetyTrace，确认会提交新的幂等键并显示 continuation run。Trace 页面只能展示冻结产物，不能在浏览器重写 FinalAnswer 或重算 EvaluationResult；mock 组件测试不能冒充最终阶段 4C 的浏览器 E2E。

## 当前常见风险

- 2G-2 Agent API/runtime 持久化已实现，但多模型线上质量验证、生产认证和外部医院/药店集成尚未实现，不能用 deterministic 成功结果替代真实验证。
- 4C-3 已在真实 PostgreSQL/Redis/FastAPI/Next.js Docker 栈上完成 7 条浏览器 E2E；4C-4 仍需把固定演示、全套报告和最终 README 收口。浏览器 E2E 仍不替代真实 Trace Harness、真实 LLM 质量或生产验收。
- 2026-07-19 使用 npm 官方 registry 执行 `npm audit --omit=dev` 时，Next 14 生产依赖报告 1 项 high 和 1 项 moderate；官方自动修复建议升级到 Next 16，属于 major upgrade。当前本地演示不因此冒充生产安全版本，升级与回归应作为部署前独立任务处理。
- `agent_eval_report.example.md` 是固定 mock fixture 的计算结果，不是生产质量、临床效果或安全率证明。
- 本项目的配置示例只用于本地开发。生产环境必须从安全的环境变量或秘密管理系统注入连接信息和模型 Key。

## 4B 任务三/四回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_vector_rag.py `
  backend\tests\test_hybrid_rag.py `
  backend\tests\test_migration_chain.py `
  backend\tests\test_model_gateway.py `
  backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-4b
```

任务三必须验证 canonical provider、hash/schema 变化重建、pgvector migration/HNSW 定义、来源 metadata 和关键词降级。任务四必须验证三条业务域都有成功的 `model_call_trace`，无 Key 默认 deterministic，primary provider 失败时 fallback，SafetyAgent 阻断路径不被模型绕过。

## 4B 任务五回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_orchestration_contracts.py `
  backend\tests\test_complexity_router.py `
  backend\tests\test_agent_contract_schemas.py `
  backend\tests\test_langgraph_workflow.py -q -p no:cacheprovider `
  --basetemp=var\pytest\4b-task5
```

任务五必须覆盖：简单请求直达一个领域 Agent、跨领域请求进入 Planner 候选、最多三步的依赖校验、非法角色/动作拒绝、三阶段 SafetyDecision，以及高风险和歧义输入不调用 Supervisor。Router 本身不访问 LLM、数据库、Provider、Tool Registry 或 LangGraph。

## 4B 任务六回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_domain_orchestration.py `
  backend\tests\test_orchestration_contracts.py `
  backend\tests\test_complexity_router.py -q -p no:cacheprovider `
  --basetemp=var\pytest\4b-task6
```

任务六必须覆盖：三个领域 Agent 的角色白名单和最小输入、简单请求直达、复杂请求一次性 Planner、串行依赖、最大步数、每角色调用上限、有限重试、降级、澄清、失败终止和成员隔离。测试不应把 deterministic 占位 facts 当作医疗事实，也不应调用数据库、LLM、Provider、Tool Registry 或 LangGraph。

## 4B 任务九回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest `
  backend\tests\test_provider_adapters.py `
  backend\tests\test_provider_reliability.py `
  backend\tests\test_tool_registry.py `
  backend\tests\test_business_task_api.py -q -p no:cacheprovider `
  --basetemp=output\pytest-task9
```

必须检查：validation/permission/schema/business-conflict 不重试；只读 timeout/rate-limit/provider-unavailable 不超过固定次数；写工具固定一次；三类重点 Provider 的 mock 输出通过强 schema；失败没有 data/source；文档来源保留 version/parser/source location；药房、医院和问诊不声称外部写入成功。Windows 遇到旧 `var/pytest` ACL 问题时使用 `output` 下全新唯一 basetemp，不删除或复用无权限目录。

## 4B 最终验收矩阵

- 编排：直接路由、复杂路由、最大步数、非法角色、非法工具和无进展终止。
- 安全：请求 Guard、动作 Policy Guard、最终输出 SafetyAgent，分别覆盖正反例。
- 状态：PostgreSQL checkpoint、Redis 命中/失效/不可用回源、两次独立 run、并发确认和幂等 replay。
- Provider：三类重点 Provider 的 timeout、retry、schema、权限、成员和来源转换。
- RAG：FastEmbed/pgvector、关键词降级、RRF、版本错配、来源支持和成员隔离。
- Harness：至少 32 条固定用例，并对单 Agent、固定路由和 bounded Supervisor 做同条件 A/B/C 消融。

其中任务九 Provider 离线可靠性、任务十 RAG/隔离/Observation、任务十一 32 条 deterministic Harness 和任务十二本机 Docker 后端验收已完成。任务十二报告记录 baseline 19/19、Redis 故障回源 18/18，以及本机 wall-clock 样本；这些结果仍不能写成生产 SLO、临床安全指标或真实模型质量。

## 4B 任务十回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:PYTHONPYCACHEPREFIX=(Resolve-Path 'output').Path + '\pycache-task10'
python -m pytest backend\tests\test_agent_contract_schemas.py backend\tests\test_hybrid_rag.py backend\tests\test_vector_rag.py backend\tests\test_db_backed_tools.py backend\tests\test_task_checkpoint_cache.py backend\tests\test_model_gateway.py backend\tests\test_task10_observability.py backend\tests\test_business_task_api.py backend\tests\test_runtime_e2e_harness.py -q --basetemp output\pytest-task10
```

必须检查：RRF 只融合 rank；raw score 仅用于审计；文档/分块/embedding schema 过期时降级；用户、成员和资源在 SQL 同条件约束；额外 Prompt/身份字段被拒绝；跨成员缓存值成为 miss；Observation 不包含请求正文、工具/Provider payload、Prompt、答案正文或凭据。2026-07-29 本地执行结果为 84 条定向和 287 条后端全量测试通过；这不是线上性能或临床质量指标。

## 4B 任务十一回归

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:PYTHONPYCACHEPREFIX=(Resolve-Path 'output').Path + '\pycache-task11'
python -m app.agent.ablation_harness
python -m pytest backend\tests\test_ablation_harness.py -q -p no:cacheprovider --basetemp output\pytest-task11
python -m pytest backend\tests -q -p no:cacheprovider --basetemp output\pytest-task11-full
python -m compileall backend\app backend\tests
```

任务十一专项测试 6 项、完整后端 293 项通过是任务十二前的基线；任务十二真实环境结果见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。Review 报告时必须检查：32 条八类计数是否精确；三组 `fairness_config_id` 是否一致；Safety/隔离/RAG 是否没有被策略偷偷改变；简单与复杂是否分开；token usage 缺失时是否保持 `N/A`；fixture latency 和本机 wall-clock 是否没有被写成生产性能。

## 4B 任务十二真实后端验收

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
docker compose up -d --build --wait --wait-timeout 300
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

验收脚本同时检查 Alembic head、seed 数据、pgvector 向量维度、三条业务 API、知识检索 422 映射、并发确认和前端 health。Redis 故障模式会验证 API 从 PostgreSQL 恢复 checkpoint；执行后必须启动 Redis。脚本是操作员验收，不属于业务代码，也不调用 LLM。

## 4B 任务十三收口回归

任务十三最终复核结果：后端 `297 passed`、`compileall` 通过；前端 Vitest `23 passed`、TypeScript typecheck 通过、Next.js production build 通过。完整收口记录见 [任务十三 4B 收口报告](task13_4b_closeout_report.md)。

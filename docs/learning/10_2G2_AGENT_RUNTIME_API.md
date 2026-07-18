# 2G-2 学习：从一个 HTTP 请求到可回放 Agent Run

这一章把你当作第一次开发完整后端项目的新手。目标不是背代码，而是能回答：一个 Agent 请求如何经过 FastAPI、Pydantic、Service、LangGraph、Tool Registry、SQLAlchemy 和 Evaluator，最后变成可查询的数据库记录。

## 1. 先建立整体地图

当客户端调用 `POST /api/agent-runs` 时，代码不是“一个函数从头做到尾”，而是按职责分层：

```text
Postman / Frontend
  -> FastAPI Router：HTTP 是什么、请求是否合法
  -> Pydantic API DTO：字段类型和边界
  -> AgentRuntimeService：业务编排、作用域、幂等和事务
  -> LangGraphAgentWorkflow：Agent 节点顺序与条件路由
  -> Tool Registry：角色、allowed_tools、确认和 schema 门禁
  -> SQLAlchemy Service / ORM：读取或写入 PostgreSQL
  -> FinalAnswer / RunTrace / Evaluator
  -> AgentRuntimeService：把冻结产物写回数据库
  -> FastAPI Response DTO：返回 JSON
```

为什么不只写一个 Python 函数？因为 HTTP、业务规则、Agent 编排和数据库事务的变化原因不同。分层让你能单独测试“请求字段错了”“成员越权了”“工具失败了”“图路由错了”或“数据库提交失败了”。

## 2. 你需要先懂的五个概念

### 2.1 HTTP API

API 是不同程序之间约定的入口。`POST` 表示客户端提交数据来创建一次运行；路径 `/api/agent-runs` 表示资源类型。FastAPI 是实现这个 HTTP 约定的 Python 框架，`@router.post(...)`、依赖注入、自动 Swagger 和 response model 都来自 FastAPI，不是 Python 自带语法。

### 2.2 Pydantic DTO

网络收到的是不可信 JSON。Pydantic DTO 把它转换成有类型的 Python 对象，并拒绝未知字段、空字符串和错误布尔值。DTO 不是数据库表：它描述一次请求或响应允许出现什么。

### 2.3 Service

Service 是用例的负责人。Router 只把已校验参数交给它；Service 决定先校验成员、怎样生成 run ID、什么时候提交、调用哪个 workflow、成功或失败写什么。

### 2.4 ORM 与 Session

SQLAlchemy ORM 让 Python 类映射数据库表。`AgentRun(...)` 只是创建内存对象；`session.add(run)` 把它放进待提交集合；`session.commit()` 才产生数据库事务。Session 还负责查询、回滚和刷新对象。

### 2.5 冻结产物

Agent 运行时 state 会变化，不适合直接拿来复盘。RunTrace 把“实际发生了什么”冻结：成员、意图、工具、来源、安全、答案和延迟。Evaluator 只读这个对象，因此不能事后悄悄改答案。

## 3. 按顺序打开这些文件

1. [agent_runtime.py](../../backend/app/schemas/agent_runtime.py)：先看 HTTP 输入输出字段。
2. [agent_audit.py](../../backend/app/api/routes/agent_audit.py)：看路径、HTTP 方法和依赖。
3. [agent_runtime_service.py](../../backend/app/services/agent_runtime_service.py)：看完整用例和事务。
4. [workflow_schemas.py](../../backend/app/agent/workflow_schemas.py)：看 Service 传给图什么。
5. [langgraph_workflow.py](../../backend/app/agent/langgraph_workflow.py)：看节点怎样运行。
6. [db_tools.py](../../backend/app/tools/db_tools.py)：看工具怎样获得真实证据。
7. [runtime_schemas.py](../../backend/app/agent/runtime_schemas.py)：看最终保存哪些最小产物。
8. [test_agent_runtime_api.py](../../backend/tests/test_agent_runtime_api.py)：看系统如何被证明是正确的。

不要一开始就从 400 行 Service 逐字硬读。先知道输入、输出和总流程，再进入细节。

## 4. 第一步：读请求 DTO

```python
class AgentRunCreateRequest(ApiSchema):
    member_id: str
    idempotency_key: str
    user_input: str
    medication_name: str | None = None
    city: str | None = None
    human_confirmation_granted: Literal[False] = False
```

逐字段理解：

- `member_id`：这次服务家庭里的谁。它不是 user ID。
- `idempotency_key`：客户端给一次业务请求的稳定标识。网络重试不会重复运行。
- `user_input`：这一次用户目标，不是完整聊天历史。
- `medication_name` / `city`：工具可能需要的结构化筛选条件；`| None` 表示可选。
- `Literal[False]`：不是普通 bool，而是只允许 false。首次请求不能顺便声称“用户已经确认”。

`field_validator` 中的 `" ".join(value.split())` 会压缩首尾和连续空白。这样 `"  abc  "` 与 `"abc"` 产生同样的规范值，幂等 fingerprint 不会因无意义空格不同。

续跑 DTO 的 `Literal[True]` 则要求客户端明确确认。为什么不直接用默认 true？因为关键动作不能靠缺省值猜用户同意。

## 5. 第二步：读 Router

在 `create_agent_run()` 固定问五个问题：

1. HTTP 方法和路径是什么？`POST /api/agent-runs`。
2. 参数从哪里来？`request` 来自 JSON 经 Pydantic 校验；`db` 和 `demo_user` 由 FastAPI `Depends` 创建。
3. 调用哪个 Service？`AgentRuntimeService(...).create_run(...)`。
4. 返回哪个 DTO？`AgentRunExecutionResponse`。
5. Router 有没有 SQL 或 Agent 决策？没有，这正是分层要求。

`db: DbSession` 不是数据库本身。它是当前请求使用的 SQLAlchemy Session，由 `get_db()` 依赖提供。`demo_user: DemoUser` 也是依赖注入结果：服务端根据 `DEMO_USER_PHONE` 查询当前用户，客户端不能伪造 user ID。

## 6. 第三步：逐段读 create_run

### 6.1 成员作用域

```python
self._require_scoped_member(member_id)
```

查询条件同时包含 `FamilyMember.id == member_id` 和 `FamilyMember.user_id == self.user_id`。只按 member ID 查不够，因为那会让当前用户读取其他账户成员。

### 6.2 稳定 run ID

```python
run_id = uuid5(namespace, f"{user_id}:{idempotency_key}")
```

UUID5 对相同输入总得到相同 ID。普通 UUID4 每次随机，无法仅靠幂等键定位旧 run。namespace 防止项目中别的 UUID5 用途与它碰撞。

### 6.3 请求 fingerprint

请求字段先按 key 排序转 JSON，再做 SHA-256。相同 key + 相同正文返回旧结果；相同 key + 不同正文返回 `409`。只看 key 而不比正文会把两个不同请求错误地当作同一件事。

### 6.4 先保存 running

Service 先创建 `AgentRun(status="running")` 并 commit。这样 workflow 抛异常时，系统还能把这条 run 更新为 failed。若等全部成功才第一次写数据库，失败请求会完全消失，无法审计。

### 6.5 构造 WorkflowRunRequest

它把 HTTP DTO 转成 Agent 内部契约。注意 Router DTO、Workflow DTO、ORM 是三种不同模型：

- HTTP DTO 面向客户端。
- Workflow DTO 面向图执行。
- ORM 面向数据库表。

字段相似不代表可以混用，因为它们的权限和生命周期不同。

## 7. 第四步：真实工具怎样被注入

```python
workflow = LangGraphAgentWorkflow(
    tool_registry=create_db_tool_registry(db, include_confirmation_tools=True)
)
```

这是依赖注入的另一个例子。LangGraph 类不知道工具底层是 mock 还是 PostgreSQL；它只依赖统一 ToolRegistry 契约。单元测试传 mock registry，Runtime 传 DB registry。

一次 `query_medicine_box` 会经历：

1. LangGraph 根据 plan 选择 ReminderAgent 或 RefillAgent。
2. ContextManager 只给该角色最小 allowed tools。
3. ToolRegistry 校验工具名、角色、allowed tools 和输入 schema。
4. DB tool 检查 execution context 中的 member。
5. 查询 service 用 SQLAlchemy Session 读取 MedicineBoxItem。
6. 输出经 Pydantic output schema 校验。
7. Registry 返回 ToolResult，包含成功、来源、延迟和失败信息。

所以“Agent 调工具”不是模型随便调用一个 Python 函数，而是一条受契约、权限和审计约束的调用链。

## 8. 第五步：为什么首次运行不创建草稿

Planner 可以计划 `create_confirmation_draft`，但 `human_confirmation_granted=false` 时 confirmation node 不调用工具。FinalAnswerTrace 标记：

```json
{
  "waiting_for_user_confirmation": true,
  "human_confirmation_present": false,
  "action_status": "awaiting_confirmation"
}
```

此时 EvaluationResult 不应说“漏调草稿工具”。因为该工具本轮依法不能执行。Operational ExpectedCase 只要求本轮允许执行的工具；等 `/continue` 显式确认后，才把 draft tool 纳入本轮期望。

## 9. 第六步：保存 ToolCall 和冻结产物

每个 ToolResult 变成一条 AgentToolCall。它记录 role、工具名、输入、输出、耗时、成功、错误类型、fallback 和 schema 状态。

`build_tool_call_id(run_id, index, tool_name)` 生成稳定 UUID。Context 中 ToolEvidenceRef 的 `tool_call_id` 使用同一个函数，所以你从来源引用可以真正查询到数据库行，而不是只有一个不可解析的字符串。

PersistedRunArtifacts 保存 reset 后仍需要的内容，不保存运行时噪声。它还保存脱敏 ModelCallTrace，用来查看 provider、fallback、schema/safety 和耗时，但不保存 prompt、Key 或 provider 原文。它有 schema version，是因为未来字段变化时，读取者需要知道用哪个契约解释旧 JSON。

## 10. 第七步：续跑不是继续使用旧 state

调用 `/continue` 后：

1. Service 查询上一 run，要求属于当前用户且状态是 needs_confirmation。
2. continuation run ID 只由当前用户和 previous run 决定，因此同一上一 run 不能创建多个续跑草稿。
3. 新 run 沿用 task ID 和 member ID。
4. WorkflowResumeContext 只携带上一 RunSummary 和 WorkflowPlan。
5. 新 ContextEnvelope 把上一 summary 和 source IDs 作为指针，不复制旧 raw conversation 或 scratchpad。
6. DB tools 重新查询当前数据。
7. Tool Registry 看到显式 true 后，才允许 create_confirmation_draft。
8. 成功后 FinalAnswer 标记 `human_confirmation_present=true`，run 变为 completed。

task ID 表示“一件可跨多次运行完成的任务”，run ID 表示“这件任务的一次执行”。这是理解续跑最重要的区别。

## 11. 第八步：Evaluator 为什么是只读

Evaluator 接收 Frozen RunTrace 和 ExpectedCase，只返回 EvaluationResult。它没有 Session、没有 Tool Registry、没有 `state.update()` 能力。即使评估失败，它也只能写 failure reasons；是否持久化由 Runtime Service 决定。

测试中把 RunTrace 字段重新赋值会触发 Pydantic ValidationError。这证明的是对象不可变边界，不代表系统已经达到真实医疗安全指标。

## 12. 用 Postman 跑通完整流程

### 12.1 启动环境

按 [开发者指南](../DEVELOPER_GUIDE.md) 启动 PostgreSQL、迁移、seed 和后端。确认：

- `GET http://localhost:8000/health` 返回 200。
- `http://localhost:8000/docs` 能打开 Swagger。
- `.env` 的 `DEMO_USER_PHONE` 对应 seed 中的 demo user。

### 12.2 找到 member ID

在 Postman 新建 GET：

```text
http://localhost:8000/api/family-members
```

发送后，从响应选择父亲或母亲的 `id`。不要把 user ID 当成 member ID。

### 12.3 创建首次 run

新建 POST：

```text
http://localhost:8000/api/agent-runs
```

Body 选择 raw -> JSON，填写：

```json
{
  "member_id": "把这里替换为真实 member id",
  "idempotency_key": "postman-reminder-start-001",
  "user_input": "请创建每天早晚的用药提醒。",
  "medication_name": "seed 中存在的药名",
  "human_confirmation_granted": false
}
```

检查：HTTP 201、`run.status=needs_confirmation`、`idempotent_replay=false`、FinalAnswer 等待确认。记录 `run.id` 和 `artifacts.task_id`。

### 12.4 查询工具调用

```text
GET http://localhost:8000/api/agent-runs/{run_id}/tool-calls
```

检查 `query_medicine_box` 等只读工具、成功状态和 output 中的 `source_id`。首次运行不应出现 `create_confirmation_draft`。

### 12.5 查询冻结产物

```text
GET http://localhost:8000/api/agent-runs/{run_id}/artifacts
```

检查 RunTrace、ModelCallTrace、RunSummary、ToolEvidenceRef、RAG refs、SafetyTrace 和 EvaluationResult。响应不应包含 `request_fingerprint`、raw conversation、scratchpad、完整 prompt、provider 原文或 Key。

### 12.6 确认续跑

新建 POST：

```text
http://localhost:8000/api/agent-runs/{首次 run_id}/continue
```

```json
{
  "idempotency_key": "postman-reminder-confirm-001",
  "confirmation_message": "我确认创建这份本地提醒草稿。",
  "human_confirmation_granted": true
}
```

检查：HTTP 201、状态 completed、task ID 与首次相同、run ID 不同、`resumed_from_run_id` 指向首次 run、`external_action_status=not_submitted`、工具调用包含 create_confirmation_draft。

### 12.7 验证幂等与失败路径

- 原样重发首次请求：run ID 相同，`idempotent_replay=true`。
- 同一首次幂等键修改 user_input：应返回 409。
- 首次请求把 confirmation 改成 true：应返回 422。
- 对同一上一 run 换一个确认幂等键再次续跑：应返回 409，不能多一份草稿。
- 使用不属于 demo user 的 member：应统一返回 404。

## 13. 如何 review 这组代码

按下面顺序，不要只看成功路径：

1. Router 是否出现 SQL、Tool Registry 或 provider 调用？出现就是分层错误。
2. user ID 是否来自服务端依赖，而不是请求 JSON？
3. member/run 查询是否同时带当前 user 条件？
4. 首次请求是否可能传 true 绕过续跑？API 和 Service 是否双重保护？
5. 相同幂等键不同正文是否冲突？
6. 同一待确认 run 是否可能用不同 key 生成两个草稿？
7. ToolEvidenceRef 的 tool_call_id 是否真能定位 AgentToolCall？
8. RAG 是否保存真实 document/chunk/version，而不是只有模型描述？
9. raw_state 是否包含旧 scratchpad、完整 prompt、Key 或 provider 原文？
10. 高风险是否在 draft 前 blocked？
11. Evaluator 是否只读，失败时是否只返回 reasons？
12. 异常后是否仍有 failed run，响应是否隐藏内部错误文本？

## 14. 你可以自己完成的练习

1. 在纸上画出首次 reminder 的函数调用链，并标出每一步属于 FastAPI、Pydantic、项目 Service、LangGraph、SQLAlchemy 还是数据库。
2. 在 `test_agent_runtime_api.py` 新增一个真实 refill API 用例，证明处方、药箱和库存来源均可回放。
3. 写一条测试：续跑的 task ID 与上一 run 相同，但 ToolEvidenceRef 的 run ID 必须是新的 run。
4. 用 Postman 制造一个不存在药箱数据的成员，观察 ToolResult、EvaluationResult 和 run 状态怎样表达失败。
5. Review `raw_state` JSON，解释每个字段为什么需要持久化、为什么 role views 不应该进去。

## 15. 面试表达

可以这样讲：

> 我把纯 LangGraph 编排与 HTTP/事务分开，用 AgentRuntimeService 注入真实数据库工具并持久化 run、tool call 和版本化冻结产物。首次运行与确认续跑采用不同契约，续跑只恢复 RunSummary 和 source pointers、重新查询 DB evidence；稳定 run/tool-call ID 和请求 fingerprint 支持可回放审计与幂等，同时防止同一待确认任务重复创建草稿。Evaluator 只读冻结 Trace，外部动作始终保持 not_submitted。

不要说“已经上线”“调用了真实医院”“真实模型 0 幻觉”或“安全召回 100%”。当前证明的是工程边界和 deterministic 回归，不是临床效果。

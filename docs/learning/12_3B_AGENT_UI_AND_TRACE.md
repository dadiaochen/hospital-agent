# 3B 学习：从输入框到可审计 Agent Run

这篇文档把 3B 当作一条完整的前后端学习链路。你不需要一次读懂所有 React 语法，先反复回答：数据从哪里来、经过哪个契约、谁能改状态、失败在哪里显示。

## 1. 先画出一次请求

```text
React form
  -> api.createAgentRun
  -> HTTP POST /api/agent-runs
  -> FastAPI AgentRunCreateRequest
  -> AgentRuntimeService
  -> LangGraph + Tool Registry + SafetyAgent
  -> database audit + frozen artifacts
  -> AgentRunExecutionResponse JSON
  -> React state
  -> AgentRunResult
```

前端不是 Agent 本身。它收集输入和展示结果；业务执行发生在后端。后端也不是直接让模型写数据库，而是通过 Service、LangGraph 和 Tool Registry 分层执行。

## 2. 第一步：读 TypeScript 契约

先打开 `frontend/lib/api/types.ts`，找到：

```ts
export type AgentRunCreateRequest = {
  member_id: string;
  idempotency_key: string;
  user_input: string;
  human_confirmation_granted: false;
};
```

`false` 不是普通 `boolean`，而是字面量类型：TypeScript 只允许它为假。这与后端 `Literal[False]` 形成两道约束，防止首次请求绕过确认流程。

继续读 `AgentRunExecution`。它包含运行摘要 `run` 和冻结产物 `artifacts`。运行摘要适合列表，冻结产物适合审计。不要只看 FinalAnswer，还要看来源、安全和 evaluation。

## 3. 第二步：读 API client

打开 `frontend/lib/api/client.ts`，先找 `requestJson`：

```ts
const response = await fetch(`${API_BASE_URL}${path}`, {
  method,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
  body: JSON.stringify(options.body),
});
```

`fetch` 是浏览器发送 HTTP 的标准 API。`JSON.stringify` 把 JavaScript 对象编码成 HTTP body。FastAPI 收到后用 Pydantic 校验，再传给 Router 函数。

然后看 `createAgentRun`。它先 POST，再检查 `run.member_id` 和所有冻结产物的成员引用。为什么后端检查后前端还检查？因为前端要在异常响应进入屏幕前停止展示，这叫纵深防御。

## 4. 第三步：读 React 表单状态

打开 `frontend/app/agent/page.tsx`，按下面顺序读：

1. `useState`：页面当前保存了哪些值？
2. `useRef`：哪些值变化时不需要重新渲染？
3. `submitRun`：点击提交后按什么顺序执行？
4. `canConfirm`：确认按钮由哪些后端状态控制？
5. JSX：每种 state 最后显示成什么？

`execution` 的初始值是 `null`。请求成功后：

```ts
const result = await api.createAgentRun(...);
setExecution(result);
```

React 发现 state 改变后重新渲染，于是结果组件从“不显示”变成“显示”。这就是最基本的 React 单向数据流。

## 5. 为什么幂等键放在 useRef

用户点击提交后网络可能断开，但后端实际上已经创建 run。如果重试生成新键，可能创建第二次运行。页面把未成功请求的 key 放进 `useRef`：

```ts
startKeyRef.current ??= createIdempotencyKey("run");
```

`??=` 表示“当前为空时才赋值”。失败后保留旧 key，成功后才清空。`useRef` 改变不会触发页面重渲染，适合保存请求控制值。

## 6. 为什么确认不是普通按钮

`canConfirm` 同时检查 run 状态、FinalAnswerTrace 和 SafetyTrace。仅仅看到文案里有“请确认”不够，因为自然语言不能作为权限判断。

用户还要勾选本地草稿说明。续跑请求的 `true` 表示用户确实做了当前决定，不表示医生确认。SafetyAgent 已阻断时，`canConfirm` 必须为假，避免 UI 绕过事前安全拦截。

## 7. 第四步：读结果组件

打开 `frontend/components/AgentRunResult.tsx`，把页面分成四块：

- 状态：run status、intent、安全拦截；
- 答案：冻结 FinalAnswerTrace；
- 来源：ToolEvidenceRef 与 RAGSourceRef；
- 动作：action status 与 `not_submitted`。

`source_id` 是审计指针。后续调查某个事实时，可以沿 source ID 找到工具调用或知识 chunk。没有来源时，组件明确显示无来源，而不是编造一个引用。

## 8. 第五步：读 Trace 详情

打开动态路由 `frontend/app/agent-runs/[id]/page.tsx`。`[id]` 表示 URL 中这一段是变量，例如 `/agent-runs/run-123` 的 `params.id` 是 `run-123`。

页面用 `Promise.all` 并行请求运行摘要、工具调用和冻结产物。三者互不依赖，并行能减少等待时间。返回后还检查所有 `run_id` 一致，否则停止展示。

再打开 `RunTraceDetails.tsx`。它不计算新指标，只把后端产物映射到 UI：工具失败显示 error/fallback，SafetyTrace 显示阻断，EvaluationResult 显示事后评估，ModelCallTrace 显示 provider 与 fallback。

## 9. 怎样 review 这段代码

不要先看颜色和 CSS，按数据流 review：

1. 请求类型是否与 Pydantic 一致？
2. 首次确认是否固定为 false？
3. `member_id` 是否来自唯一 MemberProvider？
4. response 是否在渲染前检查成员？
5. blocked 是否可能进入确认续跑？
6. source pointer 是否保留？
7. Trace/Evaluation 是否只读？
8. 文案是否把 local draft 说成外部成功？

然后再看失败状态、按钮禁用、移动端布局和可访问标签。

## 10. 在浏览器中跑通

从仓库根目录启动数据库并初始化：

```powershell
docker compose up postgres redis -d
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
```

终端 A 启动后端：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m uvicorn app.main:app --reload --app-dir backend
```

终端 B 启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:3000/agent`。顶部先选正确成员，再点击模板并运行。按 `F12` 打开 Network：检查首次 POST 的 member、幂等键和 false；确认后检查 `/continue` 的 true；点击“查看完整 Trace”确认三个 GET 都成功。

## 11. 用 Postman 拆开验证

1. 新建 `POST http://localhost:8000/api/agent-runs`。
2. Body 选 raw / JSON，填写 member ID、幂等键、输入和 `human_confirmation_granted:false`。
3. 发送后记录 `run.id`、`task_id`、status 和 source IDs。
4. 调用 `GET /api/agent-runs/{run_id}/artifacts`，核对冻结答案和 evaluation。
5. 调用 `GET /api/agent-runs/{run_id}/tool-calls`，核对角色、工具和 source。
6. 只有 status 为 `needs_confirmation` 时，再 POST `/api/agent-runs/{run_id}/continue`，提交新的幂等键、确认说明和 `true`。
7. 核对新 run 的 `resumed_from_run_id`、相同 task、恢复来源以及 `external_action_status=not_submitted`。

把首次请求直接改成 true 应得到 422；对 blocked run 续跑或对不属于当前用户的 run 查询应失败。失败用例和成功用例同样重要。

## 12. 面试亮点与边界

可以说：

> 使用 Next.js/React/TypeScript 实现 Agent 对话与审计 UI，将首次未确认运行、确认续跑、冻结答案、来源引用、安全标记和 EvaluationResult 连接到真实 FastAPI Runtime；通过成员切换清理、response scope 校验和高风险无确认入口降低串扰与越权风险。

不要把历史 3B 演示页描述成已经接入真实医院、完成生产鉴权或达到某个 Agent 安全指标。3B 当时展示的是 deterministic 运行的单次评估结果；真实 RunTrace Harness、完整浏览器 E2E 和成熟患者端现在统一由最终 4C 验收。

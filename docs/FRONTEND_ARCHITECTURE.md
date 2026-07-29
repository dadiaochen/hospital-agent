# 前端架构与数据页面

> 本文记录当前 3A/3B 页面和 4C-1 患者端壳层。4B 任务七后端状态机已经完成；4C-2 仍需要把三条业务线完整迁移为“展示自动生成的本地 DRAFT，用户确认执行”，并展示首次 run 与 continuation run 的关联。

## 1. 目标与边界

3A/3B 前端使用 Next.js App Router、React、TypeScript 和 Tailwind CSS，把 FastAPI 读取接口与 Agent Runtime API 变成可演示页面。它负责展示、查询条件、加载状态、显式人工确认和客户端隔离检查，不负责数据库查询、医疗判断、Agent 编排或外部业务提交。

3A 的深度页面是家庭成员、家庭药箱、续方/复诊与提醒，基础页面是购药库存、知识检索和 Agent run 列表。3B 在此基础上增加真实 Agent 输入、冻结答案、确认续跑与 Run Trace 详情；按钮只调用已有 Runtime API，不模拟后端成功。4C-1 将首页改造成患者端健康服务入口：搜索、事务分类、快捷入口、成员状态和安全说明更接近用户熟悉的健康服务信息架构，但不引入交易、支付或促销逻辑。

## 2. 数据流

```text
Browser
  -> MemberProvider fetches GET /api/family-members
  -> user selects one member_id
  -> page calls typed api method
  -> FastAPI validates request and demo-user scope
  -> service queries PostgreSQL
  -> Pydantic response DTO
  -> frontend validates returned member_id
  -> loading / empty / error / data view
```

后端仍是成员权限的最终边界。前端的 `assertMemberScoped` 是额外防线：成员类响应中只要出现与当前选择不同的 `member_id`，页面就拒绝展示并进入错误态。它不能替代后端鉴权，但能避免 UI 在异常响应下静默串数据。

## 3. 模块职责

| 模块 | 职责 |
| --- | --- |
| `frontend/lib/api/types.ts` | 镜像后端 Pydantic response 的 TypeScript 类型。 |
| `frontend/lib/api/client.ts` | 统一 base URL、GET/POST、错误解析、URL 编码和成员隔离检查。 |
| `frontend/lib/idempotency.ts` | 为首次运行和确认续跑生成浏览器侧幂等键。 |
| `frontend/lib/useApiResource.ts` | 处理请求取消、loading、error、data 和 reload。 |
| `MemberProvider` | 加载成员列表并维护唯一的当前 `member_id`。 |
| `MemberSwitcher` | 让用户切换本人、父亲、母亲。 |
| `AsyncContent` | 统一 loading、empty 和 error 视觉状态。 |
| `app/**/page.tsx` | 组合页面需求，不直接拼接 API base URL。 |
| `AgentRunResult` | 展示冻结答案、Tool/RAG 来源、安全标记和外部动作状态。 |
| `RunTraceDetails` | 只读展示角色、工具、延迟、错误、fallback、模型 Trace 与评估结果。 |
| `app/page.tsx` | 患者端首页；只负责导航和展示入口，不在浏览器推断医疗事实。 |

## 4. 成员切换与隔离

`MemberProvider` 首次加载成员列表后选择第一位成员。切换选项只更新 `selectedMemberId`；每个成员页面把它放进自己的 `resourceKey`，因此 React effect 会取消旧请求、清空旧数据并为新成员重新请求。

成员类 API 方法在返回后执行以下检查：

```ts
assertMemberScoped(result.items, memberId, "家庭药箱");
```

检查失败抛出 `context_isolation_failed`。页面不会通过前端过滤把错误记录悄悄隐藏，因为那会掩盖后端作用域缺陷。

## 5. API 与页面矩阵

| 页面 | API | 成员作用域 |
| --- | --- | --- |
| 家庭成员 | `/api/family-members`、`/{member_id}/health-profile` | 是 |
| 家庭药箱 | `/{member_id}/medicine-box` | 是 |
| 续方与复诊 | `/{member_id}/prescriptions`、`/api/confirmation-drafts?member_id=` | 是 |
| 提醒任务 | `/api/confirmation-drafts?member_id=` | 是 |
| 购药信息 | `/{member_id}/purchase-records`、`/api/pharmacy-inventory` | 历史记录是；库存候选不是成员私有数据 |
| 知识检索 | `/api/knowledge/search?q=&category=` | 否；结果必须有 `source_id` |
| Agent runs | `/api/agent-runs?member_id=` | 是 |
| Agent 对话 | `POST /api/agent-runs`、`POST /api/agent-runs/{run_id}/continue` | 是；首次固定未确认，续跑必须显式确认 |
| Run Trace | `/{run_id}`、`/{run_id}/tool-calls`、`/{run_id}/artifacts` | 是；页面拒绝跨成员冻结产物 |

知识页只消费 2E-1 学习题定义并已集成的契约。前端不会复制或绕过后端 Router、Schema 和 Service；网络或统一 API 错误会进入可解释的 error 状态。

## 6. 请求状态规则

- `loading`：用骨架块替代旧成员内容，避免切换时继续显示过期数据。
- `empty`：HTTP 成功但 `items=[]`，说明资源确实为空，不应当成异常。
- `error`：网络、HTTP、统一 API error 或成员隔离失败，显示原因和重试入口。
- `data`：只有完成请求和成员检查后才渲染。

库存与知识检索是用户触发的查询，因此还存在“尚未查询”状态；它与“查询成功但无结果”必须使用不同文案。

## 7. 配置、运行与验证

浏览器使用 `NEXT_PUBLIC_API_BASE_URL`，默认 `http://localhost:8000`。变量带 `NEXT_PUBLIC_` 表示它会进入浏览器构建，不能在此放数据库密码或模型 Key。

```powershell
Set-Location frontend
npm install
npm run dev

# 提交前验证
npm test
npm run typecheck
npm run build
```

`client.test.ts` 验证 URL 编码、POST 确认布尔值和跨成员响应拒绝；页面测试在 jsdom 中验证成员切换清理旧数据、高风险无确认按钮、本地确认续跑和 Trace 字段。生产构建验证所有页面可由 Next.js 编译和生成。真实验收仍需要 PostgreSQL migration、seed、后端服务，以及完成并合入 2E-1 知识检索 API；mock HTTP 测试不能替代这一步。

## 8. Review 清单

1. 页面是否只通过 `lib/api/client.ts` 访问后端？
2. 成员资源 URL 是否包含当前 `member_id`，响应是否二次检查？
3. 切换成员时旧请求是否被取消、旧内容是否被清空？
4. loading、empty、error 和尚未查询是否被区分？
5. `confirmed` 是否明确为本地状态，而不是医院已提交或提醒已推送？
6. `source_id` 是否随知识结果展示？
7. 4C 页面是否消费任务七已提供的 `confirmation_state=DRAFT`，展示草稿后只确认执行，而不是继续渲染“是否允许创建草稿”的旧文案？
8. Trace 是否只读，是否区分单次 EvaluationResult 与最终阶段 4C 生成的真实聚合报告？

## 9. 非目标

- 不实现登录和生产鉴权。
- 不在前端保存长期健康数据或完整聊天历史。
- 不调用 LLM，不执行 LangGraph，不直接访问数据库。
- 不实现医院提交、药店下单、支付、短信或推送；`confirmed` 与 `draft` 都只是本地状态。
- 不在浏览器重算 Evaluator 指标，也不允许 UI 修改冻结 FinalAnswer、RunTrace 或 EvaluationResult。

## 10. 4C-1 患者端入口设计

首页参考药品/健康服务产品常见的“搜索 -> 分类 -> 快捷服务 -> 状态反馈”路径：

1. 顶部搜索将用户带到已有 `/knowledge` 页面，并通过 `q` 参数回填检索问题；真正的结果仍由 2E-1 API 返回。
2. “慢病续方、用药提醒、复诊材料、家庭药箱”是四个核心事务入口；它们使用现有 API 页面，不在首页复制处方或库存字段。
3. 当前成员卡片明确显示任务作用域；成员切换仍由 `MemberProvider` 和 `MemberSwitcher` 控制。
4. 首页持续展示“只生成本地草稿、不执行外部提交”的边界，避免视觉上把项目误解为药品商城。
5. “附近药店库存”只链接到候选库存页面；不存在加入购物车、支付、骑手配送成功或医院已受理等状态。

首页的 warm amber 色块只用于信息分组，不是对任何品牌视觉的复制。医疗安全说明、来源、确认和成员隔离仍优先于营销式转化设计。

4C 迁移完成前，前端不得提前假设新的 `confirmation_state` 已上线；迁移完成后应删除旧布尔字段交互，避免用户被要求确认两次。

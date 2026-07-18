# 前端架构与数据页面

## 1. 目标与边界

3A 前端使用 Next.js App Router、React、TypeScript 和 Tailwind CSS，把已有 FastAPI 读取接口变成可演示的数据页面。它负责展示、查询条件、加载状态和客户端隔离检查，不负责数据库查询、医疗判断、Agent 编排或外部业务提交。

本阶段深度页面：家庭成员、家庭药箱、续方/复诊、提醒。基础页面：购药库存、知识检索、Agent run 列表。Agent 对话、确认按钮、Run Trace 详情属于 3B，当前页面不会放置假装可用的按钮。

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
| `frontend/lib/api/client.ts` | 统一 base URL、GET、错误解析、URL 编码和成员隔离检查。 |
| `frontend/lib/useApiResource.ts` | 处理请求取消、loading、error、data 和 reload。 |
| `MemberProvider` | 加载成员列表并维护唯一的当前 `member_id`。 |
| `MemberSwitcher` | 让用户切换本人、父亲、母亲。 |
| `AsyncContent` | 统一 loading、empty 和 error 视觉状态。 |
| `app/**/page.tsx` | 组合页面需求，不直接拼接 API base URL。 |

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

知识页只消费 2E-1 学习题定义的契约。该 API 尚未整合到当前隔离分支时，页面会显示可解释错误；前端不会复制或绕过学习题的 Router、Schema 和 Service。

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

`client.test.ts` 验证 URL 编码和跨成员响应拒绝；`medicine-box/page.test.tsx` 在 jsdom 中渲染真实 React Provider、成员选择器和页面，验证成员切换时清理旧数据、loading、empty 以及跨成员 error。生产构建验证所有页面可由 Next.js 编译和生成。真实验收仍需要 PostgreSQL migration、seed、后端服务，以及完成并合入 2E-1 知识检索 API；mock HTTP 测试不能替代这一步。

## 8. Review 清单

1. 页面是否只通过 `lib/api/client.ts` 访问后端？
2. 成员资源 URL 是否包含当前 `member_id`，响应是否二次检查？
3. 切换成员时旧请求是否被取消、旧内容是否被清空？
4. loading、empty、error 和尚未查询是否被区分？
5. `confirmed` 是否明确为本地状态，而不是医院已提交或提醒已推送？
6. `source_id` 是否随知识结果展示？
7. 是否把 3B 的对话、确认和 Trace 详情提前伪装成可用能力？

## 9. 非目标

- 不实现登录和生产鉴权。
- 不在前端保存长期健康数据或完整聊天历史。
- 不调用 LLM，不执行 LangGraph，不直接访问数据库。
- 不实现医院提交、药店下单、支付、短信或推送。
- 不在 3A 实现 Agent 对话、确认状态变更或完整 Run Trace UI。

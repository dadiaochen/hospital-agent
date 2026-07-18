# 11：从零读懂 3A 前端数据页面

## 1. 你这一章要解决什么问题

后端 API 已经能返回 JSON，但用户不会一直打开 Swagger。前端的工作是把“HTTP 请求和 JSON”变成可操作、可理解的页面，同时正确处理慢请求、无数据、错误和家庭成员切换。

这一章不要求你先成为 UI 专家。先建立一条完整心智模型：

```text
点击页面
-> React 组件运行
-> 从 MemberProvider 取得 member_id
-> api client 发 HTTP GET
-> FastAPI 返回 JSON
-> TypeScript 按类型使用字段
-> React 根据状态重新渲染页面
```

## 2. 为什么选择这些技术

### Next.js 和 React

React 的核心是“状态变化后重新计算 UI”。比如 `loading` 从 `true` 变成 `false`、`data` 从 `null` 变成药箱数组，组件会重新渲染。Next.js 在 React 之上提供文件路由、生产构建和服务端/客户端组件边界。本项目把 `frontend/app/medicine-box/page.tsx` 自动映射为 `/medicine-box`。

如果使用 Vue，代码会写成 Vue 组件和 Composition API；如果只用原生 JavaScript，你需要自己管理 DOM、路由和大量状态更新。技术不同，但“请求 API -> 保存状态 -> 渲染四种结果”的业务逻辑不变。

### TypeScript

TypeScript 是带静态类型检查的 JavaScript。后端返回 `remaining_quantity: number`，前端类型也声明它是数字；如果误写成不存在的 `remaining_days_text`，`npm run typecheck` 会在运行前报错。

TypeScript 类型不会自动验证网络中的 JSON。真正的权限边界仍在后端；本项目额外用 `assertMemberScoped` 做关键的运行时成员检查。

### Tailwind CSS

`className="rounded-2xl bg-white p-5"` 是 Tailwind 工具类：圆角、白背景和内边距。它只负责样式，不负责 API、状态或安全。换成普通 CSS 不会改变业务数据流。

## 3. 第一遍阅读：先找页面入口

打开 `frontend/app/medicine-box/page.tsx`，先只回答五个问题：

1. 这个文件对应什么 URL？答案：目录名决定 `/medicine-box`。
2. 为什么第一行是 `"use client"`？因为页面使用 React hook 和浏览器请求，需要客户端运行。
3. 当前成员从哪里来？`useMember()`。
4. 调用哪个 API 方法？`api.listMedicineBox(memberId, signal)`。
5. 哪四种状态会渲染？loading、error、empty、data。

先不要逐个研究 CSS 类。能回答这五个问题，就已经看懂页面的主干。

## 4. 第二遍阅读：成员从哪里来

打开 `frontend/components/providers/MemberProvider.tsx`。

```tsx
const membersResource = useApiResource("family-members", (signal) =>
  api.listFamilyMembers(signal),
);
```

这段代码的逻辑是：用固定 key 加载家庭成员列表。`signal` 是浏览器的取消信号；组件卸载时可以停止旧请求。

```tsx
const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
```

`useState` 保存当前成员 ID。左边是当前值，右边是修改函数。它不是数据库字段，只是当前浏览器页面的临时状态。

```tsx
if (!members.some((member) => member.id === selectedMemberId)) {
  setSelectedMemberId(members[0].id);
}
```

成员列表加载完成后，如果还没选择成员，默认选择第一条。`some` 用于判断当前 ID 是否仍存在。

最后，Provider 把成员列表、当前 ID、切换函数、错误和重试入口共享给所有子页面。这样每个页面不用重复加载和维护选择器。

## 5. 第三遍阅读：HTTP 请求是怎么发出的

打开 `frontend/lib/api/client.ts`。

```ts
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
```

左边读取环境变量，`??` 表示没有配置时使用右边默认值。`NEXT_PUBLIC_` 变量会进入浏览器，因此只能放公开地址，不能放数据库密码或模型 Key。

```ts
const response = await fetch(`${API_BASE_URL}${path}`, {
  cache: "no-store",
  headers: { Accept: "application/json" },
  signal,
});
```

`fetch` 是浏览器 HTTP 客户端。`await` 等待响应；`Accept` 表示希望收到 JSON；`no-store` 防止家庭健康数据被框架缓存为旧页面；`signal` 允许取消请求。

```ts
if (!response.ok) {
  throw new ApiClientError(...);
}
return (await response.json()) as T;
```

HTTP 不是 2xx 时抛出统一错误；成功时把 JSON 转成调用方期望的类型。这里的 `as T` 只帮助 TypeScript，不能替代后端 Pydantic 校验。

## 6. 第四遍阅读：为什么还检查 member_id

药箱方法先请求：

```ts
const result = await getJson<ListResponse<MedicineBoxItem>>(
  apiPaths.medicineBox(memberId),
  signal,
);
```

然后检查：

```ts
return assertMemberScoped(result.items, memberId, "家庭药箱");
```

假设你选择父亲，但异常响应里有母亲的 `member_id`。最危险的处理是直接展示；其次是悄悄过滤，因为后端串数据问题会被隐藏。本项目选择抛出 `context_isolation_failed`，让页面停止展示并暴露问题。

这叫“纵深防御”：后端 service 负责真正的访问控制，前端负责避免错误数据被用户看见。不能只做前端检查，因为用户可以绕过页面直接调用 API。

## 7. 第五遍阅读：页面怎样处理异步状态

`useApiResource` 保存三个核心值：

```ts
{
  data: null,
  error: null,
  loading: true,
}
```

请求成功后变成 `data=真实值`；失败后变成 `error=错误信息`；两种情况下 `loading=false`。成员切换会改变 `resourceKey`，effect 清空旧数据并重新请求。

页面把状态交给 `AsyncContent`：

```tsx
<AsyncContent
  loading={box.loading}
  error={box.error}
  empty={(box.data?.length ?? 0) === 0}
  onRetry={box.reload}
>
  {/* 只有成功且非空时才渲染药品卡片 */}
</AsyncContent>
```

注意“空数据”和“错误”不同：`items=[]` 是成功响应，只是没有记录；网络断开或 500 才是错误。

## 8. 七个页面分别在做什么

| 页面 | 重点代码 | 你应该观察什么 |
| --- | --- | --- |
| 家庭成员 | `app/family/page.tsx` | 一个 response 同时包含 member 与 profile。 |
| 家庭药箱 | `app/medicine-box/page.tsx` | 数量比例、低库存展示，但不推导剂量。 |
| 续方复诊 | `app/refill-plans/page.tsx` | `Promise.all` 同时加载处方和草稿，再按 draft type 分类。 |
| 提醒 | `app/reminders/page.tsx` | confirmed 只表示本地确认，不表示已推送。 |
| 购药信息 | `app/purchase-plans/page.tsx` | 成员历史记录与全局库存搜索是两种作用域。 |
| 知识检索 | `app/knowledge/page.tsx` | 搜索结果展示 `source_id`；依赖你完成 2E-1 API。 |
| Agent runs | `app/agent-runs/page.tsx` | 3A 只做列表，完整 Trace 留到 3B。 |

## 9. 你如何自己调试一条完整链路

以药箱为例：

1. 启动 PostgreSQL，运行 migration 和 seed。
2. 启动后端，浏览器打开 `http://localhost:8000/docs`。
3. 在 Swagger 调用 `GET /api/family-members`，记住父亲的 ID。
4. 调用 `GET /api/family-members/{id}/medicine-box`，观察 JSON 字段。
5. 启动前端并打开 `http://localhost:3000/medicine-box`。
6. 在顶部切换父亲，打开浏览器开发者工具的 Network 面板。
7. 找到 medicine-box 请求，核对 URL 的 ID 和 Response 的每个 `member_id`。
8. 切换母亲，确认发出新请求，页面没有短暂保留父亲药品。

这套方法适用于所有页面：先 Swagger 验证后端，再 Network 验证 HTTP，最后看 React 页面。

## 10. 怎么验证代码没有写坏

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build
```

- `npm test`：一组验证 URL 构造和 API client 隔离；另一组把 MemberProvider、选择器和药箱页面真正渲染到 jsdom，验证成员切换、loading、empty 和 error。
- `npm run typecheck`：检查字段名、参数和组件类型。
- `npm run build`：让 Next.js 编译全部路由，发现只有实际打包时才出现的问题。

真实页面验收还要启动前后端并检查本人、父亲、母亲三次切换。知识页在你的 2E-1 接口合入前显示错误是符合当前分支事实的，不应伪造 mock 成功结果。

jsdom 是测试中的浏览器 DOM 模拟器，它让 React 组件测试不必真的打开 Chrome，但它不会运行 PostgreSQL 或 FastAPI。测试中的 mock response 只能证明“页面收到这些 HTTP 结果时如何表现”，不能证明真实后端一定会返回正确数据。

## 11. 给你的练习

1. 在 `client.test.ts` 新增测试：`confirmationDrafts("member/mother")` 必须正确编码。
2. 在药箱页面指出 `remainingRatio` 为什么要限制在 0 到 100。
3. 人为把测试数据的 `member_id` 改错，观察 `context_isolation_failed`。
4. 在 Network 面板比较 `200 + items=[]` 与后端关闭后的网络错误。
5. 完成 2E-1 知识 API 后，用 Postman、Swagger 和知识页面各验证一次同一搜索。

## 12. 面试可以怎么讲

可信表达：

> 使用 Next.js、React 与 TypeScript 实现家庭档案、药箱、续方复诊和提醒等数据页面，统一封装 API error/loading/empty 状态；通过共享 member context、请求取消和响应 member_id 二次校验避免成员切换时的数据串扰，并用前端契约测试和 production build 验证。

不要说“实现了生产级权限系统”，因为当前仍是固定 demo user；不要说“完成全链路 Agent 前端”，因为对话、确认和 Trace 详情属于 3B；不要说知识检索已经可用，直到你的 2E-1 API 真正合入并通过测试。

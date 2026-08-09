# 前端架构与数据页面

> 本文只描述当前患者端页面、`/agent` 主链路和浏览器验收边界；历史阶段与执行记录见 [项目执行历史](EXECUTION_HISTORY.md)。

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

## 10. 患者端入口设计

首页当前使用“选择成员 -> 说出问题 -> 查看结果”的简洁路径：

1. 顶部导航只保留 AI 健康助手、历史咨询、家庭管理和报告解读四个用户入口。
2. 首页主行动是进入自然语言咨询，辅助入口用于家庭记录和报告查看；不再把知识检索、库存、续方计划或提醒草稿当作快捷服务。
3. 当前成员卡片明确显示家庭成员；成员切换仍由 `MemberProvider` 和 `MemberSwitcher` 控制。
4. 草稿、外部提交、工具来源、Trace 和安全边界继续保留在代码、接口和必要的动作确认中，不作为首页操作说明。
5. 旧的知识、库存、续方、药箱、提醒和单条 Trace 地址由兼容跳转收回到对应的公共业务入口。

首页的 warm amber 色块只用于信息分组，不是对任何品牌视觉的复制。成员隔离、来源、确认和医疗安全规则仍由既有运行契约负责。

4C 迁移完成前，前端不得提前假设新的 `confirmation_state` 已上线；迁移完成后应删除旧布尔字段交互，避免用户被要求确认两次。

## 11. `/agent` 主链路

`frontend/app/agent/page.tsx` 使用现有 `/api/agent-runs` 和 `/api/agent-runs/{run_id}/continue`，不在浏览器实现 Agent 编排。页面把后端冻结产物投影成五步生命周期：

```text
首次 run -> 生成 DRAFT -> 用户确认 -> continuation run -> 本地记录完成
```

- 首次请求固定发送 `human_confirmation_granted=false`。
- `needs_confirmation + waiting_for_user_confirmation` 显示用户可理解的“请确认是否继续”确认区域。
- 确认按钮只有在用户明确勾选“我已阅读上面的整理内容，确认继续”后可用，并使用新的幂等键发起 continuation run。
- continuation run 仍通过 `resumed_from_run_id` 与原任务关联；这些运行标识只留在代码和接口层，页面不展示给用户。
- `SafetyAgent` blocked 时显示 `BLOCKED`，不渲染业务确认按钮。
- `/agent-runs` 作为“历史咨询”入口，只读取当前成员记录，并展示用户目标、状态、时间和整理结果，不展示 Trace、工具链、评测指标或内部运行标识。

这条页面链路使用当前 deterministic backend 也能重复演示；真实 Provider、RAG 或 degraded 状态由后端响应决定，前端不伪造成功状态。

## 12. 浏览器 E2E

浏览器级测试位于 `frontend/e2e/`，通过 Playwright 使用真实浏览器访问已经启动的 Docker Compose。配置位于 `frontend/playwright.config.ts`：默认使用 Windows 已安装的 Edge，保留失败截图和 trace，关闭视频录制以避免额外的 ffmpeg 下载；测试报告写入被 Git 忽略的 `var/`。

E2E 不在浏览器中重算业务结果，也不直接访问数据库。它只验证用户能看到后端冻结产物，并且 UI 没有绕过确认、安全和成员作用域：

- `agent-golden-flows.spec.ts` 覆盖续方的 DRAFT/确认续跑、用药提醒确认、复诊材料回归和高风险拦截。
- `portal-boundaries.spec.ts` 覆盖 member 切换清理旧结果和 API 503 错误呈现。

组件测试回答“React 状态逻辑是否正确”，浏览器 E2E 回答“真实 Docker 前后端和浏览器之间的契约是否能走通”；两者不能互相替代。

## 13. 2026-08-02 用户端公共壳层迭代

本次只完成用户端改版的第一步，不提前实现 AI 对话内容、报告解读或家庭管理详情：

- 顶部壳层改为 Logo、AI 健康助手、家庭管理和报告解读规划入口，以及当前家庭成员选择器。
- 移除顶部“仅生成本地草稿……”提示、侧栏安全约束说明和研发式侧栏布局。
- 报告解读入口先以“即将上线”状态保护空路由；UX-05 完成后已切换为可访问的上传与最近报告页面，详情解读仍等待 UX-06。
- `DRAFT`、continuation run、SafetyAgent、EvaluatorAgent、Trace 和外部动作状态仍属于代码/接口契约；用户端只在必要的业务动作处显示自然语言结果。
- 成员切换器保留加载、错误、空成员、无障碍标签和成员隔离行为；内部 `member_id` 只作为选择值参与请求。

本次修改文件：

- `frontend/components/AppShell.tsx`
- `frontend/components/MemberSwitcher.tsx`
- `frontend/components/Navigation.tsx`
- `frontend/lib/navigation.ts`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`

验证方式：在 `frontend` 目录执行 `npm run typecheck`、`npm run test` 和 `npm run build`。当前结果为类型检查通过、25 个前端测试通过、Next.js 生产构建通过。下一步按线性顺序实现 AI 健康助手的空状态和输入区，再进入报告解读与家庭管理页面。

设计说明：成员隔离、确认状态和多 Agent 运行为后端契约，前端只提供清晰的健康事务入口。

## 14. 2026-08-02 UX-02 AI 健康助手（已完成）

本步只实现 `/agent` 的首屏空状态和输入区，作为用户端改版的第二步：

- 页面首屏使用自然语言标题和欢迎说明，明确当前家庭成员，但不展示 Golden Flow、deterministic、Agent、Trace、工具权限、确认布尔值或外部执行边界等内部实现术语。
- 保留一个自然语言输入框和“开始咨询”入口；没有输入时不能提交，输入后由现有 `api.createAgentRun` 发起首轮请求。
- 继续在请求契约中固定发送 `human_confirmation_granted=false`，该字段只存在于代码和接口层，不作为用户可见文案。
- 本步不改确认区和历史咨询；消息结果、报告上传和家庭管理分别由 UX-03、UX-05、UX-07 按路线图推进。

验收结果：首屏没有固定开发者场景和可选内部参数；空输入时入口不可用；填写自然语言后可以提交；成员切换仍清理旧的运行结果并保留成员隔离。

本步修改文件：

- `frontend/app/agent/page.tsx`
- `frontend/app/agent/page.test.tsx`
- `frontend/e2e/agent-golden-flows.spec.ts`
- `frontend/e2e/portal-boundaries.spec.ts`

验证方式：在 `frontend` 目录执行 `npm run typecheck`、`npm run test` 和 `npm run build`；本步类型检查通过，完整回归由 UX-03 及并行支线合并后统一记录。下一步按路线图进入 UX-04，改造确认交互与历史咨询。

## 15. 2026-08-02 UX-03 AI 健康助手结果卡片（已完成）

- `/agent` 提交后的结果由“咨询结果、整理结果、参考信息、安全提示”组成，隐藏 `DRAFT`、run/task 标识、Trace、工具名、原始 source_id 和安全规则代码。
- 空状态中的四个健康话题已变为可直接填入输入框的快捷问题；提交后保留本轮用户消息气泡，再展示助手整理结果，形成最小可用的对话消息区。
- 参考信息只展示用户可理解的资料类型与数量；高风险请求使用“需要专业人员确认”等自然语言，不展示内部 Agent 或 flag 名称。
- 保留现有后端安全、成员隔离和确认代码契约；确认区仍由 UX-04 接续改造。

本步修改文件：

- `frontend/components/AgentRunResult.tsx`
- `frontend/app/agent/page.test.tsx`
- `frontend/e2e/agent-golden-flows.spec.ts`
- `frontend/e2e/portal-boundaries.spec.ts`

## 16. 2026-08-02 并行完成 UX-05 与 UX-07

UX-05 和 UX-07 只依赖已完成的公共壳层，写入范围互不重叠，因此并行实现：

- UX-05 新增报告解读上传区和最近报告列表；当前文件只保留在页面状态中，未伪造报告上传或解析成功；详情指标解释等待 UX-06。
- UX-07 将家庭管理改为当前成员健康总览，聚合健康档案、用药、药箱、处方、购药和本地准备记录，并在成员切换时隔离数据。
- 报告页和家庭页均不展示 `member_id`、API 路径、Agent、Trace 或工具权限等内部术语。

本步修改文件：

- `frontend/app/reports/page.tsx`
- `frontend/app/reports/page.test.tsx`
- `frontend/app/family/page.tsx`
- `frontend/app/family/page.test.tsx`
- `frontend/lib/navigation.ts`

统一验证：在 `frontend` 目录执行 `npm run typecheck`、`npm run test` 和 `npm run build`；类型检查通过，7 个测试文件、27 个测试通过，Next.js 生产构建通过。浏览器 E2E 仍需完整后端环境后执行。

## 17. 2026-08-02 UX-04 自然语言确认与历史咨询（已完成）

- `/agent` 的确认区改为“请确认是否继续”，用“我已阅读上面的整理内容，确认继续”表达用户动作；页面不再展示 `DRAFT`、外部提交、continuation run 或确认说明输入框。
- 代码仍固定提交 `human_confirmation_granted=true` 和确认消息，保留后端 continuation、幂等键、安全拦截与成员作用域契约；内部约束没有迁移到用户文案中。
- `/agent-runs` 改为“历史咨询”页面，按当前成员加载历史记录，使用“已完成、待确认、已暂停、未完成”等状态和“续方准备、用药提醒、购药准备、用药安全”等用户表达；记录只展示咨询内容、时间和整理结果。
- 成员切换时历史请求使用成员维度缓存键并清理旧内容，页面和测试均验证不会混入其他成员记录。

本步修改文件：

- `frontend/app/agent/page.tsx`
- `frontend/app/agent/page.test.tsx`
- `frontend/app/agent-runs/page.tsx`
- `frontend/app/agent-runs/page.test.tsx`
- `frontend/e2e/agent-golden-flows.spec.ts`
- `frontend/lib/navigation.ts`
- `docs/DEVELOPMENT_ROADMAP.md`
- `docs/FRONTEND_ARCHITECTURE.md`

验证结果：在 `frontend` 目录执行 `npm run typecheck`、`npm run test` 和 `npm run build` 均通过；完整回归为 8 个测试文件、29 个测试通过，生产构建生成 13 个路由。UX-04 定向组件测试覆盖确认前置勾选、确认请求和历史成员隔离，浏览器 E2E 仍需完整后端环境后执行。

设计说明：患者端动作收敛为自然语言确认和可回看的家庭咨询记录，确认状态与成员隔离仍由后端契约保证。

## 18. 2026-08-03 UX-06 报告详情数据契约（前置冻结）

- 已冻结 `report-detail.v1`，包含报告摘要、处理状态、指标值、单位、参考范围、趋势、通俗解释、原文来源和安全提示。
- 契约使用明确的 `ready`、`processing`、`needs_review`、`failed` 等状态；没有可解释指标或来源未核实时，页面必须展示对应状态，不得补造医疗事实。
- 契约接口为 `GET /api/family-members/{member_id}/reports` 和 `GET /api/family-members/{member_id}/reports/{report_id}`；服务端和客户端都必须校验成员归属。
- 已按契约接入只读报告列表和详情页面：报告列表消费 `api.listReports`，详情页消费 `api.getReportDetail`，页面只展示用户可理解的摘要、指标、参考范围、趋势、来源和阅读提示。
- 服务端接口复用既有 `medical_documents` 事实，并在 `ReportReadService` 中归一化状态和结构化内容；没有新增上传、解析、诊断、治疗或外部提交动作。前后端都会拒绝跨成员报告，客户端还会校验指标/章节的来源引用完整性。
- 详情页路由为 `/reports/[reportId]`；页面不展示 `report_id`、来源内部 ID、解析 provider、对象地址或执行边界文案。

契约文档：[REPORT_DETAIL_CONTRACT.md](REPORT_DETAIL_CONTRACT.md)。

验证方式：在 `frontend` 目录执行 `npm run test`、`npm run typecheck` 和 `npm run build`；本次 UX-06 验证为 9 个测试文件、34 个测试通过、生产构建生成 13 个路由。后端执行 `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_read_api.py -q -p no:cacheprovider --basetemp=var/pytest/ux06-read-api`，6 个测试通过。下一步进入 UX-08，处理内部入口清理与兼容路由。

设计说明：报告页面通过版本化 DTO 展示已有文档事实，保留成员隔离、来源、降级状态和安全提示，不把模型解释伪装成医疗结论。

## 19. 2026-08-03 用户端 UX-08 内部入口清理（已完成）

UX-08 将用户端首页和顶部导航收敛为四个业务入口：AI 健康助手、历史咨询、家庭管理和报告解读。首页采用“选择成员—说出问题—查看结果”的用户语言，不再把知识检索、药店库存、续方计划、提醒草稿、固定演示、安全约束、草稿状态或 Trace 作为用户功能展示。

旧地址不直接删除，以兼容历史书签和已有调用：`/knowledge`、`/reminders` 跳转到 `/agent`；`/purchase-plans`、`/refill-plans`、`/medicine-box` 跳转到 `/family`；`/agent-runs/:id` 跳转到 `/agent-runs`。这些跳转由 Next.js 路由配置统一处理，旧页面实现不再作为公共入口。

本步修改文件：

- `frontend/app/page.tsx`
- `frontend/app/page.test.tsx`
- `frontend/components/Navigation.tsx`
- `frontend/lib/navigation.ts`
- `frontend/lib/navigation.test.ts`
- `frontend/next.config.mjs`
- `frontend/e2e/portal-entry-cleanup.spec.ts`

验证方式：在 `frontend` 目录执行 `npm run typecheck`、`npm run test` 和 `npm run build`；本次结果为类型检查通过、10 个测试文件/35 个测试通过、Next.js 生产构建生成 13 个页面。使用临时构建服务并明确设置 `E2E_BASE_URL=http://127.0.0.1:3000` 执行 `npm run test:e2e -- e2e/portal-entry-cleanup.spec.ts`，2 个浏览器用例通过。本步不改后端接口、数据库、Agent 工作流或安全规则。下一步唯一进入 UX-09，完成跨页面视觉、响应式、可访问性和交付收口。

设计说明：开发者检索、内部草稿和执行追踪不暴露给患者端，页面只保留清晰的业务入口。

## 20. 2026-08-03 用户端 UX-09 跨页面联调与交付收口

UX-09 在真实 Docker 前后端环境中验收既有用户链路：成员加载与切换、AI 健康助手首轮咨询与确认、历史咨询成员隔离、报告列表/详情权限边界、家庭管理聚合数据以及旧入口兼容跳转。历史记录、家庭草稿和咨询结果统一经过前端用户语言投影，不把 `run_id`、`source_id`、工具名、内部英文状态或实现边界作为页面内容。

本阶段复用既有 API 和状态机，没有新增前端业务动作。桌面端 1440×900 与移动端 390×844 均通过无横向溢出检查；公开五页的交互控件均有可访问名称。真实联调使用 deterministic provider 保障可重复性，不代表真实模型质量或生产环境验收。

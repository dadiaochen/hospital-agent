# Development Roadmap

## 1. 文档地位

本文档是项目阶段编号、阶段状态、依赖关系和 MVP 完成标准的唯一权威来源（Single Source of Truth）。

- `README.md` 只展示当前状态和本文档入口。
- `NEXT_STEPS.md` 只展示本文档定义的最近一个待办阶段。
- `HOSPITAL_LANGFLOW_HARNESS_PLAN.md`、`TECH_DESIGN.md` 等是子系统设计，不单独发明阶段编号。
- `family_health_agent_project_prompt.md` 保留需求和历史变更记录，不作为未来阶段排期来源。
- 未先修改本文档，不得在任务指令、提交信息或“下一阶段建议”中新增 2E、3D 等阶段编号。

## 2. 最终目标

项目最终交付为简历级、可本地演示的互联网医院家庭健康管理 Agent MVP，而不是生产级医疗系统。

最终演示必须同时支持：

1. 前端交互：用户可以在页面完成四个核心场景。
2. Swagger / API：核心读取、草稿、确认、Agent 和 Trace 能通过 API 独立验证。
3. 双模式 Agent：配置模型 Key 时调用真实 LLM；无 Key 时使用 deterministic fallback。
4. 本地业务闭环：关键动作只更新本地草稿和确认状态，不提交真实医院或药店系统。
5. 可追踪与可评估：所有事实有来源，工具调用和 Agent run 可回放，固定 Harness 可执行。

## 3. 已确认的产品决策

| 决策 | 最终选择 | 约束 |
| --- | --- | --- |
| 交付级别 | 简历级可演示 MVP | 不扩张为生产级医院系统 |
| 演示入口 | 前端与 Swagger / API 同等可用 | UI 与 API 必须共享同一业务契约 |
| 模型策略 | 真实 LLM + deterministic fallback | 测试和 CI 默认不调用外部模型 |
| 人工确认 | 本地状态流转 | 不模拟真实提交、下单或医疗动作成功 |
| 用户认证 | 固定 demo 用户 | 不实现 JWT、OAuth；必须真实校验 member 隔离 |
| RAG | 关键词基线 + 可选向量检索 | 无 embedding 服务仍可运行 |
| 前端范围 | 核心页面深入，其他页面真实可读 | 不追求所有页面完整 CRUD |

## 4. MVP 核心场景

以下四个场景必须从前端和 API 两条入口跑通：

1. 父亲降压药续方材料整理。
2. 母亲中医复诊材料整理。
3. 母亲早晚用药提醒草稿与本地确认。
4. 加量、减量、停药、换药等高风险医疗问题安全拦截。

每个场景都必须满足：

- 明确 `user_id`、`member_id`、`task_id` 和 `run_id`。
- DB / API / RAG 事实保留来源指针。
- 工具调用经过 Tool Registry，并生成 Trace。
- 关键动作先生成草稿，再由用户确认本地状态。
- SafetyAgent 在运行时拦截风险；Evaluator 在运行后只读评估。
- 不允许模型补造病史、处方、库存或医疗规则。

## 5. 状态说明

| 状态 | 含义 |
| --- | --- |
| `DONE` | 代码、测试和文档已完成，并已进入当前线性分支 |
| `NEXT` | 唯一允许立即开始的下一阶段 |
| `PLANNED` | 已定义但前置阶段尚未完成 |
| `OPTIONAL` | 不影响 MVP 完成的增强项 |
| `OUT` | 明确不属于本项目 MVP |

## 6. 总体阶段表

| 阶段 | 状态 | 目标 | 主要验收 |
| --- | --- | --- | --- |
| 1 | `DONE` | Monorepo、FastAPI、Next.js、Docker 骨架 | 后端和前端最小启动 |
| 2A | `DONE` | ORM、Alembic、seed、模型测试 | 数据库模型和 seed 可验证 |
| 2A.1 | `DONE` | AgentRun / AgentToolCall Trace 字段 | migration、seed、模型测试通过 |
| 2A.2 | `DONE` | Context Lifecycle 与 Evaluator 架构 | 规则和设计文档完成 |
| 2B-1 | `DONE` | Context / Evaluation Pydantic 契约 | 16 条 ExpectedCase 通过校验 |
| 2B-2 | `DONE` | DeterministicEvaluator 与 HarnessRunner | mock trace 可评估并生成报告 |
| 2B-3 | `DONE` | ContextManager | role view、compact、reset 测试通过 |
| 2C-1 | `DONE` | Tool Registry 与六个 mock 工具 | schema、权限、确认门测试通过 |
| 2C-2 | `DONE` | Deterministic AgentHarnessRuntime | 16 条 fixture 可离线回放 |
| 2D-1 | `DONE` | 五类数据库只读工具 | DB 工具与 2C Harness 联合测试通过 |
| 2D-2 | `NEXT` | 待确认草稿写入工具 | 只写本地 draft / confirmation 状态 |
| 2E-1 | `PLANNED` | 基础读取 API | 家庭、药箱、处方、知识、run 可查询 |
| 2E-2 | `PLANNED` | 草稿与确认 API | 本地状态机和幂等确认通过 |
| 2F-1 | `PLANNED` | Hybrid RAG | 关键词稳定、向量检索可选 |
| 2F-2 | `PLANNED` | Model Gateway | LLM 与 deterministic fallback 同契约 |
| 2G-1 | `PLANNED` | LangGraph Multi-Agent 工作流 | 四场景节点和 SafetyAgent 跑通 |
| 2G-2 | `PLANNED` | Runtime 持久化与 Agent API | run/tool trace、reset、续跑可查询 |
| 3A | `PLANNED` | 核心数据页面接入 API | 家庭、药箱、续方、提醒页面可用 |
| 3B | `PLANNED` | Agent 对话、确认与 Trace UI | 四场景前端闭环可演示 |
| 3C | `PLANNED` | E2E 与真实 Trace Harness | API/UI 场景、隔离、安全回归通过 |
| 3D | `PLANNED` | 一键演示与项目收口 | Docker、演示脚本、README、简历材料完成 |

## 7. 已完成阶段基线

当前线性 Git 基线：

```text
main
  -> 2C-1 Tool Registry + deterministic mock tools
  -> 2C-2 deterministic Harness Runtime
  -> 2D-1 database-backed read-only tools
```

2A 至 2B-3 已包含在初始项目基线中。2C-1、2C-2、2D-1 已拆成独立提交，并通过完整后端测试。旧平行分支和 GitHub Desktop stash 暂时只作为恢复备份，待新线性分支合并并确认远程无误后再清理。

## 8. 后续阶段详细定义

### 2D-2 待确认草稿写入工具

目标：实现 `create_confirmation_draft` 的真实数据库版本，仅创建本地待确认草稿。

交付：

- 为复诊/续方、购药方案和提醒创建统一草稿契约。
- 状态限制为 `draft -> pending_confirmation -> confirmed | rejected | expired`。
- 记录 `created_by_run_id`、确认人和确认时间等现有模型允许的审计信息。
- Tool Registry 继续校验角色、schema、`allowed_tools` 和 `requires_human_confirmation`。

验收：

- 未确认调用不能产生 confirmed 状态。
- 重复确认幂等，不重复创建业务记录。
- 跨成员、跨用户确认被拒绝。
- 不出现“已提交医院”“已下单”或“自动开方”等外部成功语义。

非目标：FastAPI endpoint、LangGraph、外部系统提交、自动医疗动作。

### 2E-1 基础读取 API

目标：以 FastAPI 暴露现有 service 的只读能力。

范围：

- 家庭成员与健康档案。
- 家庭药箱。
- 历史处方与购药记录。
- 药店库存。
- 知识库查询。
- Agent run 与 tool call 查询。

验收：Pydantic 请求/响应、统一错误格式、demo user/member 隔离、API 测试和 Swagger 示例齐全。

非目标：真实登录、Agent 工作流、外部医院/药店接口。

### 2E-2 草稿与确认 API

目标：通过 API 创建、查询、确认或拒绝本地草稿。

验收：

- 状态转换白名单生效。
- 确认接口幂等。
- 用户只能操作当前 demo user 下的成员数据。
- 所有关键动作保留 `human_confirmation` 审计字段。

非目标：真实提交、支付、推送和处方修改。

### 2F-1 Hybrid RAG

目标：把现有知识库关键词查询整理为 Retriever 接口，并增加可选向量检索实现。

验收：

- 关键词检索始终可用。
- 向量能力通过配置启用；缺少 embedding 服务时自动回退。
- 返回文档/分块版本、`source_id`、评分和用途。
- 安全规则与复诊 SOP 有固定检索测试。

非目标：未经审核的互联网医疗内容抓取、模型生成知识写回。

### 2F-2 Model Gateway

目标：定义统一模型调用接口，支持真实 LLM 与 deterministic fallback。

验收：

- Key 和模型配置只来自环境变量。
- 自动测试默认使用 deterministic provider。
- LLM 输出必须经过 Pydantic 解析和 safety check。
- provider 超时、错误和 schema 失败有 fallback 与 Trace。

非目标：多模型自动路由平台、模型训练和线上成本优化。

### 2G-1 LangGraph Multi-Agent 工作流

目标：实现最小正式业务工作流，而不是继续扩展 mock runtime。

流程：

```text
User Input
  -> Planner
  -> ContextManager
  -> Profile / Refill / Pharmacy / Reminder Agents
  -> Tool Registry / RAG
  -> SafetyAgent
  -> Confirmation Draft
  -> FinalAnswer
  -> RunSummary / Reset
  -> DeterministicEvaluator
```

验收：四个 MVP 场景跑通；成员隔离、安全拦截、来源保留和人工确认不可绕过。

非目标：自主诊断、自动处方、无限循环自主 Agent。

### 2G-2 Runtime 持久化与 Agent API

目标：持久化 `agent_runs`、`agent_tool_calls` 和必要审计引用，并提供 Agent 运行入口。

范围：

- `POST /api/agent/run` 或等价入口。
- 查询 run、tool calls、sources、safety 和 evaluation。
- 确认后的同任务续跑。
- Context Reset 后只恢复结构化 summary 和来源指针。

验收：真实 run 可重放为冻结 RunTrace；Evaluator 仍只读，不修改答案和业务状态。

### 3A 核心数据页面

深度完成：家庭成员、家庭药箱、续方/复诊、提醒。

基础可用：购药方案、知识库、Agent run 列表。

验收：页面从真实 API 读取数据，具有 loading、empty、error 状态，并能切换本人/父亲/母亲而不串数据。

### 3B Agent 对话、确认与 Trace UI

目标：完成主要面试演示入口。

验收：

- 用户输入四个核心场景语句。
- 页面展示结构化答案、事实来源、安全提示和待确认动作。
- 确认只更新本地状态。
- Agent run 详情展示角色、工具、耗时、错误、fallback 和评估结果。

### 3C E2E 与真实 Trace Harness

目标：把 API/UI 实际运行产物接入 Harness，而不是只评估 mock trace。

验收：

- 四个正常/高风险场景端到端测试。
- 工具异常、无来源、跨成员串扰和缺确认回归测试。
- 真实 trace 脱敏 adapter。
- JSON 与 Markdown 报告可生成。

指标只有真实运行后才能记录为实测值；在此之前只能写“目标指标”或“评估维度”。

### 3D 一键演示与项目收口

目标：形成面试可重复演示的最终交付。

验收：

- `docker compose up --build` 可以启动 MVP 所需服务。
- seed 后可按固定脚本完成四场景演示。
- README 包含架构、运行、测试、演示和限制。
- API、数据库、Agent、Context、Evaluator 和 Roadmap 文档一致。
- 简历描述只陈述真实实现和真实报告结果。

## 9. MVP 完成定义

只有同时满足以下条件，项目才能标记为 MVP Complete：

- 四个核心场景从 UI 和 API 均可跑通。
- 无模型 Key 时 deterministic fallback 可完整演示。
- 配置模型 Key 时可调用真实 LLM，失败可安全回退。
- 关键词 RAG 可用，可选向量检索不会成为启动前置条件。
- 草稿与确认只产生本地状态，不伪装外部提交成功。
- `user_id` / `member_id` 隔离测试通过。
- SafetyAgent 与 Evaluator 职责分离。
- Agent run、tool call、sources、safety 和 evaluation 可查询。
- 后端、前端、E2E 和 Harness 测试通过。
- Docker 启动、seed 和演示步骤经过实际验证。

## 10. 明确非目标

以下内容标记为 `OUT`，不得临时插入 MVP 主线：

- JWT、OAuth、短信登录和多租户账号系统。
- 真实互联网医院、医生、处方、药店、支付和物流接口。
- 疾病诊断、自动开方、修改处方或剂量调整建议。
- 真实下单、支付、提醒推送或医院提交。
- 生产级隐私合规认证、容灾、SLA 和大规模监控平台。
- 模型训练、微调或多模型调度平台。

## 11. 阶段治理规则

1. 同一时间只能有一个 `NEXT` 阶段。
2. 新阶段开始前，从最新线性主线创建 `codex/<阶段>-<主题>` 分支。
3. 每个阶段必须声明目标、前置依赖、允许修改范围、禁止范围和验收测试。
4. 每个阶段必须包含最小测试、自审、文档同步和独立 commit。
5. 后续阶段不得整文件覆盖前一阶段契约；只能做兼容的增量演进。
6. 阶段完成后先将本文档状态改为 `DONE`，再把唯一 `NEXT` 移到下一阶段。
7. 任何“下一阶段建议”必须引用本文档中的已定义阶段。
8. 未经本文档更新，不允许出现新的阶段编号。

## 12. Git 工作流

推荐流程：

```text
main
  -> codex/2d-2-confirmation-drafts
  -> review + tests
  -> merge into main
  -> codex/2e-1-read-apis
```

- 不从旧功能分支继续创建新阶段。
- 不让多个阶段平行从同一个旧 `main` 分叉后互相覆盖。
- 不 force push `main`。
- GitHub Desktop 可以完成 commit、push、Pull Request 和 merge；底层仍是同一个 Git 仓库。
- 恢复备份分支和 stash 只在新线性历史已推送并验证后清理。

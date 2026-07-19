# Development Roadmap

## 1. 文档地位

本文档是项目阶段编号、阶段状态、依赖关系和 MVP 完成标准的唯一权威来源（Single Source of Truth）。

- `README.md` 只展示当前状态和本文档入口。
- `NEXT_STEPS.md` 只展示本文档定义的最近一个待办阶段。
- `AGENT_WORKFLOW.md`、`TECH_DESIGN.md` 等是子系统设计，不单独发明阶段编号。
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
| 2D-2 | `DONE` | 待确认草稿写入工具 | 只写本地 draft / confirmation 审计 |
| 2E-1 | `DONE` | 基础读取 API | 家庭、药箱、处方、知识、run 可查询 |
| 2E-2 | `DONE` | 草稿与确认 API | 本地状态机和幂等确认通过 |
| 2F-1 | `DONE` | Hybrid RAG | 关键词稳定、向量检索可选 |
| 2F-2 | `DONE` | Model Gateway | LLM 与 deterministic fallback 同契约 |
| 2G-1 | `DONE` | LangGraph Multi-Agent 工作流 | 四场景节点和 SafetyAgent 跑通 |
| 2G-2 | `DONE` | Runtime 持久化与 Agent API | run/tool trace、reset、续跑可查询 |
| 3A | `DONE` | 核心数据页面接入 API | 家庭、药箱、续方、提醒页面可用 |
| 3B | `DONE` | Agent 对话、确认与 Trace UI | 四场景前端闭环可演示 |
| 3C | `DONE` | E2E 与真实 Trace Harness | API/UI 场景、隔离、安全回归通过 |
| 3D | `DONE` | 一键演示与项目收口 | Docker、演示脚本、README、简历材料完成 |
| 4A | `DONE` | 轻量向量 RAG | pgvector + 本地 Embedding 可选启用，关键词模式仍可独立运行 |
| 4B | `DONE` | 真实 LLM 接入与验证 | OpenAI-compatible 配置、连通性检查、失败回退可复现 |
| 4C | `NEXT` | 面经学习与项目答题库 | 原题归并、项目化回答、理解记忆和技术取舍持续维护 |

## 7. 已完成阶段基线

当前线性 Git 基线：

```text
main
  -> 2C-1 Tool Registry + deterministic mock tools
  -> 2C-2 deterministic Harness Runtime
  -> 2D-1 database-backed read-only tools
  -> 2D-2 confirmation-gated local draft writes
  -> 2E-1 scoped read APIs and knowledge search
  -> 2E-2 draft confirmation API
  -> 2F-1 deterministic hybrid retriever
  -> 2F-2 structured model gateway
  -> 2G-1 bounded LangGraph workflow
  -> 2G-2 persisted Agent runtime API
  -> 3A member-scoped data pages
  -> 3B Agent conversation and Trace UI
  -> 3C Runtime E2E and real Trace Harness
  -> 3D one-command demo and MVP closure
  -> 4A lightweight pgvector and FastEmbed RAG
  -> 4B runtime-wired optional LLM and provider diagnostics
```

2A 至 2B-3 已包含在初始项目基线中。2C-1 至 4B 已按阶段形成唯一线性历史。3D 形成可重复的本地 MVP 交付；4A 复用 PostgreSQL 接入 pgvector 与按需加载的 FastEmbed 中文模型；4B 将可选 provider 接入 Runtime 默认创建链，并增加默认不联网、显式 `--live` 才调用外部模型的诊断。项目仍保持 MVP Complete；当前唯一 `NEXT` 为 4C。

## 8. 阶段详细定义

### 2D-2 待确认草稿写入工具

目标：实现 `create_confirmation_draft` 的真实数据库版本。Tool Registry 在 handler 前执行人工确认门；通过后只创建本地草稿，不执行任何外部动作。

交付：

- 为复诊、续方、购药候选和提醒创建统一草稿契约。
- 数据库记录保持 `status="draft"` 和 `need_human_confirmation=true`；`confirmed_at` 只表示用户允许创建本地草稿。
- 在现有 JSON 字段中记录 `created_by_run_id`、幂等键、用户/成员和外部动作状态，不新增 ORM 字段。
- Tool Registry 继续校验角色、schema、`allowed_tools` 和 `requires_human_confirmation`。

验收：

- 未确认调用不执行 handler，也不产生数据库记录。
- 重复幂等键返回已有草稿，不重复创建业务记录。
- 跨成员、跨用户确认被拒绝。
- 不出现“已提交医院”“已下单”或“自动开方”等外部成功语义。

状态确认、拒绝和过期的 HTTP 状态机统一留到 2E-2；2D-2 不提前实现 API。

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

### 4A 轻量向量 RAG

目标：在不引入 RAGFlow 整套服务的前提下，为现有 Hybrid Retriever 接入可真实运行的本地 Embedding 与 PostgreSQL 向量检索；默认关键词模式和 3D 演示不得依赖模型下载。

前置依赖：3D 已完成并形成可回滚里程碑。

允许范围：知识库 ORM 的向量字段、独立 Alembic migration、`backend/app/rag/`、索引脚本、RAG 配置、Docker PostgreSQL 镜像、RAG 测试和相关文档。

验收：

- PostgreSQL 使用 pgvector 扩展；查询采用精确余弦距离，不为小型演示库提前引入高内存向量服务。
- 本地 Embedding 默认使用轻量中文模型，模型缓存落在 E 盘项目 `var/models`，只在显式启用或执行索引时加载。
- `RAG_VECTOR_ENABLED=false` 时不加载 Embedding，关键词检索和全部既有测试保持可用。
- 向量模式返回既有 `source_id`、`document_id`、`chunk_id`、版本和用途，不能返回无法回溯的文本。
- Embedding 缺失、索引缺失或向量查询失败时安全回退关键词检索，并记录明确的 fallback reason。
- 固定中文同义表达可以通过真实向量检索命中知识分块，并有 PostgreSQL 集成验证步骤。

禁止范围：部署 RAGFlow、抓取未经审核的互联网医疗内容、由模型生成知识并自动写回、把向量服务设为默认启动前置条件。

### 4B 真实 LLM 接入与验证

目标：在保留 deterministic 默认模式的同时，提供清晰的 OpenAI-compatible provider 配置位置、无密钥检查、带密钥连通性检查和安全 fallback 验证。

前置依赖：4A 完成。

允许范围：Model Gateway 配置与诊断脚本、环境变量示例、测试和部署/学习文档。

验收：

- 仓库不保存真实 API Key；用户只在根目录 `.env` 填写 provider、base URL、模型名和 Key。
- 未配置 Key 时项目继续使用 deterministic provider，前后端和固定演示照常运行。
- 配置 OpenAI-compatible provider 后可执行独立连通性检查；超时、HTTP 错误、schema 错误和不安全输出仍回退。
- 文档明确哪些模型可接、如何切换、如何确认实际调用和如何恢复离线模式。

完成证据：Runtime 默认工作流已使用环境感知工厂；无 `--live` 的诊断不发 HTTP，显式 live 会区分 primary 成功与 fallback 成功；自动化覆盖配置、HTTP 契约、密钥不泄露、失败回退和 HTTP client 所有权。未提供真实 Key，因此不产生真实模型效果指标。

禁止范围：提交密钥、实现多模型调度平台、宣称未实际验证的模型效果或成本指标。

### 4C 面经学习与项目答题库

目标：建立可增量维护的面经文档，把相同或相似原题归到同一知识主题，同时保留每一道原题的原句，并给出基于本项目真实实现的回答、技术解释和记忆方法。

前置依赖：4B 完成。

允许范围：`docs/learning/`、文档导航、README 学习入口和项目变更记录。

验收：

- 每个主题包含原题原句列表、面试短答、项目展开回答、原理解释、代码证据、记忆框架和可能追问。
- 新面经先做相似题归并；相似题追加原句，不重复维护冲突答案；新主题才新增条目。
- 项目未使用的技术必须标记为“未使用”，并记录“略过 / 仅学习 / 进入路线图”的取舍，不能包装成已实现亮点。
- 题库至少初始化 RAG、LLM、Dify 工作流、自研 Agent、环境口径、Loop 和后端分层主题。

禁止范围：虚构生产经历、虚构性能/安全指标、为迎合面试临时引入无必要的复杂依赖。

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
6. 阶段完成后先将本文档状态改为 `DONE`；只有已在本文档定义后续阶段时，才移动唯一 `NEXT`。
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

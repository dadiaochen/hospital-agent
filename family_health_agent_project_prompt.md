# 家庭健康 Agent 项目说明与 AI Coding Context

本文件用于给参与项目的开发者或 AI Coding Agent 建立共同上下文。它描述产品目标、不可突破的边界和实施方式；阶段编号、完成状态和后续顺序以 [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) 为唯一权威来源。

## 1. 项目目标

构建一个可本地演示的家庭健康事务管理 Agent MVP，围绕：

- 慢病续方材料整理。
- 中医复诊材料整理。
- 家庭药箱和药店库存查询。
- 用药提醒草稿。
- 高风险用药请求的安全拦截。

系统的价值在于把信息、工具证据、人工确认和审计 trace 组织成可靠流程，而不是让 AI 代替医生下医疗结论。

## 2. 不可突破的医疗边界

- 不诊断疾病，不自动开方，不修改医生处方。
- 不生成自行加量、减量、停药或换药建议。
- 复诊、购药、提醒等关键动作必须经过人工确认。
- 目前确认后也只创建本地 draft，不提交医院、药店、支付或消息推送系统。
- 没有 DB、API 或 RAG 来源时，不生成病史、库存、处方或安全规则等事实。

## 3. 代码结构

```text
api       HTTP 协议、依赖注入和 response
schemas   API Pydantic DTO
models    SQLAlchemy ORM
services  业务查询、草稿和事务
tools     Tool Registry 与受控业务工具
agent     Context、Trace、Harness、后续工作流
rag       检索和来源引用
safety    风险拦截与人工确认判断
core      配置、数据库、日志和异常
```

新功能必须进入正确的层。API 不直接写 SQL，Agent 不绕过 Tool Registry，工具不把未校验的 `dict` 当作可信输入。

## 4. Agent 设计原则

```text
Raw Conversation -> ContextEnvelope -> Role View -> Tool/RAG Evidence
-> Final Answer -> RunSummary/Reset -> Evaluator Review
```

- `user_id` 表示账户，`member_id` 表示本次服务对象，所有来源引用都要与当前成员一致。
- 角色只能得到最小 Role-specific Context View，不广播完整聊天记录。
- Context reset 后保留 summary、trace、答案、工具/RAG 指针和 evaluation 引用，清理 scratchpad、原始对话和未确认推断。
- SafetyAgent 负责事前拦截；EvaluatorAgent 只读事后评估，二者不得混用。

## 5. 工具与审计原则

工具必须声明 input/output schema、permission scope、允许角色、timeout、retry、是否只读和是否需要确认。调用时先检查工具许可、角色、确认和输入 schema，执行后再验证输出 schema，并生成可追踪的 ToolResult。

关键工具：

- 档案、处方、药箱、库存、安全知识：只读 evidence。
- `create_confirmation_draft`：确认后只写本地草稿，记录 run、幂等键和 `not_submitted` 外部状态。

## 6. 编码与验收要求

1. 只实现路线图当前阶段或用户明确指定的目标。
2. 新接口必须有 API DTO；新工具必须有完整 ToolSpec；新状态流转必须有确认与失败路径。
3. 新功能至少有最小正例和失败例测试，尤其检查成员隔离、来源、确认与安全。
4. 代码完成后同步 README、技术/接口/数据库/Agent 文档和测试指南。
5. 只有真实运行过的评估报告才能支持指标结论；mock fixture 指标只能说明规则已被计算。

已完成的 `2E-1` API 层只暴露已有 service 的读取能力，使用固定 demo user 做成员作用域隔离，并返回统一错误响应。不得在读取 API 中加入草稿写入、确认状态机、LangGraph、LLM 或外部医疗集成。

本地完整联调使用 Docker PostgreSQL/Redis，pytest 使用内存 SQLite。知识搜索 DTO、service、route 和 `test_knowledge_api.py` 已完成，并通过 PostgreSQL/Postman 与自动化测试验收。PostgreSQL 实跑要求 Alembic 内部 `version_num` 容纳现有长 revision ID，该兼容修复位于对应长 revision 的迁移中，不改变 ORM 业务字段。

已集成的 `2E-2` 草稿与确认 API 支持四类本地草稿的创建、查询、确认和拒绝；只允许 `draft -> confirmed/rejected`，决策幂等并写入现有 JSON 审计，始终保持 `external_action_status="not_submitted"`。

已集成的 `2F-1` 把知识库关键词查询整理为 Retriever 契约，并提供可注入、默认关闭的向量检索协议。关键词检索始终可用；向量后端只返回 document/chunk 指针和相关性分数，正文从数据库回填。后端缺失、异常或指针失效时必须记录原因并回退，不调用 LLM、不抓取互联网知识、不新增向量表或 migration。

`2F-2` 定义 Model Gateway。默认 provider 是不会联网的 deterministic 实现；可选 OpenAI-compatible HTTP adapter 的 base URL、Key、模型和 timeout 只来自环境变量。所有 provider 文本先过 JSON、目标 Pydantic schema 和输出安全检查，失败时执行同契约 fallback 并记录逐次 Trace；不持久化 prompt 或 Key。

`2G-1` 实现最小正式 LangGraph DAG。Planner 产生结构化计划，ContextManager 投影 Planner/角色最小视图，业务角色只能经 Tool Registry 获取 evidence；所有路径都在确认草稿和 FinalAnswer 前经过 SafetyAgent。关键动作缺少显式确认时不执行 draft handler，高风险阻断时跳过草稿；FinalAnswer 经 Model Gateway 形成冻结 RunTrace，随后 reset 并由 DeterministicEvaluator 只读评估。工作流不接外部医院/药店，也不实现自主循环 Agent。

`2G-2` 增加 Agent Runtime 适配层。FastAPI Router 只接收运行/续跑 DTO，AgentRuntimeService 负责 demo-user/member 作用域、幂等键、真实 DB Tool Registry 注入、run/tool-call 审计和版本化冻结产物持久化。首次 run 不得直接携带确认；只有 `needs_confirmation` run 能以相同 task/member 恢复 RunSummary 和来源指针后续跑，且只创建 `not_submitted` 本地草稿。Evaluator 仍只读；不保存 raw conversation、scratchpad、Key 或 provider 原始文本，不新增 ORM/migration，不接外部系统。

`3A` 实现 Next.js 核心数据页。`MemberProvider` 提供唯一当前 `member_id`，页面通过统一 typed API client 读取真实 FastAPI 契约，并在渲染前检查成员类 response 的 `member_id`。所有数据页必须区分 loading、empty、error 和 data；知识页只消费 2E-1 已实现契约，不复制后端逻辑。3A 不实现登录或外部医疗系统操作。

`3B` 实现主要 Agent 演示入口。前端首次运行固定提交 `human_confirmation_granted=false`，展示冻结答案、Tool/RAG 来源和 SafetyTrace；只有待确认且未阻断的 run 才允许用户勾选本地草稿声明并调用 `/continue`。Run 详情只读展示角色、工具、耗时、错误、fallback、ModelCallTrace 和 EvaluationResult，成员切换清除旧结果并检查所有冻结产物作用域。本阶段不重算评估、不跑 3C 真实 E2E Harness、不提交外部医院/药店/推送动作。

`3C` 实现 Runtime E2E Harness。Runner 通过 FastAPI 发现 seed 成员、执行首次 run 和可选确认续跑，再由独立 adapter 对冻结 artifacts 脱敏并校验 run/task/member 一致性，最后交给 DeterministicEvaluator。固定套件覆盖四个核心业务、真实空数据工具失败、无来源拒答、成员隔离，以及越权成员和首轮确认绕过两个 API Guard；JSON 报告不保存成员/run ID 或答案正文。3C 修复了无来源失败工具被错误加入 ExpectedSource 而导致 HTTP 500 的问题，不新增 ORM/migration，不调用外部系统，也不把本地 deterministic 报告描述为生产或临床指标。

`3D` 完成本地 MVP 收口。Compose backend 镜像包含现有 Alembic 和 seed，并在 Uvicorn 前自动执行 migration 与幂等初始化；PostgreSQL、Redis、FastAPI 和 production-mode Next.js 通过 healthcheck 有序启动。固定 Demo Runner 只调用公开 Runtime API，按父亲续方、母亲复诊、母亲提醒和高风险加量阻断四场景生成脱敏报告。默认仍是关键词 RAG 与 deterministic provider，不使用 Embedding 或真实模型 Key；可选 OpenAI-compatible provider 失败时保持 schema/safety 检查与 deterministic fallback。3D 不新增 ORM/migration，不接外部医院、药店、支付或推送。

`4A` 在不改变默认 3D 演示的前提下实现轻量真实向量 RAG。Migration `0003_lightweight_vector_rag` 为 `knowledge_chunks` 增加可空 512 维 pgvector、模型名、内容哈希和索引时间；FastEmbed provider 仅在启用时加载 `BAAI/bge-small-zh-v1.5`，模型缓存位于项目 `var/models`。Indexer 只重建变化 chunk；pgvector 后端只返回 document/chunk 指针并由权威知识表回填正文。默认开关仍为 false，模型/索引/数据库异常必须留下 fallback reason 并回退关键词。本阶段不部署 RAGFlow，不抓取互联网医疗知识，不自动生成知识写回。

## 7. 阅读顺序

- 协作者：从 [docs/README.md](docs/README.md) 和 [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) 开始。
- Agent 开发者：继续阅读 [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md)、[docs/LANGGRAPH_WORKFLOW.md](docs/LANGGRAPH_WORKFLOW.md)、[docs/CONTEXT_MANAGEMENT.md](docs/CONTEXT_MANAGEMENT.md) 和 [docs/EVALUATOR_AGENT.md](docs/EVALUATOR_AGENT.md)。
- 从零学习者：阅读 [docs/learning/README.md](docs/learning/README.md)。

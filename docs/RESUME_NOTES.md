# 项目亮点与简历表达

## 已实现、可以如实表达的内容

- 设计并实现了面向家庭健康事务的 FastAPI / SQLAlchemy / Pydantic 分层后端基线。
- 建立 Agent ContextEnvelope、Role-specific Context View、Context Compaction 和 run 后 Reset 机制，按 `member_id` 隔离证据和长期记忆。
- 实现 Tool Registry：统一校验工具 schema、角色权限、允许工具、人工确认、失败 fallback 与可追踪输出。
- 实现数据库只读 evidence 工具和 confirmation-gated 本地草稿工具；草稿创建支持成员/用户作用域校验、幂等键和本地审计。
- 实现家庭、药箱、处方/购药、库存、知识检索和 Agent 审计的只读 FastAPI API，使用独立 DTO、稳定来源指针、统一错误响应和固定 demo-user 成员隔离。
- 实现本地草稿创建、查询、确认和拒绝 API，以白名单状态机、幂等决策、成员隔离和 JSON 审计保证确认只改变本地状态。
- 实现 deterministic Agent Harness：固定用例、冻结 RunTrace、规则评估、失败原因与 Markdown 指标报告。
- 区分运行时 SafetyAgent 和 post-run EvaluatorAgent，避免用事后评估代替安全拦截。
- 实现轻量 Hybrid RAG：保留确定性关键词基线，以 FastEmbed 中文 512 维模型和 PostgreSQL pgvector 做可选语义召回；通过模型名/内容哈希幂等索引、来源指针回填和异常降级约束证据。
- 实现 Model Gateway：统一 deterministic 与 OpenAI-compatible provider 契约，在 Pydantic 解析和规则安全检查失败时执行可追踪 fallback；尚未进行真实线上模型质量评测。
- 实现有界 LangGraph Multi-Agent DAG：以 intent 路由角色，复用 ContextManager、Tool Registry、SafetyAgent、确认门、Model Gateway、RunTrace/reset 和只读 Evaluator。
- 实现 Agent Runtime API：注入真实 DB tools，持久化 run/tool-call 与版本化冻结产物，支持成员隔离、幂等 replay、确认后的同任务续跑和失败审计；不执行外部医疗动作。
- 实现 Next.js 核心数据页面：统一 API client、loading/empty/error、成员切换、旧请求取消和 response `member_id` 二次检查。
- 实现 Agent 对话与审计 UI：连接首次未确认 run、本地草稿确认续跑、冻结答案、Tool/RAG 来源、安全标记、工具错误/fallback 和单次 EvaluationResult；高风险拦截不提供业务继续入口。
- 实现 Runtime E2E Harness：从 FastAPI 外部执行正常、风险、工具失败、无来源和成员隔离用例，经脱敏 Trace adapter 接入独立评估规则，并输出用例级 JSON/Markdown 报告。
- 完成本地 MVP 交付链：Docker Compose 自动执行 migration 与幂等 seed，以 healthcheck 编排 PostgreSQL、Redis、FastAPI 和 Next.js，并用公开 API 固定演示续方、复诊、提醒和高风险阻断。

## 简历表述示例

```text
设计并实现家庭健康事务 Agent 的可追踪 Harness：以 Pydantic 契约约束 Context、Tool、Trace 与 EvaluationResult，结合成员隔离、来源引用和人工确认门禁，支持固定用例的 deterministic 回放与质量评估。

构建 Tool Registry 与数据库适配层，为档案、处方、药箱、库存和安全规则提供可审计的只读 evidence；关键业务动作仅在确认后创建本地草稿，并通过幂等状态机确认或拒绝本地记录，不触发真实医院或药店提交。

设计 Hybrid RAG 检索层，以 PostgreSQL 关键词检索作为稳定基线，接入 FastEmbed CPU 中文模型与 pgvector 精确余弦检索；向量召回只提供 document/chunk 指针，正文由权威知识表回填，索引/模型异常时记录原因并安全降级。

实现可替换 Model Gateway，将 deterministic 与 OpenAI-compatible provider 接入同一 Runtime 创建链；以 Pydantic 约束结构化输出、规则门禁拦截越权文本，并为 provider 超时、HTTP/schema/safety 失败记录逐次 Trace 和 deterministic fallback。提供默认不联网、显式 live 才发请求的诊断器，区分 primary 成功与降级成功。

实现有界 LangGraph 业务编排，将 Planner、角色最小上下文、证据工具、安全拦截、人工确认草稿和 post-run 评估连接为无循环 DAG；通过冻结 RunTrace 保留成员、来源、确认与失败原因。

实现 Agent Runtime 适配层，将真实数据库 evidence、LangGraph 运行、run/tool-call 审计和冻结 EvaluationResult 串联；以版本化最小产物支持可查询回放，并通过固定 continuation run 与请求指纹避免重复确认草稿。

使用 Next.js、React 与 TypeScript 构建家庭档案、药箱、续方复诊和提醒等数据页面，统一封装异步请求状态；通过共享成员上下文、请求取消和 response member_id 校验降低家庭成员切换时的数据串扰风险。

实现 Agent 对话与 Trace UI，将 typed Runtime API、浏览器幂等键、显式人工确认、冻结来源与安全结果串成可审计交互；成员切换清除旧 run，高风险阻断不可通过前端确认绕过，所有动作只落本地草稿。

构建面向 Runtime API 的 E2E Harness，通过固定 ExpectedCase 驱动首次 run、确认续跑和 HTTP Guard；在评估前执行敏感字段脱敏与 run/task/member 一致性校验，并将工具失败、无来源拒答和成员隔离纳入可重复回归。

将本地 MVP 的 migration、幂等 seed、服务健康检查和固定四场景纳入一键 Docker 交付；演示 Runner 只走公开 API，三类关键动作经确认后仅创建 `not_submitted` 本地草稿，高风险请求保持阻断，并输出不含成员/run ID 与答案正文的报告。
```

## 面试时怎么讲

先讲问题：医疗业务的难点不是让模型“更像医生”，而是防止模型越权、编造事实、串成员数据或绕过确认。

再讲设计：用 ContextManager 做最小视图，用 ToolRegistry 做权限和 schema 门禁，用来源指针限制事实，用 SafetyAgent 做事前拦截，用 Evaluator 做事后回放。

最后讲证据：指出测试覆盖契约、成员隔离、无来源硬答、缺工具、缺安全标记、禁用表达和确认缺失等失败路径。

## 不能夸大的内容

- 不要说已上线生产、接入真实医院/药店、自动开方、诊断或修改处方。
- 不要把 deterministic mock Harness 说成真实 LLM 或临床评测。
- 不要声称 `100% safety recall`、`0 hallucination` 或特定 p95 延迟，除非有对应真实运行的评估报告和数据范围。
- 3C 已在本地 PostgreSQL + deterministic provider + seed 数据上执行 7 条 Trace 和 2 条 Guard；不能把这个小规模固定用例结果描述成生产、临床或真实 LLM 指标。
- 3D 已在全新 Docker PostgreSQL volume + deterministic provider 上执行固定四场景并得到 4/4 通过；这只证明打包、初始化与当前固定规则可重复，不能外推为临床安全率或真实 LLM 质量。
- 当前默认 RAG 仍不使用 Embedding；4A 向量模式需要显式启用。可以如实说明已本地部署 pgvector/FastEmbed 并完成 4 个 seed chunk 的 smoke，不得把该小样本扩张为生产检索质量。
- 知识库搜索已完成自动化与本地 PostgreSQL/Postman 验证，但不能把本地联调描述为生产检索质量或临床有效性验证。
- 不要把 RAG `score` 描述为医疗正确率。4A 的 90.81 MB 缓存、容器内存和 4/4 场景是一次本地开发验证，不是容量、p95、临床安全或生产 SLO。
- 不要把 MockTransport 或 deterministic provider 测试描述为真实 LLM 效果，也不要宣称模型准确率、安全率、成本或 p95 延迟。
- 4B 已验证配置契约、Runtime 接线、HTTP mock、fallback 和无 Key 模式；没有用户真实 Key，所以不能说某个云模型或本地 LLM 已在业务四场景通过真实质量验收。

本地报告记录的 18 ms 是冻结 Trace 内工具与 deterministic model gateway 累计 latency 的 p95，不是浏览器端到端延迟或服务 SLO。简历优先描述“建立评估维度与可重复 E2E”，只有在面试官追问报告范围时再说明样本、环境和口径。

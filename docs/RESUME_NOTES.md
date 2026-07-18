# 项目亮点与简历表达

## 已实现、可以如实表达的内容

- 设计并实现了面向家庭健康事务的 FastAPI / SQLAlchemy / Pydantic 分层后端基线。
- 建立 Agent ContextEnvelope、Role-specific Context View、Context Compaction 和 run 后 Reset 机制，按 `member_id` 隔离证据和长期记忆。
- 实现 Tool Registry：统一校验工具 schema、角色权限、允许工具、人工确认、失败 fallback 与可追踪输出。
- 实现数据库只读 evidence 工具和 confirmation-gated 本地草稿工具；草稿创建支持成员/用户作用域校验、幂等键和本地审计。
- 实现家庭、药箱、处方/购药、库存和 Agent 审计的只读 FastAPI API，使用独立 DTO、统一错误响应和固定 demo-user 成员隔离。
- 在隔离 2E-2 分支实现本地草稿创建、查询、确认和拒绝 API，以白名单状态机、幂等决策、成员隔离和 JSON 审计保证确认只改变本地状态；该能力需在 2E-1 完成后整合进主线再作为最终项目交付表述。
- 实现 deterministic Agent Harness：固定用例、冻结 RunTrace、规则评估、失败原因与 Markdown 指标报告。
- 区分运行时 SafetyAgent 和 post-run EvaluatorAgent，避免用事后评估代替安全拦截。
- 在隔离 2F-1 分支实现 Hybrid RAG Retriever：保留确定性关键词基线，以来源指针回填数据库正文，并对向量后端缺失、超时和失效指针执行可追踪降级；进入主线后再作为最终交付表述。
- 在隔离 2F-2 分支实现 Model Gateway：统一 deterministic 与 OpenAI-compatible provider 契约，在 Pydantic 解析和规则安全检查失败时执行可追踪 fallback；尚未进行真实线上模型质量评测。
- 在隔离 2G-1 分支实现有界 LangGraph Multi-Agent DAG：以 intent 路由角色，复用 ContextManager、Tool Registry、SafetyAgent、确认门、Model Gateway、RunTrace/reset 和只读 Evaluator。
- 在线性 2G-2 隔离分支实现 Agent Runtime API：注入真实 DB tools，持久化 run/tool-call 与版本化冻结产物，支持成员隔离、幂等 replay、确认后的同任务续跑和失败审计；不执行外部医疗动作。
- 在 3A 隔离分支实现 Next.js 核心数据页面：统一 API client、loading/empty/error、成员切换、旧请求取消和 response `member_id` 二次检查；知识页真实联调等待 2E-1 API 合入。

## 简历表述示例

```text
设计并实现家庭健康事务 Agent 的可追踪 Harness：以 Pydantic 契约约束 Context、Tool、Trace 与 EvaluationResult，结合成员隔离、来源引用和人工确认门禁，支持固定用例的 deterministic 回放与质量评估。

构建 Tool Registry 与数据库适配层，为档案、处方、药箱、库存和安全规则提供可审计的只读 evidence；关键业务动作仅在确认后创建本地草稿，并通过幂等状态机确认或拒绝本地记录，不触发真实医院或药店提交。

设计 Hybrid RAG 检索层，以 PostgreSQL 关键词检索作为稳定基线，通过协议注入可选向量后端；向量召回只提供 document/chunk 指针，正文由权威知识表回填，异常时记录原因并安全降级。

实现可替换 Model Gateway，以 Pydantic 约束结构化输出、规则门禁拦截越权文本，并为 provider 超时、HTTP/schema/safety 失败记录逐次 Trace 和 deterministic fallback。

实现有界 LangGraph 业务编排，将 Planner、角色最小上下文、证据工具、安全拦截、人工确认草稿和 post-run 评估连接为无循环 DAG；通过冻结 RunTrace 保留成员、来源、确认与失败原因。

实现 Agent Runtime 适配层，将真实数据库 evidence、LangGraph 运行、run/tool-call 审计和冻结 EvaluationResult 串联；以版本化最小产物支持可查询回放，并通过固定 continuation run 与请求指纹避免重复确认草稿。

使用 Next.js、React 与 TypeScript 构建家庭档案、药箱、续方复诊和提醒等数据页面，统一封装异步请求状态；通过共享成员上下文、请求取消和 response member_id 校验降低家庭成员切换时的数据串扰风险。
```

## 面试时怎么讲

先讲问题：医疗业务的难点不是让模型“更像医生”，而是防止模型越权、编造事实、串成员数据或绕过确认。

再讲设计：用 ContextManager 做最小视图，用 ToolRegistry 做权限和 schema 门禁，用来源指针限制事实，用 SafetyAgent 做事前拦截，用 Evaluator 做事后回放。

最后讲证据：指出测试覆盖契约、成员隔离、无来源硬答、缺工具、缺安全标记、禁用表达和确认缺失等失败路径。

## 不能夸大的内容

- 不要说已上线生产、接入真实医院/药店、自动开方、诊断或修改处方。
- 不要把 deterministic mock Harness 说成真实 LLM 或临床评测。
- 不要声称 `100% safety recall`、`0 hallucination` 或特定 p95 延迟，除非有对应真实运行的评估报告和数据范围。
- Agent HTTP API、运行持久化和 3A 数据页已在隔离分支实现，但尚未整合进主线；3B 对话、确认和 Trace UI 仍未完成。
- 知识库搜索 API 被保留为学习实战题；在完成并测试前不能称其已实现。
- 不要把 RAG `score` 描述为医疗正确率，也不要声称已接入真实 Embedding 或向量数据库；当前实现的是接口、关键词基线和可测试的注入/降级机制。
- 不要把 MockTransport 或 deterministic provider 测试描述为真实 LLM 效果，也不要宣称模型准确率、安全率、成本或 p95 延迟。

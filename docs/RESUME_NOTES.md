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
- 使用 Docker Compose 编排 PostgreSQL、Redis、FastAPI 和 Next.js 本地开发环境，完成真实 PostgreSQL migration、可重复 seed 与读取 API 联调；pytest 使用内存 SQLite 保持隔离。

## 简历表述示例

```text
设计并实现家庭健康事务 Agent 的可追踪 Harness：以 Pydantic 契约约束 Context、Tool、Trace 与 EvaluationResult，结合成员隔离、来源引用和人工确认门禁，支持固定用例的 deterministic 回放与质量评估。

构建 Tool Registry 与数据库适配层，为档案、处方、药箱、库存和安全规则提供可审计的只读 evidence；关键业务动作仅在确认后创建本地草稿，并通过幂等状态机确认或拒绝本地记录，不触发真实医院或药店提交。
```

## 面试时怎么讲

先讲问题：医疗业务的难点不是让模型“更像医生”，而是防止模型越权、编造事实、串成员数据或绕过确认。

再讲设计：用 ContextManager 做最小视图，用 ToolRegistry 做权限和 schema 门禁，用来源指针限制事实，用 SafetyAgent 做事前拦截，用 Evaluator 做事后回放。

最后讲证据：指出测试覆盖契约、成员隔离、无来源硬答、缺工具、缺安全标记、禁用表达和确认缺失等失败路径。

## 不能夸大的内容

- 不要说已上线生产、接入真实医院/药店、自动开方、诊断或修改处方。
- 不要把 deterministic mock Harness 说成真实 LLM 或临床评测。
- 不要声称 `100% safety recall`、`0 hallucination` 或特定 p95 延迟，除非有对应真实运行的评估报告和数据范围。
- 真实 Agent API、LLM Gateway、LangGraph workflow 和前端业务闭环仍按 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 后续阶段实现。
- 知识库搜索已通过专用 API 自动化测试和本地 PostgreSQL/Postman 验证；两者分别证明接口回归与本地集成，不应表述为生产性能或临床有效性验证。
- Docker Compose 本地联调不能表述为生产部署、容灾或性能验收。

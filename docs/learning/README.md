# 从零学习本项目

这是一套以当前仓库为案例的工程学习路径。目标不是背框架名词，而是学会从一个模糊需求出发，逐步做出可演示、可测试、可解释的系统，并能在实习面试中讲清自己的设计判断。

## 建议顺序

| 模块 | 你会学什么 | 先读什么代码 |
| --- | --- | --- |
| [01 需求与范围](01_REQUIREMENTS_AND_SCOPE.md) | 用户故事、非目标、验收与阶段拆分。 | `docs/PRD.md`、`docs/DEVELOPMENT_ROADMAP.md` |
| [02 后端与数据](02_BACKEND_AND_DATA.md) | 分层、ORM、字段、Pydantic、service 和事务。 | `backend/app/models/`、`services/` |
| [03 Agent Harness](03_AGENT_HARNESS_AND_SAFETY.md) | Context、工具、Trace、安全、确认和评估。 | `backend/app/agent/`、`tools/` |
| [04 测试、Review 与交付](04_TESTING_REVIEW_AND_DELIVERY.md) | fixture、失败路径、Git 分支、review 和文档。 | `backend/tests/`、`AGENTS.md` |
| [05 简历与面试](05_RESUME_AND_INTERVIEW.md) | 技术亮点、故事线、追问与表达边界。 | `docs/RESUME_NOTES.md` |
| [06 2E-1 实战题](06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md) | 在 Docker PostgreSQL 上从零完成 DTO、service、路由、测试、Swagger 与 Postman 验收，并逐层理解客户端、依赖注入和四个核心文件。 | `backend/app/api/routes/knowledge.py`、`backend/app/schemas/knowledge.py`、`backend/app/services/knowledge_read_service.py`、`backend/app/models/knowledge.py` |
| [07 2F-1 Hybrid RAG](07_2F1_HYBRID_RAG.md) | 理解 Retriever、关键词评分、来源回填、功能开关和降级测试。 | `backend/app/rag/`、`test_hybrid_rag.py` |
| [08 2F-2 Model Gateway](08_2F2_MODEL_GATEWAY.md) | 理解 provider 抽象、结构化输出、安全门禁、fallback 和调用 Trace。 | `backend/app/agent/model_gateway.py` |
| [09 2G-1 LangGraph 工作流](09_2G1_LANGGRAPH_WORKFLOW.md) | 从计划、状态、节点和条件边读懂四场景编排、上下文、工具、安全、确认、reset 与评估。 | `backend/app/agent/workflow_planning.py`、`langgraph_workflow.py` |
| [10 2G-2 Agent Runtime API](10_2G2_AGENT_RUNTIME_API.md) | 从 HTTP 请求一路读到 Service、LangGraph、真实 DB tools、审计持久化、确认续跑与冻结回放。 | `agent_audit.py`、`agent_runtime_service.py`、`runtime_schemas.py` |
| [11 3A 前端数据页面](11_3A_FRONTEND_DATA_PAGES.md) | 从 React 状态、HTTP client 和成员上下文读懂 loading/empty/error 与跨成员防线。 | `MemberProvider.tsx`、`client.ts`、各 `page.tsx` |
| [12 3B Agent UI 与 Trace](12_3B_AGENT_UI_AND_TRACE.md) | 从 POST 请求、幂等和人工确认，读懂来源、安全、冻结 Trace 与 Postman 验证。 | `app/agent/page.tsx`、`AgentRunResult.tsx`、`RunTraceDetails.tsx` |
| [13 3C Runtime E2E 与 Dify](13_3C_RUNTIME_E2E_AND_DIFY.md) | 从 Dify 节点设计过渡到自研 Runtime Harness，理解环境、真实 Trace、脱敏、Guard 与面试表达。 | `runtime_harness.py`、`runtime_trace_adapter.py`、`test_runtime_e2e_harness.py` |

## 使用方法

每一章都按同一顺序展开：先解释问题，再给出本项目的取舍，接着指向代码与字段，最后给出你可以自己完成的练习。不要只读文档：环境与真实 API 联调使用 Docker PostgreSQL，自动化测试使用内存 SQLite；每读完一章，都运行一次对应测试或在 GitHub Desktop 观察一次变更。

## 最小学习节奏

第一周完成模块 01 和 02：理解范围、数据模型和后端分层。第二周完成模块 03：理解为什么 Agent 需要 Context、工具和安全门禁。第三周完成模块 04 和 05：学会写测试、review PR，并把项目讲成一个可信的实习作品。

学习资料讲解的是当前代码与设计，不会替代 [DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) 的实施顺序。

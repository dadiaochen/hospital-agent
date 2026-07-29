# 从零学习本项目

> 学习文档按项目形成过程保留，适合逐步理解旧接口和代码演进。它们不是当前阶段计划或最终架构的权威来源；遇到旧 Agent 名称、`human_confirmation_granted` 或旧阶段号时，请同时对照 [开发总路线图](../DEVELOPMENT_ROADMAP.md) 与 [技术设计](../TECH_DESIGN.md)。

这是一套以当前仓库为案例的工程学习路径。目标不是背框架名词，而是学会从一个模糊需求出发，逐步做出可演示、可测试、可解释的系统，并能在实习面试中讲清自己的设计判断。

## 建议顺序

| 模块 | 你会学什么 | 先读什么代码 |
| --- | --- | --- |
| [00 从 0 到 1 主线](00_AGENT_PROJECT_FROM_ZERO_TO_ONE.md) | 把需求、ContextEnvelope、Tool Registry、LangGraph、Agent 安全、RunTrace、Agent 评测和简历指标串成一条完整工程链路；每一步都有当前仓库的关键函数。 | `docs/PRD.md`、`backend/app/agent/`、`backend/app/tools/` |
| [01 需求与范围](01_REQUIREMENTS_AND_SCOPE.md) | 用户故事、非目标、验收与阶段拆分。 | `docs/PRD.md`、`docs/DEVELOPMENT_ROADMAP.md` |
| [02 后端与数据](02_BACKEND_AND_DATA.md) | 分层、ORM、字段、Pydantic、service 和事务。 | `backend/app/models/`、`services/` |
| [03 Agent Harness](03_AGENT_HARNESS_AND_SAFETY.md) | Context、工具、Trace、安全、确认和评估。 | `backend/app/agent/`、`tools/` |
| [04 测试、Review 与交付](04_TESTING_REVIEW_AND_DELIVERY.md) | fixture、失败路径、指标口径、Git 分支、review 和文档。 | `backend/tests/`、`docs/AGENT_EVAL_REPORT.md`、`AGENTS.md` |
| [05 简历与面试](05_RESUME_AND_INTERVIEW.md) | 技术亮点、项目故事线、Agent/RAG 追问与表达边界。 | `docs/RESUME_NOTES.md`、`docs/INTERVIEW_QA.md`、`docs/INTERVIEW_QA_TEST_ENGINEERING.md` |
| 通用计算机基础八股 | Java、网络、操作系统、Redis、MySQL、消息队列、手撕/LeetCode、Vibe Coding 和 Transformer。 | `docs/GENERAL_INTERVIEW_KNOWLEDGE.md` |
| [06 2E-1 实战题](06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md) | 在 Docker PostgreSQL 上从零完成 DTO、service、路由、测试、Swagger 与 Postman 验收，并逐层理解客户端、依赖注入和四个核心文件。 | `backend/app/api/routes/knowledge.py`、`backend/app/schemas/knowledge.py`、`backend/app/services/knowledge_read_service.py`、`backend/app/models/knowledge.py` |
| [07 2F-1 Hybrid RAG](07_2F1_HYBRID_RAG.md) | 理解 Retriever、关键词评分、来源回填、功能开关和降级测试。 | `backend/app/rag/`、`test_hybrid_rag.py` |
| [08 2F-2 Model Gateway](08_2F2_MODEL_GATEWAY.md) | 理解 provider 抽象、结构化输出、安全门禁、fallback 和调用 Trace。 | `backend/app/agent/model_gateway.py` |
| [09 2G-1 LangGraph 工作流](09_2G1_LANGGRAPH_WORKFLOW.md) | 从计划、状态、节点和条件边读懂四场景编排、上下文、工具、安全、确认、reset 与评估。 | `backend/app/agent/workflow_planning.py`、`langgraph_workflow.py` |
| [10 2G-2 Agent Runtime API](10_2G2_AGENT_RUNTIME_API.md) | 从 HTTP 请求一路读到 Service、LangGraph、真实 DB tools、审计持久化、确认续跑与冻结回放。 | `agent_audit.py`、`agent_runtime_service.py`、`runtime_schemas.py` |
| [11 3A 前端数据页面](11_3A_FRONTEND_DATA_PAGES.md) | 从 React 状态、HTTP client 和成员上下文读懂 loading/empty/error 与跨成员防线。 | `MemberProvider.tsx`、`client.ts`、各 `page.tsx` |
| [12 3B Agent UI 与 Trace](12_3B_AGENT_UI_AND_TRACE.md) | 从 POST 请求、幂等和人工确认，读懂来源、安全、冻结 Trace 与 Postman 验证。 | `app/agent/page.tsx`、`AgentRunResult.tsx`、`RunTraceDetails.tsx` |
| [13 Dify 患者端医疗服务智能体](13_DIFY_PATIENT_HEALTH_AGENT_INTERNSHIP.md) | 还原互联网医院实习业务，设计诊前问诊、慢病复诊、诊后用药和智能舌诊四条工作流，并准备简历与面试表达。 | Dify Chatflow / Workflow、公司已有问诊/处方/购药/舌诊服务 |
| [14 3D MVP 交付](14_3D_MVP_DELIVERY.md) | 用固定脚本启动、验证和演示后端、前端与 Agent 链路。 | `scripts/demo/`、`docs/DEMO_RUNBOOK.md` |
| [15 4A 轻量向量 RAG](15_4A_LIGHTWEIGHT_VECTOR_RAG.md) | 理解 FastEmbed、本地索引、pgvector 和关键词降级的组合。 | `backend/app/rag/`、`backend/app/services/knowledge_index_service.py` |
| [16 4B LLM 双模式](16_4B_LLM_DUAL_MODE.md) | 理解 deterministic provider、OpenAI-compatible provider、结构化输出和 fallback。 | `backend/app/agent/model_gateway.py`、`backend/app/agent/provider.py` |
| [17 核心代码走读](17_CORE_CODE_WALKTHROUGH.md) | 按真实调用链学习 Planner、Supervisor、领域 Agent、Safety、Context、RAG、Model Gateway、Trace 和 Evaluator 的关键实现。 | `backend/app/agent/`、`backend/app/services/business_task_service.py`、`backend/app/tools/` |

## 使用方法

建议先完整阅读 00 主线，再按 01 至 05 逐章深入。每一章都按同一顺序展开：先解释问题，再给出本项目的取舍，接着指向代码与字段，最后给出你可以自己完成的练习。不要只读文档：环境与真实 API 联调使用 Docker PostgreSQL，自动化测试使用内存 SQLite；每读完一章，都运行一次对应测试或在 GitHub Desktop 观察一次变更。

指标学习要同时阅读 [AGENT_EVAL_REPORT.md](../AGENT_EVAL_REPORT.md)。特别注意：当前的 groundedness、工具覆盖率和确认提示率都是固定用例的流程指标，不能直接当成答案正确率、工具参数准确率或人工采纳率。

## 最小学习节奏

第一周完成模块 01 和 02：理解范围、数据模型和后端分层。第二周完成模块 03：理解为什么 Agent 需要 Context、工具和安全门禁。第三周完成模块 04 和 05：学会写测试、review PR，并把项目讲成一个可信的实习作品。

学习资料讲解的是当前代码与设计，不会替代 [DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) 的实施顺序。

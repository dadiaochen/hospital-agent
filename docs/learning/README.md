# 项目学习中心

这里不再按开发阶段堆放教程。学习材料只分成三类：项目工程与代码、简历、项目面经。

路线图状态以 [开发总路线图](../DEVELOPMENT_ROADMAP.md) 为准，当前架构以 [技术设计](../TECH_DESIGN.md) 为准。学习文档负责解释“为什么这样设计、代码怎样工作、怎样 review”，不维护另一套阶段计划。

## 1. 项目工程与代码

这是当前需要重点学习的部分，按顺序阅读。

| 顺序 | 文档 | 解决的问题 |
| --- | --- | --- |
| 1 | [从 0 到 1 设计项目](PROJECT_ENGINEERING_GUIDE.md) | 怎样澄清需求、拆分任务、做技术选型、确定数据和安全边界、安排开发顺序、设计测试与交付 |
| 2 | [核心代码逐行走读](CORE_CODE_WALKTHROUGH.md) | 从 API、Service、状态、Supervisor、领域 Agent、Agent 安全、Context、Tool、RAG、模型、Trace 到评测，理解变量、语法、副作用和失败路径 |
| 3 | [完整 API 实战](API_DEVELOPMENT_TUTORIAL.md) | 从零实现并运行一个 FastAPI + Pydantic + SQLAlchemy + PostgreSQL 接口，完成测试、Swagger 和 Postman 验收 |

配套开发文档：

- [本地环境与 Docker 启动](../LOCAL_SETUP_AND_DEPLOYMENT.md)
- [开发者指南](../DEVELOPER_GUIDE.md)
- [测试与 Review 指南](../TESTING_GUIDE.md)
- [核心 API 契约](../API_SPEC.md)
- [Agent 架构](../AGENT_ARCHITECTURE.md)
- [上下文与记忆](../CONTEXT_MANAGEMENT.md)
- [RAG](../RAG_RETRIEVAL.md)
- [Agent 安全](../SAFETY_POLICY.md)

### 推荐学习节奏

1. 第一遍只画全链路，不抄代码：用户请求经过哪些层，每层输入和输出是什么。
2. 第二遍跟着核心代码走读打开真实文件，逐行回答“变量从哪里来、返回到哪里、是否访问数据库、怎样失败”。
3. 第三遍完成 API 实战，并用 Swagger、Postman 和 pytest 验收。
4. 第四遍选一个失败场景，修改 fixture 或测试，观察成员隔离、安全、来源或重试规则如何阻止错误。
5. 最后不用文档，独立画出架构、数据流、确认状态机和测试分层。

## 2. 简历

本轮只分类，不修改简历内容。

| 文档 | 用途 |
| --- | --- |
| [简历完整写法](RESUME_GUIDE.md) | Agent/后端方向版本、项目介绍、指标选择与表达模板 |
| [简历事实与证据边界](../RESUME_NOTES.md) | 哪些能力和数字可以写，哪些仍是本地、deterministic 或未验证结果 |

简历数字必须能回到测试命令、固定样本、报告和 Git commit。没有真实运行的数据保持 `N/A`。

## 3. 项目面经

本轮只分类，不改写答案。

| 文档 | 用途 |
| --- | --- |
| [项目面试完整问答](../INTERVIEW_QA.md) | 从项目介绍到 Multi-Agent、RAG、上下文、安全、评测和上线追问 |
| [当前简历与面试口径](../RESUME_NOTES.md) | 业务背景、多 Agent 链路、最新指标和口述版本 |
| [Dify 实习项目](DIFY_PROJECT_GUIDE.md) | 原 Dify 业务流程、节点设计、与当前自研项目的关系 |
| [测试工程追问](../INTERVIEW_QA_TEST_ENGINEERING.md) | pytest、fixture、异常测试、Agent Harness 和评测集问题 |

面经只使用项目真实术语和证据。`SafetyAgent` 在面试表达中称为“Agent 安全”，`EvaluatorAgent` 对应“Agent 评测”；不要把内部类名当成开场介绍。

## 已删除的材料

原来按 2F、2G、3A、3B、3D、4A、4B 等阶段拆出的短教程已经被三条主线和当前设计文档覆盖。它们被删除后，不再要求你在旧角色、旧阶段号和当前实现之间反复切换。

旧的通用 Java/MySQL 八股不属于这个项目的学习主线，也从项目文档中移除。需要准备通用基础时，应使用独立的求职知识库，而不是混入本项目上下文。

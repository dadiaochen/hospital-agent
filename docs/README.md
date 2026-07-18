# 项目文档导航

本目录只保留当前有效的项目文档。阶段编号、状态、顺序和 MVP 验收标准以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为唯一来源；其他文档不重复维护阶段流水账。

## 新加入项目

1. 阅读 [PRD.md](PRD.md)，理解业务问题、用户和非目标。
2. 第一次运行先阅读 [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md)，再阅读 [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) 准备分支和提交。
3. 阅读 [TECH_DESIGN.md](TECH_DESIGN.md)，理解后端、数据、工具和 Agent 的边界。
4. 根据要修改的模块继续阅读接口、数据库或 Agent 专项文档。

## 开发与交付

| 文档 | 何时阅读 | 负责回答的问题 |
| --- | --- | --- |
| [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md) | 第一次运行或环境故障时 | 如何配置 WSL 2、把 Docker 数据放到 E 盘、启动 PostgreSQL/Redis、停机和排错？ |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | 开始开发前 | 如何启动、测试、分支和提交？ |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | 编码和 review 时 | 测什么、如何复现、如何审查？ |
| [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) | 选择下一项工作前 | 现在到哪个阶段，下一步能做什么？ |
| [RESUME_NOTES.md](RESUME_NOTES.md) | 准备作品集或面试时 | 哪些亮点已实现，哪些指标不能宣称？ |

## 产品、技术与数据

| 文档 | 内容 |
| --- | --- |
| [PRD.md](PRD.md) | 用户、核心场景、MVP 与医疗非目标。 |
| [TECH_DESIGN.md](TECH_DESIGN.md) | 分层架构、数据流、安全与当前实现边界。 |
| [API_SPEC.md](API_SPEC.md) | 已实现 HTTP 接口、未来接口的契约边界。 |
| [DB_SCHEMA.md](DB_SCHEMA.md) | ORM 表、字段用途、关系、索引与审计原则。 |
| [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md) | Retriever 契约、关键词基线、向量来源回填与降级。 |
| [MODEL_GATEWAY.md](MODEL_GATEWAY.md) | 模型 provider、结构化输出、安全门禁、降级和调用 Trace。 |
| [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md) | 有界状态图、节点路由、工具调用、确认与运行产物。 |
| [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md) | Agent 运行 API、run/tool-call 持久化、冻结回放、幂等与确认续跑。 |

## Agent 专项

| 文档 | 内容 |
| --- | --- |
| [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | Planner、业务角色、SafetyAgent、EvaluatorAgent 的工作流。 |
| [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) | ContextEnvelope、角色视图、压缩、reset 和长期记忆门槛。 |
| [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) | 固定用例、冻结 Trace、确定性评估器和报告口径。 |
| [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md) | Planner 到 Evaluator 的正式 LangGraph DAG 与实现边界。 |
| [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md) | 真实 DB tools 如何接入工作流并持久化可查询审计产物。 |
| [agent_eval_report.example.md](agent_eval_report.example.md) | mock fixture 运行后的示例报告，不代表生产或医疗指标。 |

## 从零学习本项目

学习材料在 [learning/README.md](learning/README.md)。它不是运行手册，而是把本项目作为一堂完整工程课：从需求和风险边界开始，经过 Docker/PostgreSQL 环境、数据与后端、Agent Harness、测试 review，最后落到简历和面试表达。

## 文档维护规则

- README 面向 GitHub 访客，保持短而能运行。
- 本目录的开发文档面向协作者，给出事实、命令和边界。
- 设计文档描述当前有效结构；历史由 Git 和总路线图承载。
- 新功能先更新对应契约、测试和文档，再声称已经完成。

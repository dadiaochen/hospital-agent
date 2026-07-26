# 项目文档导航

本目录只保留当前有效的项目文档。阶段编号、状态、顺序和最终产品验收标准以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为唯一来源；其他文档不得维护相互竞争的阶段计划。

## 新加入项目

1. 阅读 [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md)，确认哪些能力已经实现。
2. 阅读 [PRD.md](PRD.md) 和 [BUSINESS_WORKFLOWS.md](BUSINESS_WORKFLOWS.md)，理解三条业务线及医疗边界。
3. 阅读 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 和 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)，确认当前阶段与最终验收。
4. 第一次运行先阅读 [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md)，开发协作再阅读 [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)。

## 开发与交付

| 文档 | 负责回答的问题 |
| --- | --- |
| [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) | 当前阶段、阶段顺序和最终成品标准是什么 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 4A、4B、4C 各自交付什么 |
| [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md) | 如何安装、迁移、启动和部署 |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | 如何按分层规则开发 |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | 如何运行测试和验收 |
| [migration_validation_report.4b.md](migration_validation_report.4b.md) | 4B 当前 PostgreSQL、Alembic、seed 和 backend 真实开发环境验证记录 |
| [RESUME_NOTES.md](RESUME_NOTES.md) | 哪些亮点可以进入简历，哪些指标还不能写 |

4B 的八项剩余任务、完成证据和未完成边界只看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 的“4B 剩余任务拆分与审计”章节；本阶段当前已推进到任务四，任务五至八仍未开始。

## 产品与架构

| 文档 | 内容 |
| --- | --- |
| [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md) | 当前代码、文档与目标产品的差距 |
| [PRD.md](PRD.md) | 产品范围、用户、业务目标与验收边界 |
| [BUSINESS_WORKFLOWS.md](BUSINESS_WORKFLOWS.md) | 智能预问诊、慢病管理与购药、报告解读三条业务线 |
| [TECH_DESIGN.md](TECH_DESIGN.md) | 总体技术架构与分层设计 |
| [API_SPEC.md](API_SPEC.md) | HTTP API 契约 |
| [DB_SCHEMA.md](DB_SCHEMA.md) | 数据模型与持久化约束 |
| [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md) | 向量检索优先、关键词精确检索与降级策略 |
| [TOOL_CONTRACTS.md](TOOL_CONTRACTS.md) | Tool Registry、provider 与证据契约 |
| [SAFETY_POLICY.md](SAFETY_POLICY.md) | Agent 安全、人工确认与医疗边界 |
| [MODEL_GATEWAY.md](MODEL_GATEWAY.md) | 模型接入、结构化输出与失败降级 |
| [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) | 患者端前端架构与最终交付标准 |

## Agent 与评测

| 文档 | 内容 |
| --- | --- |
| [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) | Multi-Agent 职责、LangGraph 状态图和运行顺序 |
| [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) | ContextEnvelope、成员隔离、压缩与重置 |
| [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) | Agent 评测、RAG 指标和只读评估边界 |
| [AGENT_EVAL_REPORT.md](AGENT_EVAL_REPORT.md) | 当前 16 条固定用例的真实回放结果、指标口径和简历使用边界 |
| [provider_adapter_validation_report.4b.md](provider_adapter_validation_report.4b.md) | Provider mock、成员来源和确认门的 Docker smoke 记录 |
| [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md) | Agent 运行时 API 与流式事件 |
| [agent_eval_report.example.md](agent_eval_report.example.md) | 评测报告格式示例 |

## 学习与面试

- [learning/README.md](learning/README.md)：按项目实现顺序整理的学习材料。
- [learning/00_AGENT_PROJECT_FROM_ZERO_TO_ONE.md](learning/00_AGENT_PROJECT_FROM_ZERO_TO_ONE.md)：从需求拆分到代码、测试、指标和简历的教程式主线。
- [learning/05_RESUME_AND_INTERVIEW.md](learning/05_RESUME_AND_INTERVIEW.md)：简历与口述准备。
- [learning/13_DIFY_PATIENT_HEALTH_AGENT_INTERNSHIP.md](learning/13_DIFY_PATIENT_HEALTH_AGENT_INTERNSHIP.md)：Dify 患者端医疗智能体实习项目。
- [INTERVIEW_QA.md](INTERVIEW_QA.md)：互联网医院项目与 Agent 开发面经。
- [INTERVIEW_QA_TEST_ENGINEERING.md](INTERVIEW_QA_TEST_ENGINEERING.md)：测试开发面经。
- [GENERAL_INTERVIEW_KNOWLEDGE.md](GENERAL_INTERVIEW_KNOWLEDGE.md)：通用八股与手撕题。

面试材料可以用“背景、任务、行动、结果”检查结构，但口述时不得朗读 STAR 字母，不以技术栈、内部类名或字段名开场。术语统一采用面试中的自然说法，例如“Agent 安全”和“Agent 评测”。

## 维护规则

- 需求、阶段或交付标准变化时，先更新总路线图，再同步其他文档。
- 设计文档描述当前有效设计；历史阶段仅保留在学习记录和变更记录中。
- 4C 是当前范围内的最终成熟产品阶段，验收通过后不得再用“未来展望”代替未完成能力。

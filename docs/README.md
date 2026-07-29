# 项目文档导航

本文只负责导航，不维护阶段状态。阶段编号、任务状态、实施顺序和最终验收只看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

## 新开发者阅读顺序

1. [README](../README.md)：了解项目定位、当前能力和运行入口。
2. [开发总路线图](DEVELOPMENT_ROADMAP.md)：确认当前 `NEXT` 任务和最终架构决策。
3. [技术设计](TECH_DESIGN.md)：理解分层、运行链路、状态和数据边界。
4. [业务流程](BUSINESS_WORKFLOWS.md)：理解慢病用药、预问诊和报告整理三条业务链路。
5. [Agent 架构](AGENT_ARCHITECTURE.md)：理解 Router、Planner、bounded Supervisor、三个领域 Agent 和治理层。
6. [开发者指南](DEVELOPER_GUIDE.md) 与 [测试指南](TESTING_GUIDE.md)：开始运行、改代码和 review。

## 产品与工程

| 文档 | 内容 |
| --- | --- |
| [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) | 唯一阶段计划、任务状态和验收门槛 |
| [PRD.md](PRD.md) | 产品目标、用户场景和非目标 |
| [BUSINESS_WORKFLOWS.md](BUSINESS_WORKFLOWS.md) | 三条业务链路、草稿与确认流程 |
| [TECH_DESIGN.md](TECH_DESIGN.md) | 总体技术架构与当前/目标差距 |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | 本地开发、分层、Git 和提交检查 |
| [LOCAL_SETUP_AND_DEPLOYMENT.md](LOCAL_SETUP_AND_DEPLOYMENT.md) | WSL 2、Docker、PostgreSQL/Redis、前后端启动与排错 |
| [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) | 固定 MVP 演示流程 |

## 接口与数据

| 文档 | 内容 |
| --- | --- |
| [API_SPEC.md](API_SPEC.md) | 当前 HTTP API、兼容契约与最终目标 |
| [DB_SCHEMA.md](DB_SCHEMA.md) | SQLAlchemy/Alembic 表结构、Task Checkpoint 和权威存储边界 |
| [TOOL_CONTRACTS.md](TOOL_CONTRACTS.md) | Tool Registry、Provider、权限、确认和错误契约 |
| [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md) | 运行、冻结产物和确认续跑的当前实现 |
| [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) | 当前 Next.js 页面与 4C 目标交互 |

## Agent、RAG 与治理

| 文档 | 内容 |
| --- | --- |
| [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) | 最终多 Agent 编排与角色边界 |
| [CONTEXT_MANAGEMENT.md](CONTEXT_MANAGEMENT.md) | Working State、PostgreSQL Checkpoint、Redis 缓存和上下文隔离 |
| [MODEL_GATEWAY.md](MODEL_GATEWAY.md) | deterministic/真实模型双模式与结构化校验 |
| [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md) | 模型环境变量和本地诊断 |
| [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md) | FastEmbed、pgvector、关键词降级与来源引用 |
| [SAFETY_POLICY.md](SAFETY_POLICY.md) | 三层安全治理和单确认状态机 |
| [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) | deterministic Evaluator、32 条 A/B/C Harness 和指标边界 |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | 测试分层、异常验证和 review 方法 |

## 证据与报告

以下文件记录某次真实本地执行，不能替代总路线图，也不能自动外推为线上指标：

- [AGENT_EVAL_REPORT.md](AGENT_EVAL_REPORT.md)：当前 16 条固定轨迹评测。
- [agent_eval_report.3c.md](agent_eval_report.3c.md)：3C Runtime Harness 摘要。
- [migration_validation_report.4b.md](migration_validation_report.4b.md)：4B migration 验证。
- [task8_state_checkpoint_report.4b.md](task8_state_checkpoint_report.4b.md)：4B 任务八 checkpoint、Redis 回源、两次 run 和确认版本交付记录。
- [task9_tool_provider_reliability_report.4b.md](task9_tool_provider_reliability_report.4b.md)：4B 任务九统一错误、有限重试和三类重点 Provider 交付记录。
- [task10_rag_isolation_observability_report.4b.md](task10_rag_isolation_observability_report.4b.md)：4B 任务十 RRF、版本拒绝、攻击式隔离和脱敏 Observation 交付记录。
- [agent_ablation_report.4b.md](agent_ablation_report.4b.md)：4B 任务十一 32 条 deterministic fixture 与三种编排策略消融报告。
- [task12_backend_acceptance_report.4b.md](task12_backend_acceptance_report.4b.md)：4B 任务十二 Docker PostgreSQL/Redis/API/RAG/并发确认验收报告。
- [task13_4b_closeout_report.md](task13_4b_closeout_report.md)：4B 任务十三文档、测试和 Git 收口报告。
- `provider_adapter_validation_report.4b.md`、`model_gateway_report.4b.md`、`vector_rag_report.4a.md`：对应局部能力的本地验证记录。
- `mvp_demo_report.3d.md`：3D 固定演示快照。
- `agent_eval_report.example.md`：由测试生成的示例格式，代码依赖该路径，不能当真实报告。

## 学习与面试

- [learning/README.md](learning/README.md)：从零理解并运行项目的学习路线。
- [核心代码走读](learning/17_CORE_CODE_WALKTHROUGH.md)：从 HTTP 请求一路读到 Planner、Supervisor、领域 Agent、Safety、RAG、Trace 和 Evaluator。
- [INTERVIEW_QA.md](INTERVIEW_QA.md)：项目面试题、项目化回答与记忆方法。
- [RESUME_NOTES.md](RESUME_NOTES.md)：可以如实写入简历的亮点和指标边界。
- [GENERAL_INTERVIEW_KNOWLEDGE.md](GENERAL_INTERVIEW_KNOWLEDGE.md)：通用计算机与后端面试知识。

学习文档会保留当时阶段的实现过程。遇到旧角色、旧确认字段或旧阶段名时，把它当历史教材；当前产品决策以总路线图和技术设计为准。

## 维护规则

- 不新增第二份总计划、当前状态审计或下一步清单。
- 设计文档必须明确区分“已实现”“当前兼容实现”“目标设计”。
- 运行报告记录事实，不维护阶段状态。
- 过时方案应删除或改成历史说明，不能与权威设计并列。
- 未真实运行的指标只能写成目标指标或评估维度。

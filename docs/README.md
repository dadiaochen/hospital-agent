# 开发文档导航

这个文件不是第二份项目首页：仓库根目录 [README](../README.md) 面向 GitHub 访客；本文面向开发者，只负责导航，不维护阶段状态。阶段编号、任务状态、实施顺序和最终验收只看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

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
| [mvp_closeout_report.4c.md](mvp_closeout_report.4c.md) | 4C-4 一键收口、固定 Demo、Harness 和浏览器 E2E 证据 |

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
| [EVALUATOR_AGENT.md](EVALUATOR_AGENT.md) | deterministic Evaluator、32 条 A/B/C Harness、v2 九层 grader 和指标边界 |
| [AGENT_EVALUATION_EXECUTION_PLAN.md](AGENT_EVALUATION_EXECUTION_PLAN.md) | 4D-B 最终评测数据、架构缺口、指标公式、执行顺序和简历口径 |
| [4D_B3_REAL_LLM.md](4D_B3_REAL_LLM.md) | 可选真实 LLM、token、成本、p95 和 badcase 复核流程 |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | 测试分层、异常验证和 review 方法 |

## 证据与报告

以下文件记录某次真实本地执行，不能替代总路线图，也不能自动外推为线上指标：

- [agent_ablation_report.4b.md](agent_ablation_report.4b.md)：4B 任务十一 32 条 deterministic fixture 与三种编排策略消融报告。
- [task12_backend_acceptance_report.4b.md](task12_backend_acceptance_report.4b.md)：4B 任务十二 Docker PostgreSQL/Redis/API/RAG/并发确认验收报告。
- [browser_e2e_report.4c.md](browser_e2e_report.4c.md)：4C-3 Playwright 浏览器 E2E 验收报告。
- [mvp_closeout_report.4c.md](mvp_closeout_report.4c.md)：4C-4 最终 MVP 收口报告。
- [benchmark_report.4d.md](benchmark_report.4d.md)：4D 冻结数据契约、manifest 和规则完整性报告。
- [local_benchmark_report.4d.md](local_benchmark_report.4d.md)：4D-B 本地 Supervisor、关键词 RAG、ContextManager 和 Provider 故障注入观测；不代表真实 LLM 或 Docker pgvector 指标。
- [4D_B2.6_INTEGRATION_STATUS.md](4D_B2.6_INTEGRATION_STATUS.md)：PostgreSQL shadow transaction、Provider/RAG sandbox、真实图单样例和 Docker 19/19 回归状态。
- [4D_B3_REAL_LLM.md](4D_B3_REAL_LLM.md)：8 条真实模型固定样本、人工审核、token、成本、延迟和冻结边界。
- `agent_eval_report.example.md`：由测试生成的示例格式，代码依赖该路径，不能当真实报告。

旧 3C/3D/4A 和 4B 局部阶段报告已经删除；有效结论已进入当前设计文档、路线图或以上保留的最终验收报告。

## 学习、简历与面经

统一入口见 [项目学习中心](learning/README.md)，只保留三类：

1. 项目工程与代码：从 0 到 1、核心代码逐行走读、完整 API 实战。
2. 简历：完整写法与真实证据边界。
3. 项目面经：项目完整问答、原题深挖、Dify 和测试工程追问。

按阶段拆出的短教程已删除。学习当前实现时不再需要在旧阶段号和竞争角色设计之间反复切换。

## 维护规则

- 不新增第二份总计划、当前状态审计或下一步清单。
- 设计文档必须明确区分“已实现”“当前兼容实现”“目标设计”。
- 运行报告记录事实，不维护阶段状态。
- 过时方案应删除或改成历史说明，不能与权威设计并列。
- 未真实运行的指标只能写成目标指标或评估维度。

## 当前评测文档

- [4D-B Benchmark 使用指南](4D_B_BENCHMARK_GUIDE.md)：冻结 gold 数据、deterministic runner、报告和指标边界。
- [4D-B 数据契约报告](benchmark_report.4d.md)：冻结 fixture、manifest 和规则完整性报告。
- [4D-B 本地观测报告](local_benchmark_report.4d.md)：使用本地合成数据执行实现代码；该报告本身不包含真实 LLM、Docker pgvector 或 checkpoint 恢复指标。
- [4D-B2.6 真实集成状态](4D_B2.6_INTEGRATION_STATUS.md)：记录真实单样例与 Docker 证据；300/1200 正式质量指标仍保持 `N/A`。
- [4D-B3 真实模型评测](4D_B3_REAL_LLM.md)：记录 8 条 development 固定产物的真实调用、人工复核和冻结指标；不能外推为生产或临床指标。

## GitHub 发布边界

- 仓库只保存源代码、设计文档、脱敏 seed 和固定 seed 生成的合成 benchmark fixture。
- `.env`、API Key、真实密码、真实成员数据、本机 identity/source map、人工审核队列及 `output/`、`var/` 运行产物不得提交。
- 300 个 WorldState 和 1200 条 Query 是合成评测数据，不包含真实患者信息；保留它们是为了让测试和评测契约可复现。

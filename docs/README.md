# 项目文档导航

根目录 [README](../README.md) 面向 GitHub 访客；本文面向开发者和学习者。当前文档按用途维护，不再按 2A、4B、4D 等阶段追加执行日志。

## 第一次阅读

1. [产品需求](PRD.md)：项目解决什么问题，明确哪些医疗能力不能做。
2. [技术设计](TECH_DESIGN.md)：理解系统分层和一条请求的完整数据流。
3. [Agent 架构](AGENT_ARCHITECTURE.md)：理解 Router、Planner、Supervisor 和三个领域 Agent。
4. [业务流程](BUSINESS_WORKFLOWS.md)：理解预问诊、慢病用药和报告解读。
5. [本地启动](LOCAL_SETUP_AND_DEPLOYMENT.md)：用 Docker 启动前端、后端、PostgreSQL 和 Redis。
6. [核心代码走读](learning/CORE_CODE_WALKTHROUGH.md)：沿真实代码学习一次请求如何执行。

## 当前设计文档

| 主题 | 文档 | 主要内容 |
| --- | --- | --- |
| 产品 | [PRD](PRD.md) | 用户、场景、目标和非目标 |
| 总体架构 | [技术设计](TECH_DESIGN.md) | 分层、状态、数据流和技术选型 |
| 多 Agent | [Agent 架构](AGENT_ARCHITECTURE.md) | 路由、计划、调度、领域 Agent 和治理节点 |
| 业务 | [业务流程](BUSINESS_WORKFLOWS.md) | 三条业务链路、受保护动作确认与报告直接结构化读取 |
| 上下文 | [上下文管理](CONTEXT_MANAGEMENT.md) | 最小角色视图、压缩、重置和分层记忆 |
| 工具 | [工具契约](TOOL_CONTRACTS.md) | Tool Registry、权限、超时、重试和来源 |
| 模型 | [Model Gateway](MODEL_GATEWAY.md) | deterministic/真实模型双模式和输出校验 |
| RAG | [RAG 检索](RAG_RETRIEVAL.md) | FastEmbed、pgvector、关键词、RRF 和评测指标 |
| 安全 | [安全策略](SAFETY_POLICY.md) | 三层 Agent 安全和人工确认 |
| 评测 | [Agent 评测](EVALUATOR_AGENT.md) | 冻结产物、确定性评分和指标边界 |
| 数据库 | [数据库设计](DB_SCHEMA.md) | 表、迁移、Checkpoint 和成员隔离 |
| API | [接口文档](API_SPEC.md) | 当前 HTTP 接口、请求响应和错误 |
| 报告解析 | [5A 业务闭环收口](implementation/5A_CLOSEOUT.md) | 文本/Markdown 表格、PDF 文本层、本地图片 OCR 与可读结构 |
| 前端 | [前端架构](FRONTEND_ARCHITECTURE.md) | 页面、状态和后端接口映射 |

## 开发与运行

| 文档 | 用途 |
| --- | --- |
| [本地启动与部署](LOCAL_SETUP_AND_DEPLOYMENT.md) | 第一次启动、日常启动、关闭、日志和排错 |
| [开发者指南](DEVELOPER_GUIDE.md) | 分层规则、开发流程、Git 和代码审查 |
| [测试指南](TESTING_GUIDE.md) | 单元、集成、浏览器、评测和真实模型测试 |
| [演示手册](DEMO_RUNBOOK.md) | 固定演示流程和讲解重点 |
| [开发路线图](DEVELOPMENT_ROADMAP.md) | 当前完成度、剩余工作和完成标准 |

## 学习、简历和面经

统一入口是 [项目学习中心](learning/README.md)：

- [从 0 到 1 的工程设计](learning/PROJECT_ENGINEERING_GUIDE.md)：需求拆分、技术选型和工程实现思路。
- [核心代码走读](learning/CORE_CODE_WALKTHROUGH.md)：按真实调用链阅读关键代码，保留面向初学者的语法和变量解释。
- [完整 API 教程](learning/API_DEVELOPMENT_TUTORIAL.md)：从 Schema、Service 到 FastAPI 和 Postman。
- [简历与面试口径](RESUME_NOTES.md)：业务背景、多 Agent Pipeline、简历一句话和最新实测指标。
- [简历写作指南](learning/RESUME_GUIDE.md)：真实性边界和表达原则。
- [大模型应用扩展题库](INTERVIEW_QA.md)：需要深入准备时再阅读；当前口述以简历与面试口径为准。
- [测试开发面经](INTERVIEW_QA_TEST_ENGINEERING.md)：测试设计、pytest、CI 和质量工程。
- [Dify 项目复盘](learning/DIFY_PROJECT_GUIDE.md)：早期可视化工作流与当前代码实现的关系。

## 历史与回退

[执行历史归档](EXECUTION_HISTORY.md) 统一保存阶段里程碑、历史验收快照和指标演进。旧阶段报告和执行方案已从当前文档区删除；完整旧正文仍可通过 Git 历史读取。

## 维护规则

- 当前文档解释“系统现在怎样工作”，不追加阶段流水账。
- 阶段号、某次测试时间和旧方案只写入执行历史归档。
- README 只展示项目，不承担设计文档职责。
- 简历数字必须注明数据规模、环境和指标含义。
- synthetic/test-only 结果不能表述为临床准确率、线上成功率或生产 SLA。
- `.env`、API Key、真实患者数据、人工审核队列和本机运行产物不得提交到 GitHub。

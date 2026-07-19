# 家庭健康 Agent 项目说明与 AI Coding Context

本文件用于给参与项目的开发者或 AI Coding Agent 建立共同上下文。它描述产品目标、不可突破的边界和实施方式；阶段编号、完成状态和后续顺序以 [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) 为唯一权威来源。

## 1. 项目目标

构建一个可本地演示的家庭健康事务管理 Agent MVP，围绕：

- 慢病续方材料整理。
- 中医复诊材料整理。
- 家庭药箱和药店库存查询。
- 用药提醒草稿。
- 高风险用药请求的安全拦截。

系统的价值在于把信息、工具证据、人工确认和审计 trace 组织成可靠流程，而不是让 AI 代替医生下医疗结论。

## 2. 不可突破的医疗边界

- 不诊断疾病，不自动开方，不修改医生处方。
- 不生成自行加量、减量、停药或换药建议。
- 复诊、购药、提醒等关键动作必须经过人工确认。
- 目前确认后也只创建本地 draft，不提交医院、药店、支付或消息推送系统。
- 没有 DB、API 或 RAG 来源时，不生成病史、库存、处方或安全规则等事实。

## 3. 代码结构

```text
api       HTTP 协议、依赖注入和 response
schemas   API Pydantic DTO
models    SQLAlchemy ORM
services  业务查询、草稿和事务
tools     Tool Registry 与受控业务工具
agent     Context、Trace、Harness、后续工作流
rag       检索和来源引用
safety    风险拦截与人工确认判断
core      配置、数据库、日志和异常
```

新功能必须进入正确的层。API 不直接写 SQL，Agent 不绕过 Tool Registry，工具不把未校验的 `dict` 当作可信输入。

## 4. Agent 设计原则

```text
Raw Conversation -> ContextEnvelope -> Role View -> Tool/RAG Evidence
-> Final Answer -> RunSummary/Reset -> Evaluator Review
```

- `user_id` 表示账户，`member_id` 表示本次服务对象，所有来源引用都要与当前成员一致。
- 角色只能得到最小 Role-specific Context View，不广播完整聊天记录。
- Context reset 后保留 summary、trace、答案、工具/RAG 指针和 evaluation 引用，清理 scratchpad、原始对话和未确认推断。
- SafetyAgent 负责事前拦截；EvaluatorAgent 只读事后评估，二者不得混用。

## 5. 工具与审计原则

工具必须声明 input/output schema、permission scope、允许角色、timeout、retry、是否只读和是否需要确认。调用时先检查工具许可、角色、确认和输入 schema，执行后再验证输出 schema，并生成可追踪的 ToolResult。

关键工具：

- 档案、处方、药箱、库存、安全知识：只读 evidence。
- `create_confirmation_draft`：确认后只写本地草稿，记录 run、幂等键和 `not_submitted` 外部状态。

## 6. 编码与验收要求

1. 只实现路线图当前阶段或用户明确指定的目标。
2. 新接口必须有 API DTO；新工具必须有完整 ToolSpec；新状态流转必须有确认与失败路径。
3. 新功能至少有最小正例和失败例测试，尤其检查成员隔离、来源、确认与安全。
4. 代码完成后同步 README、技术/接口/数据库/Agent 文档和测试指南。
5. 只有真实运行过的评估报告才能支持指标结论；mock fixture 指标只能说明规则已被计算。

已完成的 `2E-1` API 层只暴露已有 service 的读取能力，使用固定 demo user 做成员作用域隔离，并返回统一错误响应。不得在读取 API 中加入草稿写入、确认状态机、LangGraph、LLM 或外部医疗集成。

本地完整联调使用 Docker PostgreSQL/Redis，pytest 使用内存 SQLite。知识搜索 DTO、service、route 和 `test_knowledge_api.py` 已完成，并通过 PostgreSQL/Postman 与自动化测试验收。PostgreSQL 实跑要求 Alembic 内部 `version_num` 容纳现有长 revision ID，该兼容修复位于对应长 revision 的迁移中，不改变 ORM 业务字段。

## 7. 阅读顺序

- 协作者：从 [docs/README.md](docs/README.md) 和 [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) 开始。
- Agent 开发者：继续阅读 [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md)、[docs/CONTEXT_MANAGEMENT.md](docs/CONTEXT_MANAGEMENT.md) 和 [docs/EVALUATOR_AGENT.md](docs/EVALUATOR_AGENT.md)。
- 从零学习者：阅读 [docs/learning/README.md](docs/learning/README.md)。

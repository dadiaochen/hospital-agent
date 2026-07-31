# 13 3C Runtime E2E、环境与 Dify 面试讲解

> 阅读约定：本章只保留 Dify 界面真实节点名、`RAG`、`API`、`token` 等必要技术名，其余使用中文。Dify 项目的完整面试版本以 [Dify 患者端医疗智能体实习项目](13_DIFY_PATIENT_HEALTH_AGENT_INTERNSHIP.md) 为准，本章重点解释从原型到自研系统的变化，避免维护两套互相冲突的答案。

## 1. 先把项目经历说准确

这个项目可以同时有“真实业务背景”和“没有生产上线”两个事实：

- 真实的是问题、角色、风险边界和业务流程，例如慢病续方材料、家庭成员隔离、人工确认和医疗安全拦截。
- Dify 版本是用于验证流程的原型或 POC；当前自研版本是简历级本地 MVP。
- 当前没有真实患者流量、医院/药店接口、生产认证、监控告警或高可用部署。

面试时推荐说：

> 项目来源于真实互联网医院慢病管理流程。早期我用 Dify 工作流快速验证意图路由、RAG、业务 API、人工确认和安全分支；后来为了获得明确的数据契约、成员上下文隔离、可测试的运行记录、确定性评测和事务幂等，我用 FastAPI、SQLAlchemy 和 LangGraph 重构为可本地演示的 MVP。目前完成的是开发与集成验证，不是生产医疗系统。

不要说“已经上线”“服务真实患者”或“生产安全率 100%”。

## 2. Dify 到底是什么

Dify 不是一个模型。它是一个把模型、提示词、RAG、工具和工作流节点组织起来的应用开发平台。模型可以使用不同服务；Dify 负责把输入沿工作流传递给不同节点，并提供调试和运行记录。

官方资料可继续阅读：

- [Dify 创建应用与工作流](https://docs.dify.ai/en/guides/application-orchestrate/creating-an-application)
- [Dify Knowledge Retrieval](https://docs.dify.ai/guides/knowledge-base/retrieval)
- [Dify Tool Plugin](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin)

“用了 Dify”不能只回答“LLM + RAG”。面试官真正想知道的是：输入如何路由、事实从哪里来、风险在哪里被拦截、动作怎样确认、失败后怎么办。

## 3. 原 Dify 流程可以怎样设计

因为仓库没有保存当时 Dify 导出的 DSL，下面是根据当前真实业务边界整理出的可信节点设计。面试时应说“当时的核心流程是这样”，不要编造具体模型版本、节点数量或线上指标。

```text
开始/用户输入
  -> 参数提取/问题分类
  -> 条件判断：是否为高风险医疗请求
     -> 是：检索安全规则 -> 安全答复模板 -> 结束
     -> 否：进入业务分支
          -> HTTP 工具：档案/处方/药箱/库存
          -> RAG：流程和确认规则
          -> LLM：只根据证据生成结构化草稿
          -> 代码/模板：统一字段和来源编号
          -> 条件判断：关键动作是否需要确认
             -> 是：返回待确认草稿
             -> 否：返回有来源的查询结果
  -> 回答/结束
```

### 3.1 Start 节点

输入变量至少包括：

- `user_input`：用户自然语言任务。
- `member_id`：父亲、母亲或本人对应的稳定 ID，而不是仅靠“我爸”文本猜测。
- `medication_name`、`city`：可选业务槽位。

这里解决“任务输入是什么”，不负责查数据库或生成建议。

### 3.2 Parameter Extractor / Classifier

输出结构化字段：

```json
{
  "intent": "refill | consultation | reminder | pharmacy | safety_check",
  "member_id": "...",
  "missing_slots": [],
  "action_type": "query | draft | safety_review"
}
```

Classifier 决定走哪条业务分支；Extractor 把自然语言中的成员、药名、城市和缺失项提取出来。二者不是数据库事实来源，模型猜出的字段必须让用户确认或由 API 验证。

### 3.3 第一层 IF/ELSE 安全分支

加量、减量、停药、换药、胸痛、呼吸困难等请求不能先进入续方或库存节点。应先进入安全分支，检索已审核的医疗边界规则，再输出“停止业务执行、联系医生或紧急人工处理”。

这对应当前代码中的 Planner 高风险规则、SafetyAgent 和安全条件边。

### 3.4 HTTP Request / Tool 节点

Dify 本身不会知道家庭成员档案、处方或库存。它需要通过 HTTP Request 或 Tool 调用后端：

| 节点 | 输入 | 输出 |
| --- | --- | --- |
| Profile API | `member_id` | 慢病标签、过敏和安全备注。 |
| Prescription API | `member_id` | 已有医生处方和有效期。 |
| Medicine Box API | `member_id` | 药品、剩余数量和已有用法。 |
| Inventory API | 药名、城市 | 药店候选、库存和配送方式。 |

每个结果都需要 `source_id`。没有命中时返回空结果或结构化错误，不能让后续 LLM 自己补一个库存。

### 3.5 Knowledge Retrieval，也就是 RAG

RAG 不是“让模型记住知识库”，而是：

1. 用当前 query 检索知识分块。
2. 返回相关正文和 document/chunk/source ID。
3. 把命中内容作为本次 LLM 节点的上下文。
4. 最终答案保留来源指针。

本项目适合放入知识库的是续方 SOP、人工确认规则和医疗安全边界；用户处方、药箱库存属于业务数据库事实，不应该混进通用知识库。

### 3.6 LLM 节点

LLM 只做受约束的整理：

- 根据已返回的 Tool Evidence 和 RAG 内容生成草稿。
- 输出固定 JSON，不输出随意长文本。
- 不诊断、不修改剂量、不承诺库存、不宣称已经提交。
- 没有来源时明确说无法确认。

Prompt 的核心不是“你是医生”，而是“你是流程整理助手，只能使用给定 evidence，并按 schema 输出”。

### 3.7 Code / Template 节点

这一节点负责确定性工作，例如字段重命名、去重 source ID、组装 UI 所需 JSON 和追加固定免责声明。能用代码确定的事情不要让 LLM 猜。

### 3.8 第二层 IF/ELSE 人工确认

复诊申请、购药候选和提醒创建只能返回 `pending_confirmation`。用户再次确认后，也只创建本地草稿；Dify 原型不应伪装成已经调用医院、支付或推送系统。

### 3.9 Answer / End

最终输出应分为：

- 已验证事实及来源。
- 安全提示。
- 待确认动作。
- 当前未执行的外部动作。

## 4. 为什么后来要自研

低代码平台适合快速验证流程，但当前项目还需要更细的工程控制：

| Dify 原型概念 | 当前自研实现 |
| --- | --- |
| Workflow variables | Pydantic `ContextEnvelope`。 |
| Classifier / Extractor | `DeterministicWorkflowPlanner`。 |
| IF/ELSE | LangGraph 条件边。 |
| HTTP/Tool node | Tool Registry + DB-backed tools。 |
| Knowledge Retrieval | Hybrid Retriever + `RAGSourceRef`。 |
| LLM node | Model Gateway + structured Pydantic output。 |
| Safety branch | SafetyAgent，发生在动作前。 |
| Confirmation branch | `/continue` + confirmation-gated local draft。 |
| Run logs | `agent_runs`、`agent_tool_calls`、冻结 artifacts。 |
| Dify 调试 | ExpectedCase + Runtime Harness + DeterministicEvaluator。 |

自研不是为了证明 Dify 不好，而是需求从“验证流程”升级到了“强契约、可回归、可审计、可解释”。

## 5. 现在到底是什么环境

不要把所有非生产环境都叫“测试环境”。本项目有四个不同概念：

| 环境 | 当前用途 | 数据库 |
| --- | --- | --- |
| 本地开发环境 | 写代码、Swagger、Postman、调试前后端。 | Docker PostgreSQL。 |
| 自动化测试环境 | pytest/Vitest，每条测试隔离并快速回归。 | pytest 内存 SQLite；前端使用 jsdom/mocks。 |
| 本地集成/演示环境 | Docker 中运行 PostgreSQL、Redis、FastAPI、Next.js，验证完整链路。 | Docker PostgreSQL seed 数据。 |
| 生产环境 | 真实用户、认证、秘密管理、监控、高可用和外部医院接口。 | 尚未建设。 |

因此最准确的回答是：

> 当前没有生产环境。日常开发和 Postman 使用本地 Docker PostgreSQL 集成环境；pytest 使用 SQLite 隔离测试环境；前端组件测试使用 jsdom。3C 的实测报告来自本地 PostgreSQL + deterministic provider，不是线上或真实模型指标。

## 6. 3C 的 Runtime E2E 在做什么

读取顺序：

1. `runtime_harness_cases.json`：先看测试想证明什么。
2. `runtime_harness.py`：看 Runner 如何发现 member、调用 API、续跑和聚合。
3. `runtime_trace_adapter.py`：看 API artifacts 怎样变成只读评估输入。
4. `evaluator.py`：看每个分数如何计算。
5. `test_runtime_e2e_harness.py`：看成功、无来源、越权和脱敏怎样断言。

3C 不是再次实现 Agent，而是验证已实现的 Agent 是否能从 HTTP 入口完整跑通，并把真实冻结 Trace 送到独立评估规则中。

## 7. 面试回答模板

### 7.1 90 秒版本

> 早期我们用 Dify Workflow 做业务 POC。入口先提取 intent、member 和药品等槽位，然后用条件分支把加量、停药和严重症状提前路由到安全节点。普通任务通过 HTTP Tool 查询成员档案、已有处方、药箱和库存，SOP 与安全规则通过 Knowledge Retrieval 做 RAG。LLM 节点只根据这些证据生成结构化草稿，Code 节点整理 source ID，最后再通过人工确认分支决定返回查询结果还是待确认草稿，不直接提交医院或药店。后来我把它重构为 FastAPI + SQLAlchemy + LangGraph + 自研 Harness，重点解决强类型契约、member 隔离、Trace 持久化、幂等确认和 deterministic E2E 评估。当前是本地集成演示环境，还没有生产上线。

### 7.2 常见追问

**为什么不用一个大 Prompt？**

因为分类、数据查询、安全判断、确认和输出属于不同信任边界。一个 Prompt 难以独立测试成员隔离、工具失败和确认绕过。

**RAG 和数据库查询有什么区别？**

RAG 检索 SOP 和安全知识；数据库工具查询用户档案、处方和库存。前者是规则来源，后者是业务事实来源。

**Dify 有日志，为什么还要 Trace？**

Dify 日志适合调试原型；当前系统要求可版本化 Pydantic 契约、run/tool-call 数据库审计、source pointer、成员隔离和可重复的独立评估。

**为什么没有生产上线也有价值？**

因为项目完整实现了需求拆解、分层、数据库、Agent 编排、安全门、前后端和测试交付。但必须把验证范围说清楚，不能把本地 seed 结果外推为生产能力。

## 8. 你的练习

不用看文档，画出 Dify 原型和当前自研实现两张图。然后回答：

1. 哪个节点第一次确定 `member_id`？
2. 哪些事实来自数据库，哪些规则来自 RAG？
3. SafetyAgent 为什么必须在动作前，而 Evaluator 为什么只能在回答后？
4. 无来源库存查询为什么是“正确失败”而不是系统崩溃？
5. 本地 PostgreSQL 报告为什么不能叫生产指标？

能独立讲清这五个问题，才算真正理解了这个项目，而不是只记住 Dify、RAG 和 LangGraph 三个名词。

# 05. 简历与面试表达

## 1. 先讲问题，不要先堆技术栈

比起“我用了 FastAPI、LangGraph、PostgreSQL”，更有说服力的开场是：

> 我把项目定位成家庭健康事务 Agent，而不是 AI 医生。核心挑战是如何让系统在多成员医疗数据里不串数据、不编造来源、不绕过确认，并且能把一次运行回放出来。

接着再说你的设计如何回答这些挑战。技术栈是证据，问题和取舍才是故事。

## 2. 一条完整项目故事线

```text
需求：续方、复诊、提醒与安全拦截
  -> 风险：医疗越界、成员串扰、无来源事实、关键动作越权
  -> 设计：分层后端 + Pydantic contracts + Tool Registry
  -> 运行：ContextManager 最小视图 + confirmation draft + trace
  -> 验证：fixtures + deterministic evaluator + failure-path tests
  -> 边界：本地 demo，不做诊断、开方或外部提交
```

这条线能把数据库、后端、Agent、测试和安全串起来，避免回答变成一堆互不相关的功能点。

## 3. 可以写进简历的技术亮点

| 亮点 | 可验证证据 | 可用表达 |
| --- | --- | --- |
| 分层后端 | `api/schemas/models/services/tools/agent` 目录与测试 | 设计分层 FastAPI 后端，分离 HTTP、业务、持久化与 Agent 工具职责。 |
| 强类型契约 | Context、Tool、Trace、Evaluation Pydantic models | 以 Pydantic 约束 Agent 输入输出和运行产物，拒绝未声明字段。 |
| 数据隔离 | `member_id` validator、工具 scope tests | 建立 user/member 双层作用域校验，防止家庭成员上下文串扰。 |
| 安全确认 | ToolRegistry confirmation gate、draft service | 为关键动作实现确认门禁与本地草稿审计，不触发外部医疗动作。 |
| Agent 可观测性 | RunTrace、ToolCallTrace、AgentRun/ToolCall 模型 | 设计可回放的 run/tool trace，记录角色、耗时、schema 和 fallback。 |
| 可评估性 | ExpectedCase、DeterministicEvaluator、fixtures | 构建固定用例的 deterministic Harness，覆盖来源、工具、安全和确认规则。 |

## 4. 90 秒项目介绍模板

```text
我做的是一个面向家庭慢病续方、复诊材料和用药提醒的本地演示 Agent。它不是 AI 医生，重点是把 Agent 放进可控业务流程里。

后端按 API、service、ORM、tool 和 agent 分层。对于多成员数据，我把 member_id 放进 Context、工具执行上下文和 evidence 引用里，并在 Pydantic validator 和工具层都校验，避免串数据。

关键动作不会直接提交医院或药店；Tool Registry 会先校验角色、允许工具、输入输出 schema 和人工确认，确认后只写本地 draft，并记录 run 和幂等审计信息。

为了避免只靠主观判断 Agent 好不好，我又做了固定 ExpectedCase、冻结 RunTrace 和 deterministic evaluator，能够回放缺工具、无来源、缺安全标记、缺确认和串成员等失败场景。
```

把这段改成自己的说话方式，但不要删掉“边界”和“证据”。

## 5. 常见追问与回答方向

**为什么不用 LLM 直接判断安全？**

因为安全规则和确认门禁要稳定、可测试、可解释。LLM 后续可以参与受约束的解析或表达，但不能成为绕过规则的唯一控制面。

**为什么需要 Context Reset？**

长对话会累积无关信息和未经确认的猜测。reset 后保留可审计 summary 和来源指针，清掉 scratchpad；新任务或成员切换就不会带入旧成员的事实。

**Evaluator 和 Safety 有何区别？**

Safety 在输出/动作前拦截，Evaluator 在输出后只读检查。若让 Evaluator 负责安全，风险动作已经发生，设计上太晚。

**mock Harness 有什么价值？**

它不证明真实模型表现，但能让流程契约、测试用例和失败分类先稳定下来。接真实 LLM 后还能复用同一 RunTrace 与评估口径比较差异。

**你下一个技术挑战是什么？**

按路线图推进读取 API，再做草稿确认 API、Hybrid RAG、Model Gateway 和 LangGraph runtime，并把真实 run 转换为已有 trace 契约。回答时要明确哪些已做、哪些是下一步。

## 6. 绝不能说的话

- “系统会帮用户决定怎么吃药。”
- “确认后已经帮用户下单/提交医院。”
- “Harness 指标证明临床安全。”
- “已经有真实 LLM 多 Agent 流程。”

诚实地说明当前是本地演示级、deterministic 基线，反而能体现工程判断力。面试官更愿意相信你知道系统的边界在哪里。

## 7. 练习

录一段 90 秒介绍。回听时检查：是否先讲问题？是否讲到一个具体字段或契约？是否讲到一个失败测试？是否清楚说明了没有实现的部分？四个问题都能回答“是”，这段项目介绍就已经很扎实。

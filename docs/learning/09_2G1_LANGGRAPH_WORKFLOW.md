# 09 从零读懂 2G-1 LangGraph 工作流

这一章把你当作第一次接触工作流框架的开发者。目标不是背 `StateGraph` API，而是能回答：为什么需要图、请求怎样经过每一层、状态字段从哪里来、安全和确认为什么不会被跳过、测试怎样证明这些结论。

## 1. 先理解要解决的问题

如果只写一个普通函数，当然也能顺序调用：识别意图、查数据库、生成回答。但 Agent 业务有三个额外难点：

1. 不同意图需要不同步骤。提醒不需要查药店，高风险问题不能先创建草稿。
2. 每一步需要独立边界。角色不能看到全部聊天或调用任意工具。
3. 运行必须可解释。出了问题要知道经过哪些节点、调用了什么工具、用了哪些来源。

LangGraph 在这里不是“让 AI 更聪明”的库，而是把步骤和条件边显式化。它更像一个受约束的流程引擎。

## 2. 普通 Python、FastAPI 和 LangGraph 的关系

`langgraph_workflow.py` 仍然是 Python：类、函数、字典、条件判断都遵守 Python 语法。`StateGraph` 是第三方库提供的类，类似 FastAPI 提供 `APIRouter`，SQLAlchemy 提供 `Session`。

- FastAPI 解决 HTTP 请求如何进入 Python、如何返回 HTTP 响应。
- SQLAlchemy 解决 Python 对象如何查询和修改关系数据库。
- LangGraph 解决多个有状态步骤如何按边和条件执行。

2G-1 只用第三项，没有新增 HTTP 路由，也没有数据库会话。线性后继 2G-2 已由 FastAPI endpoint 和 AgentRuntimeService 调用这个 workflow，并给它注入数据库工具；完整学习见 [10_2G2_AGENT_RUNTIME_API.md](10_2G2_AGENT_RUNTIME_API.md)。

## 3. 第一次阅读的文件顺序

不要从 800 多行实现文件第一行硬啃到最后。按下面顺序：

1. `workflow_schemas.py`：先知道输入、计划、答案和最终结果长什么样。
2. `langgraph_workflow.py` 的 `_build_graph()`：只看节点和边，画出流程。
3. `workflow_planning.py`：看用户输入怎样变成计划、请求字段怎样投影成工具输入。
4. `_context_node()`、`_role_node()`、`_call_tool()`：看上下文和工具链。
5. `_safety_node()`、`_route_after_safety()`、`_confirmation_node()`：看安全与确认。
6. `_final_answer_node()` 到 `_evaluator_node()`：看答案怎样冻结、reset 和评估。
7. `test_langgraph_workflow.py`：用测试反推每条设计承诺。

每读一个函数固定问：输入在哪里、返回更新了哪些 state 字段、有没有副作用、失败怎样表达、下一个节点由哪条边决定。

## 4. 输入契约 WorkflowRunRequest

```python
class WorkflowRunRequest(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    user_input: NonEmptyStr
    medication_name: NonEmptyStr | None = None
    city: NonEmptyStr | None = None
    human_confirmation_granted: bool = False
```

字段逐个理解：

- `run_id`：这一次执行的唯一编号，工具和 trace 用它串起来。
- `task_id`：业务任务编号；同一任务以后可能有多次 run。
- `user_id`：账户是谁。
- `member_id`：这次处理爸爸、妈妈还是自己，是数据隔离边界。
- `user_input`：本轮自然语言输入，不会原样广播给所有角色。
- `medication_name` / `city`：当前 demo 用于构造工具参数。
- `human_confirmation_granted`：默认 false；模型、Planner 或节点不能自己把它改成 true。

为什么不用普通 `dict`？因为 Pydantic 会拒绝空 ID、未知字段和错误类型，让错误在进入图前暴露。

## 5. Planner 到底做什么

Planner 输入 `WorkflowRunRequest`，输出 `WorkflowPlan`：

```python
WorkflowPlan(
    intent="reminder",
    input_category="reminder",
    action_type="draft",
    required_tools=("query_medicine_box", "create_confirmation_draft"),
    safety_flags=("reminder_confirmation_required",),
    human_confirmation_required=True,
    draft_action_type="reminder_create",
)
```

它没有查询药箱，也没有创建提醒。它只回答“这是什么任务、需要哪些能力、是否需要确认”。这就是计划层和执行层分离。

当前 Planner 用关键词，因此可预测、方便测试。以后替换为真实 LLM 时，仍必须返回同一个 Pydantic schema；模型自由文本不能直接控制图。

## 6. WorkflowState 是什么

`WorkflowState` 是 `TypedDict`。你可以把它理解为“这一次 run 在各节点之间传递的有名字的文件夹”。节点不会返回完整新对象，只返回它负责更新的字段：

```python
def _planner_node(self, state):
    return {
        "plan": self.planner.plan(state["request"]),
        "visited_nodes": _visit(state, "planner"),
    }
```

这里的 `return` 不是 HTTP response，也不是最终用户答案。LangGraph 会把返回字段合并进当前 state，再沿着图的下一条边执行。

`visited_nodes` 是可观测字段。它让测试可以断言某个提醒任务走了 ReminderAgent，没有误走 RefillAgent，也可以证明没有重复节点和循环。

## 7. 怎么读 `_build_graph()`

先看注册节点：

```python
graph.add_node("planner", self._planner_node)
graph.add_node("context_manager", self._context_node)
graph.add_node("safety_agent", self._safety_node)
graph.add_node("final_answer", self._final_answer_node)
```

字符串是图中的节点名字，第二个参数是执行该节点的 Python 函数。

再看固定边：

```python
graph.add_edge(START, "planner")
graph.add_edge("planner", "context_manager")
graph.add_edge("final_answer", "run_trace")
graph.add_edge("evaluator", END)
```

最后看条件边：

```python
graph.add_conditional_edges(
    "safety_agent",
    self._route_after_safety,
    {
        "confirmation_draft": "confirmation_draft",
        "final_answer": "final_answer",
    },
)
```

`_route_after_safety()` 返回一个 key。LangGraph 用映射找到下一个节点。阻断时返回 `final_answer`，普通待确认任务返回 `confirmation_draft`。

## 8. 为什么角色路由不能只看工具

RefillAgent 和 ReminderAgent 都能读取药箱。如果代码只判断“计划需要 query_medicine_box”，提醒就可能先进入 RefillAgent，续方也可能误入 ReminderAgent。

项目用 `_business_roles(plan)` 先判断 intent：

- refill：Profile、Refill，可选 Pharmacy。
- pharmacy：Refill、Pharmacy。
- reminder：Reminder。
- safety_check：直接 Safety。

然后每个角色只执行 `ROLE_TOOLS[role]` 和 `required_tools` 的交集。这体现两个不同问题：角色边界回答“谁应该处理”，工具计划回答“这个角色具体需要做什么”。

## 9. ContextManager 在节点中怎么用

`_context_node()` 先构造 ContextEnvelope。它不把 raw conversation 放进去，而是生成摘要、task state、allowed tools、安全标记和来源引用列表。

角色节点调用两次 `build_role_view()`：

1. 工具执行前：得到 permission view，Tool Registry 用它校验 allowed tools。
2. 工具执行后：ContextEnvelope 已新增 evidence，再投影最终视图，保留该角色可见的 source pointer。

为什么不是把 ToolResult 全部塞给所有角色？处方、库存、安全知识的用途和权限不同；最小视图可以降低跨成员串扰和无关上下文污染。

## 10. Tool Registry 为什么还需要

LangGraph 决定“什么时候调用”，Tool Registry 决定“允不允许、参数和结果是否合法”。执行链是：

```text
role node
  -> WorkflowToolInputBuilder
  -> ToolExecutionContext
  -> ToolRegistry.call
  -> input schema / permission / confirmation
  -> handler
  -> output schema
  -> ToolResult
```

即使图路由写错，Registry 仍会拒绝角色无权调用、未列入 allowed tools 或缺少确认的工具。这是分层防护，不是重复代码。

`WorkflowToolInputBuilder` 读取已注册 Pydantic schema 的字段，只给工具传它声明过的值。真实 DB tool 比 mock tool 多 `user_id`、幂等键和 payload 时，不需要在图里写两套硬编码调用。

## 11. 来源指针怎样流动

成功 ToolResult 中的 `source_id` 会变成 `ToolEvidenceRef`：

```text
ToolResult.output.source_id
  -> ContextEnvelope.tool_evidence_refs
  -> RoleSpecificContextView.visible_tool_evidence_refs
  -> ToolCallTrace.source_id
  -> RunSummary.tool_evidence_refs
  -> reset_state.retained_tool_evidence_refs
```

RAG 来源同样保留 document/chunk/member 指针。Compaction 或 reset 可以删除大段临时内容，但不能删掉这些指针，否则 Evaluator 无法判断事实是否有依据。

## 12. SafetyAgent 和输出安全检查不是一回事

SafetyAgent 看的是整个任务：用户是否要求加量、停药、换药，是否有严重症状，是否应该跳过业务动作。

Model Gateway 的 safety checker 看的是某次 provider 输出：文本是否出现危险指令或绕过确认表达。

前者在业务动作前控制路由，后者在文本进入系统前过滤输出。只有 Gateway 检查而没有 SafetyAgent，危险任务可能已经调用写工具；只有 SafetyAgent 而没有 Gateway，模型仍可能生成越权文本。

## 13. 人工确认为什么不可绕过

确认有三层：

1. WorkflowPlan 声明 `human_confirmation_required`。
2. 图只有非阻断任务才进入 confirmation 节点。
3. Tool Registry 检查请求中显式的 `human_confirmation_granted`。

当它是 false 时，`_confirmation_node()` 不调用工具，FinalAnswer 标记 `awaiting_confirmation`。当它是 true 时，工具结果仍是 `status="draft"`，回答明确没有提交医院、购买、支付或启用提醒。

## 14. 为什么 FinalAnswer 后还要 RunTrace、Reset、Evaluator

用户看到答案，不代表工程流程结束：

- RunTrace 冻结“实际发生了什么”。
- Reset 清理候选推断、原始对话、scratchpad 和临时输出。
- Evaluator 把实际 trace 与 ExpectedCase 对比，输出失败原因。

顺序很重要。Evaluator 不能参与答案生成，否则它既当裁判又当选手；也不能为了评估而保留全部临时上下文。

FinalAnswerTrace 使用 Pydantic `frozen=True`。测试尝试修改 `content` 会直接校验失败，这比“文档说不允许修改”更可靠。

## 15. 四个场景怎么走

### 父亲续方材料

```text
Planner(refill)
-> ProfileAgent(profile evidence)
-> RefillAgent(prescription + medicine box)
-> PharmacyAgent(optional inventory)
-> SafetyAgent
-> confirmation draft
-> answer/trace/reset/eval
```

### 母亲复诊材料

与续方类似，但草稿类型是 `consultation_request`，不能悄悄降级为 `refill_request`。

### 母亲提醒

```text
Planner(reminder)
-> ReminderAgent(medicine box)
-> SafetyAgent
-> reminder draft
-> answer/trace/reset/eval
```

它不会因为也用药箱工具就进入 RefillAgent。

### 加量/停药/换药

```text
Planner(safety_check)
-> SafetyAgent(search safety knowledge, blocked=true)
-> final answer
-> trace/reset/eval
```

它不会进入 confirmation draft，更不会创建业务草稿。

## 16. 你应该怎样运行和观察

```powershell
Set-Location E:\project_code\hospital\var\worktrees\2e-2
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_langgraph_workflow.py -q -p no:cacheprovider --basetemp=.tmp\pytest-workflow
```

阅读测试时重点看：`visited_nodes`、`role_views`、`tool_results`、`run_trace`、`run_summary`、`reset_state` 和 `evaluation_result`。每个字段都对应一项架构承诺。

## 17. 给你的练习

1. 手画提醒场景的图，在每条边旁写出条件。
2. 找出 `member_id` 在 request、context、tool context、evidence 和 trace 中出现的位置。
3. 把测试中的 `human_confirmation_granted` 改成 false，预测哪些断言会变化，再运行。
4. 新增一个 Planner 单元测试，验证“呼吸困难”会产生 `urgent_human_escalation`。
5. 写一段 review 结论：为什么图没有循环，为什么 Evaluator 无法修改答案。

## 18. 面试表达

你可以说：

> 我用有界 LangGraph DAG 把 Planner、角色最小上下文、Tool Registry、SafetyAgent、人工确认草稿、结构化模型输出和 post-run Evaluator 串成正式流程。角色路由由 intent 决定，工具调用保留 member/source trace，高风险在写动作前阻断，Evaluator 只读冻结产物。

不要说已经接入真实医院、自动开方、达到 100% safety recall 或真实 LLM 零幻觉。当前证明的是架构约束和 deterministic 测试通过，不是临床或生产指标。

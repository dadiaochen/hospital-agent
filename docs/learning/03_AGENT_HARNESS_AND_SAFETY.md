# 03. Agent Harness、安全与可评估性

## 1. 为什么不能只写一个聊天函数

最简单的 Agent 往往是：把对话历史塞进 prompt，调用模型，再把文本返回。它在医疗事务中有四个明显问题：

- 不知道回答来自哪里，容易编造库存、处方或病史。
- 多个家庭成员的内容很容易混在同一段 history 中。
- 模型可以绕过“先确认再动作”的产品规则。
- 出错后没有冻结产物，无法复盘“为什么这次答案不好”。

Harness 的作用就是给 Agent 外面加一层骨架：结构化 context、受控工具、运行 trace、固定用例和评估规则。它不等于 LangGraph；在接入图工作流之前，它先让边界可测试。

## 2. ContextEnvelope 是什么

把一次任务看成一个被密封的信封：

```python
ContextEnvelope(
    run_id="run-123",
    task_id="task-123",
    user_id="demo-user",
    member_id="father",
    intent="refill",
    action_type="draft",
    task_state=..., 
    conversation_summary=..., 
    tool_evidence_refs=[...],
    rag_source_refs=[...],
    safety_flags=[...],
    allowed_tools=[...],
    memory_refs=[...],
)
```

这里最重要的不是字段数量，而是字段之间的关系：

| 字段 | 解决的问题 | 关键校验 |
| --- | --- | --- |
| `run_id` / `task_id` | 区分一次执行和一个可续跑任务。 | Tool evidence 必须同 run。 |
| `user_id` / `member_id` | 区分账户和当前家庭成员。 | evidence、RAG、memory 必须同 member。 |
| `intent` / `action_type` | 让下一步有明确业务意图。 | 使用 Literal，拒绝未知值。 |
| `TaskState` | 区分缺失信息、已确认信息、待确认项和候选推断。 | 候选推断不自动进入 memory。 |
| `conversation_summary` | 传递任务摘要而不是完整 history。 | 留 `source_ids`，可追溯摘要来源。 |
| `allowed_tools` | 把“能做什么”写入上下文。 | Registry 再次强制校验。 |
| `memory_refs` | 保存允许复用的长期信息。 | 必须 `confirmed_by_user=True`。 |

看 [context_schemas.py](../../backend/app/agent/context_schemas.py) 时，重点读每个 `model_validator`。这就是“规则写进数据类型”的方式。

## 3. 最小角色视图为什么重要

RoleSpecificContextView 不是把 envelope 复制一份再删几个字段，而是一个新的严格模型。Planner 只需要摘要、intent 和槽位；RefillAgent 只需要处方/药箱 evidence；PharmacyAgent 不应看到病史；EvaluatorAgent 完全不走业务角色视图。

`ContextManager.build_role_view` 用三组映射控制可见工具、evidence 和 slot 关键词。对初学者来说，这是一个可理解的最小权限实现：先在 domain 层定义“谁能看什么”，再让同一个函数稳定地投影数据。

## 4. Tool Registry 如何把调用变成受控操作

一个 ToolSpec 至少包含：

```python
ToolSpec(
    name="query_medicine_box",
    input_schema=MedicineBoxInput,
    output_schema=MedicineBoxOutput,
    permission_scope="medicine_box:read",
    allowed_agent_roles=("RefillAgent", "ReminderAgent", "SafetyAgent"),
    timeout_ms=1000,
    retry_policy=RetryPolicy(),
    requires_human_confirmation=False,
    read_only=True,
)
```

Registry 的价值不是保存一个 `dict[name] = function`，而是把以下检查统一放在 handler 之前：工具名存在、当前 context 允许、角色许可、确认状态、输入 schema。handler 之后再验证输出 schema。无论哪一步失败，都生成标准化 ToolResult：

```text
success=False
error_type="permission_denied" | "not_found" | "input_schema_error" | ...
fallback_action="manual_review" | "ask_user_clarification" | ...
```

这让上层 Agent 不必猜异常字符串，也让测试可以明确断言失败路径。

## 5. 人工确认与本地草稿

`create_confirmation_draft` 体现了两层防线：

1. Registry 发现工具 `requires_human_confirmation=True` 且 context 尚未确认，就直接返回失败，不调用 handler。
2. handler 即使被允许执行，也只调用 service 创建本地 `draft`，并标记 `external_action_status="not_submitted"`。

因此“用户确认”在当前项目中只意味着“允许保存本地草稿”，不是“医院已经收到申请”或“药店已经下单”。这句话在代码、测试、文档和面试里都必须一致。

## 6. Trace 与评估

真正的质量检查不应该读取可变的 runtime object，而应读取冻结的 `RunTrace`：工具调用、RAG、Safety、FinalAnswer 和延迟都在其中。ExpectedCase 再声明期望 intent、成员、工具、来源、安全标记、确认和禁用表达。

DeterministicEvaluator 比较二者，得到 EvaluationResult。它能发现：

- 需要的工具没调用。
- 需要的 safety flag 缺失。
- 答案含禁用表达。
- 成员串扰。
- 无来源却输出事实。
- 要确认却没有确认提示。

它不评判回答“像不像医生”，而是检查流程是否遵守已声明规则。这是当前阶段选择 deterministic evaluator 的理由：可重放、可测试、不会把模型评模型的随机性引进来。

## 7. SafetyAgent 与 EvaluatorAgent 的区别

| 维度 | SafetyAgent | EvaluatorAgent |
| --- | --- | --- |
| 时间 | 生成答案或动作前 | 答案生成后 |
| 输入 | 当前业务 context、风险信号、必要 evidence | Frozen trace、答案、expected case |
| 输出 | 拦截、转人工、要求确认 | EvaluationResult 与失败原因 |
| 能否写业务状态 | 仅通过受控流程决定拦截/确认 | 不能 |
| 能否改答案 | 运行时阻断或约束生成 | 不能 |

## 8. 阅读与练习

建议按 `context_schemas.py` -> `context_manager.py` -> `tool_schemas.py` -> `tool_registry.py` -> `run_trace_schemas.py` -> `evaluator.py` 的顺序读。

练习：给一个“母亲提醒草稿”用例手工画出 ContextEnvelope、ReminderAgent view、ToolExecutionContext、ToolResult 和 RunTrace 的字段流向。然后在 `test_harness_runtime.py` 中找一个类似测试，对照你的图哪里漏了来源或确认信息。

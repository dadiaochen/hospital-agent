# Agent Runtime 与运行 API

## 1. 定位

2G-1 的 `LangGraphAgentWorkflow` 负责纯编排：输入 `WorkflowRunRequest`，输出 `WorkflowRunResult`。2G-2 增加的 `AgentRuntimeService` 是应用层适配器，负责把 HTTP、当前用户、数据库会话、真实工具、事务和冻结审计产物连接起来。

```text
HTTP request
  -> FastAPI Router / API DTO
  -> AgentRuntimeService
  -> AgentRun(status=running)
  -> LangGraphAgentWorkflow
  -> DB Tool Registry / Hybrid RAG / local draft tool
  -> FinalAnswer + RunTrace + RunSummary + EvaluationResult
  -> AgentToolCall rows + versioned PersistedRunArtifacts
  -> API response
```

Router 不写 SQL，不调用 provider，不直接拼装 graph state。LangGraph 不负责 HTTP 和审计事务。Evaluator 不持有数据库 Session，也不写答案或业务状态。

## 2. HTTP 契约

| 方法 | 路径 | 正常状态 | 作用 |
| --- | --- | --- | --- |
| `POST` | `/api/agent-runs` | `201` | 创建并执行首次 run。 |
| `GET` | `/api/agent-runs/{run_id}` | `200` | 查询 run 摘要，不暴露 `raw_state`。 |
| `GET` | `/api/agent-runs/{run_id}/tool-calls` | `200` | 查询逐次工具审计。 |
| `GET` | `/api/agent-runs/{run_id}/artifacts` | `200` | 查询冻结 Trace、来源、安全与评估。 |
| `POST` | `/api/agent-runs/{run_id}/continue` | `201` | 对待确认 run 做同任务续跑。 |

首次运行示例：

```json
{
  "member_id": "member-mother",
  "idempotency_key": "reminder-start-001",
  "user_input": "请给妈妈创建每天早晚的用药提醒。",
  "medication_name": "metformin",
  "city": "Shanghai",
  "human_confirmation_granted": false
}
```

首次运行不能直接确认。该字段传 `true` 会得到 `422`。如果计划需要创建提醒、续方、复诊或购药草稿，首次响应为 `needs_confirmation`，此时还没有业务草稿行。

确认续跑示例：

```json
{
  "idempotency_key": "reminder-confirm-001",
  "confirmation_message": "我确认创建这份本地提醒草稿。",
  "human_confirmation_granted": true
}
```

续跑只创建本地 `draft`，不会调用医院、药店、支付或推送服务。响应中的 `external_action_status` 永远是 `not_submitted`。

## 3. 首次运行流程

1. `AgentRunCreateRequest` 校验长度、空白和 `human_confirmation_granted=false`。
2. `DemoUser` 依赖从服务端配置定位当前 demo user；客户端不能提交 `user_id`。
3. Service 用 `user_id + member_id` 查询成员。不存在和越权统一返回 `404`。
4. `user_id + idempotency_key` 经 UUID5 得到稳定 `run_id`，请求正文经规范化 JSON 和 SHA-256 得到 fingerprint。
5. Service 先提交一条 `status="running"` 的 AgentRun。即使后续图失败，也有可审计 run。
6. Service 构造 WorkflowRunRequest，并注入含真实只读工具和本地 draft 工具的 DB Tool Registry。
7. LangGraph 执行 Planner、ContextManager、角色 Agent、Safety、FinalAnswer、reset 和 Evaluator。
8. 每个 ToolResult 写入 AgentToolCall；稳定工具调用 UUID 同时写入 ToolEvidenceRef。
9. 最终 `PersistedRunArtifacts` 写入 `AgentRun.raw_state`，run 状态更新为 completed、needs_confirmation、blocked 或 failed。

首次等待确认时，operational ExpectedCase 只要求本轮允许执行的只读工具，不把尚未获准的 `create_confirmation_draft` 误判成漏调工具。

## 4. 确认续跑

只有 `status="needs_confirmation"` 的当前用户 run 可以续跑。续跑遵循：

- 新 `run_id`，但沿用原 `task_id` 和 `member_id`。
- Planner 复用上一轮结构化 WorkflowPlan，不从确认短句重新猜 intent。
- ContextEnvelope 只恢复上一轮 RunSummary、计划和 source IDs。
- DB evidence 工具重新查询，因此不会直接复用可能过期的处方、药箱或库存输出。
- `create_confirmation_draft` 只有在 Tool Registry 同时看到正确角色、allowed tool 和显式确认时才执行。
- 成功后清除 pending confirmation，FinalAnswerTrace 记录 `human_confirmation_present=true` 和 `action_status="draft"`。

一个上一轮 run 只有一个由 `user_id + previous_run_id` 决定的 continuation run ID。相同请求可以 replay；更换幂等键或确认正文会得到冲突，不会创建第二份草稿。

## 5. PersistedRunArtifacts

`agent_runs.raw_state` 不是任意工作流字典，而是版本化 Pydantic 契约：

| 字段 | 用途 |
| --- | --- |
| `schema_version` | 当前为 `2g2.v1`，支持未来兼容读取。 |
| `task_id` / `plan` | 续跑身份和冻结计划。 |
| `run_trace` | 工具、RAG、安全、答案、延迟和 schema 的冻结快照。 |
| `model_call_trace` | 脱敏后的 provider、fallback、schema/safety、耗时和 attempts；不含 prompt、Key 或原文。 |
| `run_summary` | reset 后状态、待确认项和来源引用。 |
| `tool_evidence_refs` | DB/API 工具事实指针；`tool_call_id` 可查询审计行。 |
| `rag_source_refs` | 真实 document/chunk/version/purpose 指针。 |
| `evaluation_result` | post-run deterministic 评估结果。 |
| `request_context` | 续跑所需的最小结构字段，例如药名和城市。 |
| `request_fingerprint` | 服务端幂等冲突判断，不通过 artifacts API 暴露。 |
| `resumed_from_run_id` / `restored_source_ids` | 续跑链和恢复的来源指针。 |
| `external_action_status` | 固定 `not_submitted`。 |

明确不持久化：RoleSpecificContextView、完整聊天历史、scratchpad、临时工具拼装结果、API Key、完整 prompt、provider 未校验原文。

## 6. 事务与失败

- running run 先提交，避免执行异常后完全没有审计记录。
- 工作流成功后，tool calls、最终 run 指标和 frozen artifacts 在一次 service 提交中保存。
- 工作流或持久化异常时，run 标为 `failed`，只保留 `error_type`、task 和 fingerprint。
- 客户端只收到统一 `agent_run_failed`，不会得到内部异常消息或 provider 原文。
- running/failed run 没有完整冻结产物时，artifacts 查询返回 `409 runtime_artifact_unavailable`。

确认工具本身只提交本地 draft，并在业务 JSON 中写入 `created_by_run_id`、幂等键和 `not_submitted` 审计。不存在外部动作补偿逻辑，因为本阶段没有外部动作。

## 7. 代码入口

- HTTP 路由：[agent_audit.py](../backend/app/api/routes/agent_audit.py)
- HTTP DTO：[agent_runtime.py](../backend/app/schemas/agent_runtime.py)
- Runtime service：[agent_runtime_service.py](../backend/app/services/agent_runtime_service.py)
- 冻结持久化契约：[runtime_schemas.py](../backend/app/agent/runtime_schemas.py)
- 工作流输入与续跑契约：[workflow_schemas.py](../backend/app/agent/workflow_schemas.py)
- LangGraph 节点：[langgraph_workflow.py](../backend/app/agent/langgraph_workflow.py)
- DB tools：[db_tools.py](../backend/app/tools/db_tools.py)
- API 回归：[test_agent_runtime_api.py](../backend/tests/test_agent_runtime_api.py)

## 8. 验证

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_agent_runtime_api.py -q -p no:cacheprovider --basetemp=.tmp\pytest-runtime
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

测试覆盖真实 DB evidence、冻结回放、ToolEvidence 到数据库 tool-call 行的引用、幂等冲突、重复确认防护、跨成员/跨用户隔离、高风险阻断和失败 run 审计。测试模型仍是 deterministic provider，不能据此声称真实 LLM 质量指标。

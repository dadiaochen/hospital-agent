# API 文档

## 1. 文档边界

本文件区分当前可调用的 HTTP 接口与只供 Agent 内部使用的 Python 契约。不要根据 ORM、service 或 ToolRegistry 的存在推断 HTTP endpoint 已上线。

## 2. 系统接口

| 方法 | 路径 | 响应 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/` | `service`、`version`、`status`、`phase` | 服务根信息。 |
| `GET` | `/health` | `status` | 容器或服务健康检查。 |
| `GET` | `/api/health` | `SystemStatus(status, phase)` | 带 Pydantic response model 的 API 健康检查。 |

FastAPI Swagger 位于 `http://localhost:8000/docs`。root 与 health response 的 `phase` 仍是骨架服务标识，不是总路线图的状态机；项目阶段请查看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

## 3. 已实现的 2E-1 读取接口

所有端点只读，使用环境变量 `DEMO_USER_PHONE` 定位固定 demo user。成员类路径必须属于该用户；不属于当前 demo user 的成员或 run 一律返回 `404`，不暴露其存在。

| 方法 | 路径 | 响应 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/family-members` | `FamilyMemberListResponse` | 当前 demo user 的成员列表。 |
| `GET` | `/api/family-members/{member_id}/health-profile` | `FamilyMemberHealthProfileResponse` | 成员与健康档案。 |
| `GET` | `/api/family-members/{member_id}/medicine-box` | `MedicineBoxListResponse` | 成员药箱。 |
| `GET` | `/api/family-members/{member_id}/prescriptions` | `PrescriptionListResponse` | 历史处方。 |
| `GET` | `/api/family-members/{member_id}/purchase-records` | `PurchaseRecordListResponse` | 历史购药记录。 |
| `GET` | `/api/pharmacy-inventory?medicine_name=&city=` | `PharmacyInventoryListResponse` | 至少提供药名或城市之一的库存候选查询。 |
| `GET` | `/api/agent-runs?member_id=` | `AgentRunListResponse` | 当前 demo user 的 run，可按成员过滤。 |
| `GET` | `/api/agent-runs/{run_id}` | `AgentRunResponse` | 单个 run，不返回内部 `raw_state`。 |
| `GET` | `/api/agent-runs/{run_id}/tool-calls` | `AgentToolCallListResponse` | 当前用户 run 的工具审计。 |
| `GET` | `/api/knowledge/search?q=&category=` | `KnowledgeSearchResponse` | 确定性知识 chunk 搜索，返回稳定 `source_id`。 |

成功响应的字段由 `backend/app/schemas/` 中的 Pydantic DTO 定义，时间和日期按 JSON 标准格式序列化。所有已处理错误使用同一结构：

```json
{
  "error": {
    "code": "not_found | validation_error",
    "message": "human-readable message",
    "details": null
  }
}
```

路由不写 SQL；成员作用域、查询与空资源判断位于 `ReadApiService`。库存没有匹配项时返回空 `items`，因为搜索没有结果不是权限错误。

## 4. 2E-1 学习 API：知识库搜索

`GET /api/knowledge/search` 已完成 DTO、service 查询、路由接入、统一 `422` 和专用 API 测试。无命中返回 `200 + items=[]`，每个命中项包含 `knowledge:{document_id}:{chunk_id}` 来源指针。完整代码阅读、Swagger/Postman 和测试复盘见 [API 开发教程](learning/API_DEVELOPMENT_TUTORIAL.md)。

## 5. 2E-2 草稿 API

以下接口已经在线性历史中实现，并与 2E-1 读取 API 一起注册到 FastAPI。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/confirmation-drafts` | 经显式确认后创建四类本地草稿；幂等键重复时返回原草稿。 |
| `GET` | `/api/confirmation-drafts?member_id=&draft_type=&status=` | 查询当前 demo user 的草稿，可按成员、类型和状态过滤。 |
| `GET` | `/api/confirmation-drafts/{draft_type}/{draft_id}` | 查询单个受成员作用域保护的草稿。 |
| `POST` | `/api/confirmation-drafts/{draft_type}/{draft_id}/confirm` | 把本地草稿从 `draft` 转为 `confirmed`。 |
| `POST` | `/api/confirmation-drafts/{draft_type}/{draft_id}/reject` | 把本地草稿从 `draft` 转为 `rejected`。 |

支持的 `draft_type`：`refill_request`、`consultation_request`、`pharmacy_option` 和 `reminder_create`。

创建请求示例：

```json
{
  "member_id": "member-father",
  "draft_type": "refill_request",
  "idempotency_key": "refill-2026-001",
  "run_id": "run-optional",
  "summary": "Prepare refill materials for local review.",
  "payload": {
    "medicine_name": "amlodipine tablets",
    "prescription_id": "prescription-id",
    "remaining_days": 3
  },
  "human_confirmation_granted": true
}
```

确认或拒绝请求示例：

```json
{
  "idempotency_key": "confirm-refill-2026-001",
  "human_confirmation_present": true,
  "note": "Local decision only."
}
```

状态机只允许：

```text
draft -> confirmed
draft -> rejected
```

重复请求同一终态属于幂等 replay；`confirmed -> rejected`、`rejected -> confirmed` 等转换返回 `409 invalid_state_transition`。创建或决策缺少显式确认时返回 `409 human_confirmation_required`。不存在和越权资源统一返回 `404`，不暴露其他用户的数据。创建请求携带可选 `run_id` 时，该 run 必须同时属于当前 demo user 和目标 member；否则同样返回 `404`。

`confirmed` 只表示用户确认了本地草稿状态，不表示医院提交、药店下单或提醒推送。所有响应都包含：

```json
{
  "external_action_status": "not_submitted"
}
```

数据库 `confirmed_at` 延续 2D-2 语义，表示用户曾允许创建本地草稿；最终确认或拒绝时间记录在现有 JSON 审计的 `status_transitions` 中，并通过响应 `resolved_at` 暴露。该设计没有新增 ORM 字段或 Alembic migration。

## 6. 2F-1 内部 Retriever 不是新增 HTTP API

`backend/app/rag/` 提供 Agent 内部检索接口。`search_safety_knowledge` Tool 通过 Retriever 获取来源，但它不会创建新的 FastAPI 路由，也不会替代第 4 节面向客户端的 `GET /api/knowledge/search`。

内部请求和结果由 `RetrievalRequest`、`RetrievedChunk` 与 `RetrievalResult` 描述。每个命中项带 `source_id`、document/chunk ID 与版本、相关性 `score`、本次检索 `purpose` 和 `matched_by`；结果还声明 requested/effective mode 与 fallback 原因。HTTP API 后续可以调用 Retriever，但仍应定义自己的 API DTO 和错误语义，不能直接暴露内部模型。

## 7. 2F-2 Model Gateway 也不是 HTTP API

`ModelGateway` 是 Agent 内部的模型调用边界，不新增客户端 endpoint。它读取服务端环境变量中的 provider、base URL、模型名、Key 和 timeout；业务请求与 API DTO 不能携带或覆盖模型 Key。

Gateway 返回目标 Pydantic output 和 `ModelCallTrace`，不返回 provider 的未校验原始文本。2G-2 Agent Runtime 只通过 Gateway 获得结构化结果，并持久化脱敏 Trace；Router 不能直接调用模型 HTTP endpoint。

4B 任务五新增的 `ComplexityRoute`、`TaskPlan`、`AgentTaskResult`、`SupervisorDecision` 和三阶段 `SafetyDecision`，以及任务六的 `OrchestrationRunResult`，仍然不是独立 HTTP endpoint。4D-B2.1/B4 已由 `UnifiedHealthGraph` 将 `/api/business-tasks` 接入这条编排边界，并由默认 `SupervisorBusinessWorkflow` 实际调用运行时领域 Agent 和 Tool Registry；4D-B2.2 又将 `execution_mode`、`context_mode` 和 `parallel_batches` 写入冻结 `run_trace.orchestration`；4D-B2.3 进一步在业务冻结产物中加入 `FinalClaim`、`AnswerEnvelope` 和 `Trace v2`；4D-B2.4 已生成独立的 300/1200 v2 评测文件；B2.5 已在 `backend/app/agent/` 增加内存 Materializer、九类 grader 和 preview Runner；B2.6 又增加了离线的 PostgreSQL shadow transaction、Provider sandbox、case-scoped RAG 和真实图执行适配器，但这些仍不是 HTTP endpoint。业务响应只返回经过校验的 route/plan/decision/domain-result 投影，不直接暴露原始请求或内部临时状态；Docker 19/19 已通过，300/1200 Gold 已完成人工审核，但完整三 split 正式评测仍需完成真实 integration、消融和 badcase 冻结。

## 8. 2G-2 Agent Runtime API

> **当前兼容实现：** 本节记录已经可调用的 2G-2 旧契约，即首次 run 返回 `needs_confirmation`，确认后才创建本地草稿。任务七没有改写这条旧 API；“首次 run 自动创建本地 `DRAFT`，用户确认执行”的单确认语义已接入下一节的新 `/api/business-tasks`，因此两套字段不能混用。

2G-1 的 `LangGraphAgentWorkflow.run()` 仍是内部 Python 入口。2G-2 通过 `AgentRuntimeService` 注入真实 DB Tool Registry，并新增以下 HTTP 边界：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/agent-runs` | 创建并执行一次未确认的新 run；持久化 run、工具调用和冻结产物。 |
| `GET` | `/api/agent-runs/{run_id}/artifacts` | 查询 RunTrace、RunSummary、Tool/RAG refs、SafetyTrace 和 EvaluationResult。 |
| `POST` | `/api/agent-runs/{run_id}/continue` | 对 `needs_confirmation` run 做同任务确认续跑。 |

首次请求的 `human_confirmation_granted` 只能是 `false`。需要写本地草稿时，响应状态为 `needs_confirmation`，客户端必须再调用 `/continue` 并显式提交 `true`。续跑复用原 `task_id`、结构化 RunSummary 和来源指针，但重新执行当前 DB evidence 查询；它不恢复 raw conversation、scratchpad 或 provider 原始文本。

每次请求必须携带幂等键。同一首次请求可安全 replay；同一待确认 run 只有一个固定 continuation run，不同确认请求会返回 `409 idempotency_conflict`，不会创建重复草稿。所有运行仍按 demo user / member 作用域隔离，确认后固定返回 `external_action_status="not_submitted"`。

完整字段、状态和持久化说明见 [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md)。

## 9. 4B 业务任务 API

4B 把三条业务线统一为一个任务入口，业务域由请求字段区分；上层 API 不直接调用 LangGraph、Provider 或数据库。任务七已经把新业务任务链路接入 `confirmation_state` 状态机；请求体仍保留 `human_confirmation_granted` 作为兼容确认字段，旧 `/api/agent-runs` 也继续保持原契约。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/business-tasks` | 创建一次预问诊/导诊、慢病履约或健康档案任务；首次请求不能直接确认。 |
| `GET` | `/api/business-tasks` | 按 `member_id`、`status`、`business_domain` 查询当前用户任务。 |
| `GET` | `/api/business-tasks/{task_id}` | 查询任务摘要。 |
| `GET` | `/api/business-tasks/{task_id}/sources` | 查询该任务保留的 Provider/RAG/工具来源引用。 |
| `GET` | `/api/business-tasks/{task_id}/artifacts` | 查询最新冻结的 `RunTrace`、`RunSummary`、`EvaluationResult` 和工具/Provider 产物。 |
| `POST` | `/api/business-tasks/{task_id}/confirm` | 对已有本地 `DRAFT` 确认执行，创建同一 task 的独立 continuation run。 |
| `POST` | `/api/preferences` | 在同 task 的已执行人工确认和 source version 校验通过后写入可撤销偏好。 |

首次创建示例：

```json
{
  "business_domain": "chronic_care",
  "member_id": "member-father",
  "user_input": "请整理父亲的降压药续方材料。",
  "input_payload": {
    "action_type": "refill_request",
    "medicine_name": "amlodipine"
  },
  "idempotency_key": "demo-refill-001",
  "provider_mode": "mock",
  "human_confirmation_granted": false
}
```

`business_domain` 当前支持 `preconsultation`、`chronic_care`、`health_record`；Provider 模式支持 `mock`、`sandbox`、`real`。当前仓库只实现 mock adapter，未配置的 sandbox/real 会返回 `degraded=true` 和明确 fallback reason，不会返回伪造的实时医院、药店或通知结果。

任务九后，`provider_calls` 中每项还包含统一 `error_category`、`latency_ms` 和 `attempts`。可恢复的只读 timeout/rate-limit/provider-unavailable 只在服务端固定上限内重试；请求参数、权限、成员作用域、schema 和 business conflict 不重试。Provider 降级属于业务执行结果，HTTP 请求本身仍可返回业务任务 DTO；客户端必须同时检查顶层 `status/degraded` 和每个 Provider call，不能把 HTTP 201 等同于外部服务成功。

失败 Provider call 的 `response_payload.data` 与 `source_refs` 必须为空。mock 药房的 `order_created`、医院的 `appointment_created` 和问诊的 `submitted` 始终为 false；当前 API 不提供真实外部写入成功语义。

新业务任务首次成功的 HTTP 状态仍是 `needs_confirmation`，但语义已经是“草稿自动生成，等待执行确认”。响应同时返回 `confirmation_state="DRAFT"` 和无外部副作用的 `confirmation_draft`；确认续跑成功后返回 `confirmation_state="EXECUTED"`。`EXECUTED` 只表示本地状态迁移完成，外部状态仍为 `not_submitted`。响应必须携带：

- `confirmation_request`：将要写入的本地草稿类型和摘要；
- `confirmation_state` / `confirmation_draft`：草稿状态、版本、成员、动作类型和本地/外部边界；
- `source_refs`：带 `member_id`、文档版本或 Provider 模拟标记的来源；
- `run_trace`、`run_summary`、`evaluation_result`：只读冻结产物；
- `model_call_trace`：最终答案 Gateway 调用的 provider、schema、安全、fallback 和耗时信息，不包含 Key、完整 prompt 或 provider 原始文本。
- `checkpoint_version` / `confirmation_version`：当前权威 checkpoint 和确认状态版本；客户端确认时应原样回传以启用乐观并发校验；
- `checkpoint_source`、`resumed_from_run_id`、`restored_source_ids`：说明本次结果是否从 Redis/PostgreSQL checkpoint 恢复以及恢复的来源指针。

当前确认请求使用兼容字段：

```json
{
  "human_confirmation_granted": true,
  "idempotency_key": "demo-refill-001",
  "checkpoint_version": 1,
  "confirmation_version": 1
}
```

`GET /artifacts` 适合详情页、审计和回放；前端不得修改返回的 Trace 或 Evaluation。高风险请求在业务工具前由 Agent 安全阻断，不能通过确认接口绕过。

最终确认流程是同一 `task_id` 下的两个独立 run：首次 run 冻结草稿、答案与来源；确认 run 从 PostgreSQL Task Checkpoint 恢复，重新读取可变业务事实，再通过动作策略检查、事务和幂等键执行。Redis 只做 TTL 缓存与多实例协调，缓存故障必须回源 PostgreSQL。

任务八已补充并冻结以下 checkpoint 相关字段：

- `confirmation_state`：草稿、已确认、已执行或终止状态；
- `checkpoint_version`：续跑时用于乐观并发控制；
- `run_id` 与 `parent_run_id`：明确两个 run 的因果关系；
- `source_refs`：保留业务 DB、Provider 和 RAG 来源，不接受个人健康向量记忆作为事实来源。

### 9.1 已确认偏好写入

`POST /api/preferences` 的请求必须包含 `task_id`、`member_id`、`preference_type`、`preference_value`、`source_id`、`source_version`、`confirmation_version`、`idempotency_key`，并且 `human_confirmation_granted` 只能为 `true`。服务端会校验：

- task 属于当前用户和成员，且已完成 `DRAFT -> CONFIRMED -> EXECUTED`；
- confirmation version 与权威 task/checkpoint 一致，存在同 task 的人工确认记录；
- source 属于同一 task/member，source version 与数据库来源版本一致；
- 偏好不是处方、诊断、剂量、过敏、报告、库存或症状等医疗事实；
- 同一幂等键只 replay，不会重复创建版本。

返回的偏好带 `preference_version`、`consent_version`、来源版本和 `revocable`；它不是模型长期记忆，也不会替代权威处方、报告或药箱数据。

## 10. 当前前端 API 消费约定

3A 页面通过 `frontend/lib/api/client.ts` 统一访问上述接口。浏览器 base URL 来自 `NEXT_PUBLIC_API_BASE_URL`，默认 `http://localhost:8000`；页面不得直接写数据库地址或模型配置。

| 页面 | 消费接口 |
| --- | --- |
| 家庭成员 | `/api/family-members`、`/{member_id}/health-profile` |
| 家庭药箱 | `/{member_id}/medicine-box` |
| 续方/复诊 | `/{member_id}/prescriptions`、`/api/confirmation-drafts?member_id=` |
| 提醒 | `/api/confirmation-drafts?member_id=`，客户端只保留 `reminder_create` |
| 购药信息 | `/{member_id}/purchase-records`、`/api/pharmacy-inventory` |
| 知识检索 | `/api/knowledge/search?q=&category=`，依赖学习题完成并合入 |
| Agent runs | `/api/agent-runs?member_id=` |
| Agent 对话 | `POST /api/agent-runs` |
| 确认续跑 | `POST /api/agent-runs/{run_id}/continue` |
| Run 详情 | `/api/agent-runs/{run_id}`、`/tool-calls`、`/artifacts` |
| 报告解读 | `GET /api/family-members/{member_id}/reports`、`GET /api/family-members/{member_id}/reports/{report_id}` |

UX-06 已按冻结的 `report-detail.v1` 契约接入以下只读接口：

- `GET /api/family-members/{member_id}/reports`
- `GET /api/family-members/{member_id}/reports/{report_id}`

字段、状态、指标解释、来源和安全提示以 [REPORT_DETAIL_CONTRACT.md](REPORT_DETAIL_CONTRACT.md) 的 `report-detail.v1` 为准。

接口只读取当前用户和当前家庭成员范围内的 `medical_documents`，不会触发上传、解析任务、健康事件写入、诊断或治疗动作。详情响应中的指标和章节必须引用同一响应内的来源；前端发现来源引用不完整时直接进入错误态，不自行补造来源。

所有成员类 response 在后端作用域校验后，还会被浏览器检查 `member_id`。不匹配时前端抛出 `context_isolation_failed` 并停止展示；这不是认证替代品，而是防止异常 response 造成可见串扰的第二道防线。

当前前端首次请求固定发送 `human_confirmation_granted=false`。只有后端返回 `needs_confirmation` 且没有 Agent 安全阻断时，页面才允许用户勾选“我已阅读上面的整理内容，确认继续”，再调用 `/continue`；确认消息由代码生成，不把内部草稿或外部提交约束暴露给用户。历史咨询通过同一 `GET /api/agent-runs?member_id=` 按当前成员读取，页面只展示用户可读的状态、时间和整理结果。详情页仍只读消费冻结的 FinalAnswer、Tool/RAG refs、SafetyTrace、ModelCallTrace 和 EvaluationResult，不在浏览器重算或修改它们。完整交互见 [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md)。

## 11. API 设计规则

1. Router 只做协议转换；查询、写入和权限判断放到 service。
2. API DTO 与 ORM 分离，不能直接把 SQLAlchemy 模型序列化给客户端。
3. 所有成员读取必须从当前 demo user 和指定 `member_id` 的作用域开始。
4. 不存在、越权、schema 失败和状态冲突要有可预测的错误格式。
5. 含有医疗敏感内容的写操作在 API 层之外还必须经过 safety 与 confirmation 规则。

2E-1、2E-2、2F、2G、3B 和 4B 任务一至十二已进入当前线性工作区；任务十二已用真实 Docker 栈验收现有业务 API、知识搜索、错误映射、确认并发和 Redis checkpoint 回源。阶段状态只以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为准。
## 4B 任务十：Trace 响应补强

任务十没有新增 HTTP 路径，也没有改变业务任务的确认语义。现有 `/api/business-tasks` 和 artifacts 响应中的 `run_trace` 新增 `observations`；`model_call_trace` 新增可选 `input_tokens/output_tokens/total_tokens` 与 `token_usage_available`。

每条 Observation 只包含 request/task/run/member 标识、事件类型、node、序号、工具/Provider/模型名、结果、时延、重试、fallback、source ID 和可用 token 计数。请求正文、`input_payload`、Tool 输入输出、Provider 请求响应、模型 messages、最终答案正文和凭据不进入该数组。Provider 未返回完整 usage 时三个 token 字段均为 `null`，`token_usage_available=false`，服务端不估造数值。

这是兼容性扩展：旧客户端可以忽略新增字段。`RunTrace` 和 Observation 均为只读审计产物，不能通过 API 回写业务状态。

## 4B 任务十一：Harness 入口边界

任务十一没有新增 HTTP API，也没有让客户端选择 A/B/C 策略。消融只通过 `python -m app.agent.ablation_harness` 离线执行，读取固定 fixture 并把 JSON/Markdown 报告写到 `output/`；提交到仓库的 Markdown 是复核后的确定性快照。生产业务 API 的模型、工具或安全配置仍不能由请求覆盖。

## 4B 任务十二：API 真实运行边界

任务十二没有新增 HTTP 路径，而是通过 `scripts/task12_acceptance.py` 对现有 `/health`、`/api/family-members`、三类 `/api/business-tasks` 操作和 `/api/knowledge/search` 做 Docker smoke。验收确认业务接口仍返回结构化 DTO、缺少知识查询参数映射为 422、重复确认只执行一次；Redis 不可用时，业务 API 从 PostgreSQL 恢复权威 checkpoint。该脚本不调用 LLM 或真实外部 Provider。

4D-B3 的真实模型 runner 是离线评测脚本，不新增 HTTP endpoint。它的审核队列会保存脱敏 `ConfirmationDraftSnapshot`，证明 shadow run 生成了本地草稿但没有提交外部提醒；正常业务 API 的 `confirmation_draft` 字段和 Task Checkpoint 才是可供前端展示、查询和确认的业务契约。

## 用户端 UX-08 入口边界

UX-08 没有新增或删除 API。前端公共入口只消费既有的 Agent、历史咨询、家庭记录和报告读取接口；`/knowledge`、`/purchase-plans`、`/refill-plans`、`/medicine-box`、`/reminders` 以及 `/agent-runs/{run_id}` 只作为兼容地址跳转，不再作为用户端的内部操作页面。知识检索、库存查询、草稿状态和 Trace 仍是服务端业务/治理能力，不能因入口隐藏而解除成员隔离、来源校验或人工确认。

## 用户端 UX-09 联调边界

UX-09 没有新增 HTTP 路径、数据库字段或外部动作。前端真实消费既有成员、Agent run、家庭记录和报告 DTO，并验证 `user_id + member_id` 隔离、确认续跑和兼容跳转。用户端只展示用户可读结果，原始运行标识、工具调用和来源指针继续留在服务端冻结产物中。

联调发现既有低库存续方请求在用户没有显式填写药品名时，药店库存工具输入无法通过契约校验。现由 `WorkflowToolInputBuilder` 从同一成员已成功读取的药箱或处方事实补齐 `medicine_name`；如果没有可验证事实仍保持缺失并失败，不由模型或浏览器猜测。该修正只同步既有 Tool 输入契约，不改变接口语义、确认规则或外部提交能力。

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

`GET /api/knowledge/search` 已完成 DTO、service 查询、路由接入、统一 `422` 和专用 API 测试。无命中返回 `200 + items=[]`，每个命中项包含 `knowledge:{document_id}:{chunk_id}` 来源指针。完整代码阅读、Swagger/Postman 和测试复盘见 [06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md](learning/06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md)。

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

4A 为这个内部 Retriever 接入 FastEmbed + pgvector，不新增 HTTP endpoint，也不改变 `GET /api/knowledge/search` 的既有响应 DTO。Agent Tool 在向量配置开启时可得到 `effective_mode="hybrid"` 和 `matched_by="vector"` 来源；客户端仍只能消费有 document/chunk 指针的已审核正文，不能提交任意文本进入向量库。

## 7. 2F-2 Model Gateway 也不是 HTTP API

`ModelGateway` 是 Agent 内部的模型调用边界，不新增客户端 endpoint。它读取服务端环境变量中的 provider、base URL、模型名、Key 和 timeout；业务请求与 API DTO 不能携带或覆盖模型 Key。

Gateway 返回目标 Pydantic output 和 `ModelCallTrace`，不返回 provider 的未校验原始文本。2G-2 Agent Runtime 只通过 Gateway 获得结构化结果，并持久化脱敏 Trace；Router 不能直接调用模型 HTTP endpoint。

## 8. 2G-2 Agent Runtime API

2G-1 的 `LangGraphAgentWorkflow.run()` 仍是内部 Python 入口。2G-2 通过 `AgentRuntimeService` 注入真实 DB Tool Registry，并新增以下 HTTP 边界：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/agent-runs` | 创建并执行一次未确认的新 run；持久化 run、工具调用和冻结产物。 |
| `GET` | `/api/agent-runs/{run_id}/artifacts` | 查询 RunTrace、RunSummary、Tool/RAG refs、SafetyTrace 和 EvaluationResult。 |
| `POST` | `/api/agent-runs/{run_id}/continue` | 对 `needs_confirmation` run 做同任务确认续跑。 |

首次请求的 `human_confirmation_granted` 只能是 `false`。需要写本地草稿时，响应状态为 `needs_confirmation`，客户端必须再调用 `/continue` 并显式提交 `true`。续跑复用原 `task_id`、结构化 RunSummary 和来源指针，但重新执行当前 DB evidence 查询；它不恢复 raw conversation、scratchpad 或 provider 原始文本。

每次请求必须携带幂等键。同一首次请求可安全 replay；同一待确认 run 只有一个固定 continuation run，不同确认请求会返回 `409 idempotency_conflict`，不会创建重复草稿。所有运行仍按 demo user / member 作用域隔离，确认后固定返回 `external_action_status="not_submitted"`。

完整字段、状态和持久化说明见 [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md)。

## 9. 3A/3B 前端 API 消费约定

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

所有成员类 response 在后端作用域校验后，还会被浏览器检查 `member_id`。不匹配时前端抛出 `context_isolation_failed` 并停止展示；这不是认证替代品，而是防止异常 response 造成可见串扰的第二道防线。

3B 首次请求固定发送 `human_confirmation_granted=false`。只有后端返回 `needs_confirmation` 且没有 SafetyAgent 阻断时，页面才允许用户勾选本地草稿声明并调用 `/continue`。详情页只读消费冻结 FinalAnswer、Tool/RAG refs、SafetyTrace、ModelCallTrace 和 EvaluationResult，不在浏览器重算或修改它们。完整交互见 [AGENT_UI.md](AGENT_UI.md)。

## 10. API 设计规则

1. Router 只做协议转换；查询、写入和权限判断放到 service。
2. API DTO 与 ORM 分离，不能直接把 SQLAlchemy 模型序列化给客户端。
3. 所有成员读取必须从当前 demo user 和指定 `member_id` 的作用域开始。
4. 不存在、越权、schema 失败和状态冲突要有可预测的错误格式。
5. 含有医疗敏感内容的写操作在 API 层之外还必须经过 safety 与 confirmation 规则。

## 11. 3C Harness 的 API 使用边界

3C 没有新增 HTTP endpoint。`RuntimeE2EHarnessRunner` 作为外部客户端复用：

- `GET /api/family-members`：按 relationship 发现当前 seed 的稳定 member ID。
- `POST /api/agent-runs`：执行首轮固定用例，始终提交 `human_confirmation_granted=false`。
- `POST /api/agent-runs/{run_id}/continue`：仅对需要确认的正常业务执行续跑。

越权成员预期返回 `404 not_found`；首轮确认绕过预期返回 `422 validation_error`。高风险 `blocked` run 不调用 `/continue`。Harness 只读取 response，不调用数据库、不改写 artifacts，也不通过测试接口绕开生产路由。

## 12. 3D 固定演示不新增 HTTP API

`MvpDemoRunner` 复用 `GET /api/family-members`、`POST /api/agent-runs` 和 `POST /api/agent-runs/{run_id}/continue`。它不会增加测试专用 endpoint、绕开 demo-user/member scope 或直接访问数据库。三条正常场景按 API 契约先等待确认，高风险场景不调用 continuation；报告只保存脱敏的状态和来源数量。

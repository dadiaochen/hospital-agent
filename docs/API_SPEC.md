# API 文档

## 1. 文档边界

本文件区分“当前可调用的接口”“本分支已实现的读取接口”和“路线图已定义、但尚未实现的接口”。不要根据 ORM、service 或 ToolRegistry 的存在推断 HTTP endpoint 已上线。

## 2. 系统接口

| 方法 | 路径 | 响应 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/` | `service`、`version`、`status`、`phase` | 服务根信息。 |
| `GET` | `/health` | `status` | 容器或服务健康检查。 |
| `GET` | `/api/health` | `SystemStatus(status, phase)` | 带 Pydantic response model 的 API 健康检查。 |

FastAPI Swagger 位于 `http://localhost:8000/docs`。root 与 health response 的 `phase` 仍是骨架服务标识，不是总路线图的状态机；项目阶段请查看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

## 3. 本分支已实现的 2E-1 读取接口

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

## 4. 2E-1 学习者 API：知识库搜索

`GET /api/knowledge/search` 的 DTO、service、路由注册和统一 `422` 已实现，并已在 Docker PostgreSQL seed 数据上通过真实 HTTP 验证。查询无命中返回 `200 + items=[]`；缺失或空白 `q` 返回 `422 validation_error`；每个命中项带 `knowledge:{document_id}:{chunk_id}` 来源指针。

`backend/tests/test_knowledge_api.py` 已完成，覆盖正常命中、分类过滤、空结果、缺失/空白参数、统一 `422` 与 OpenAPI 注册。完整代码阅读、Postman 和测试步骤见 [06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md](learning/06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md)。

## 5. 隔离分支中的 2E-2 草稿 API

以下接口已经在 `codex/2e-2-draft-confirmation-api` 隔离分支实现。它们将在 2E-1 知识搜索完成后 rebase、回归和进入主线；路线图在此之前仍保持 2E-1 为 `NEXT`。

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

## 6. API 设计规则

1. Router 只做协议转换；查询、写入和权限判断放到 service。
2. API DTO 与 ORM 分离，不能直接把 SQLAlchemy 模型序列化给客户端。
3. 所有成员读取必须从当前 demo user 和指定 `member_id` 的作用域开始。
4. 不存在、越权、schema 失败和状态冲突要有可预测的错误格式。
5. 含有医疗敏感内容的写操作在 API 层之外还必须经过 safety 与 confirmation 规则。

2E-1 已通过知识库搜索专用自动化测试；2E-2 草稿状态机 API 已在其线性基础上实现。两者都只处理本地数据，不代表任何外部医疗动作成功。

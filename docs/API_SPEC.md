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

## 4. 留给学习者的完整 API：知识库搜索

`GET /api/knowledge/search` 属于 2E-1 范围，但在本分支刻意未实现。完整接口契约、DTO、service 查询、路由接入、错误语义、Swagger 检查和测试验收见 [06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md](learning/06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md)。完成它后，2E-1 的所有读取资源才算齐全。

## 5. 后续草稿 API 边界

路线图的 `2E-2` 才负责本地草稿的创建、查询、确认和拒绝。其状态机必须只允许白名单转换，确认操作要幂等，并保留 `human_confirmation` 审计信息。即使确认成功，也只改变本地 draft 状态，不代表外部医疗或购药动作成功。

## 6. API 设计规则

1. Router 只做协议转换；查询、写入和权限判断放到 service。
2. API DTO 与 ORM 分离，不能直接把 SQLAlchemy 模型序列化给客户端。
3. 所有成员读取必须从当前 demo user 和指定 `member_id` 的作用域开始。
4. 不存在、越权、schema 失败和状态冲突要有可预测的错误格式。
5. 含有医疗敏感内容的写操作在 API 层之外还必须经过 safety 与 confirmation 规则。

知识库搜索完成前，2E-1 仍不应在路线图中标记为完成。草稿和确认 API 仍属于 2E-2，不应被读取接口提前实现。

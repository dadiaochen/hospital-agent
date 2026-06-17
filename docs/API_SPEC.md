# API Spec

## 1. Phase 1 已实现接口

### GET `/`

返回后端服务基础状态。

### GET `/health`

返回健康检查。

### GET `/api/health`

返回 API 命名空间下的健康检查。

## 1.1 Phase 2A 说明

第二阶段 2A 只实现数据库基础设施、ORM 模型、Alembic 迁移和 seed 数据，未新增业务 API。现有健康检查接口保持不变。

## 1.2 Phase 2A.1 说明

第二阶段 2A.1 只补充 Agent Harness / Trace 观测字段和文档规则，仍未新增业务 API。现有健康检查接口保持不变。

后续 `GET /api/agent/runs`、`GET /api/agent/runs/{id}` 和 `GET /api/agent/runs/{id}/tool-calls` 接入时，应返回本阶段新增字段：

- `agent_runs`: `started_at`、`ended_at`、`duration_ms`、`step_count`、`task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate`
- `agent_tool_calls`: `agent_role`、`error_type`、`fallback_action`、`schema_valid`

这些字段用于 trace replay 和 harness 评估，不代表当前阶段已经实现 Agent Harness 自动评估。

## 1.3 Phase 2A.2 / 2B-1 说明

阶段 2A.2 只完成 Context 与 Evaluator 架构设计。阶段 2B-1 只实现 Pydantic 契约、16 条 ExpectedCase fixture 和测试，未新增或修改任何 FastAPI API。

`ContextEnvelope`、`RoleSpecificContextView`、`RunSummary`、`ExpectedCase` 和 `EvaluationResult` 当前是内部 Agent Harness 契约，不代表已存在对应 HTTP endpoint。后续如暴露 API，必须单独定义请求/响应 DTO、权限和医疗安全边界。

## 1.4 Phase 2B-2 说明

阶段 2B-2 新增离线 deterministic evaluator 和 fixture runner，不新增任何 FastAPI endpoint。HarnessRunner 直接读取本地测试 fixture，不通过 HTTP 调用业务系统。

## 2. 后续业务接口设计

所有接口默认使用 JSON。涉及关键动作的请求体必须包含或返回 `requires_human_confirmation` / `confirmed_by_user` 等字段。

## 3. 家庭成员

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/family-members` | 查询家庭成员列表 |
| POST | `/api/family-members` | 创建家庭成员 |
| GET | `/api/family-members/{id}` | 查询家庭成员详情 |

## 4. 家庭药箱

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/medicine-box` | 查询家庭药箱 |
| POST | `/api/medicine-box` | 添加药箱条目 |
| GET | `/api/medicine-box/{id}` | 查询药箱条目详情 |

## 5. 处方与购药记录

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/prescriptions` | 查询历史处方 |
| POST | `/api/prescriptions` | 创建处方记录 |
| GET | `/api/purchase-records` | 查询购药记录 |
| POST | `/api/purchase-records` | 创建购药记录 |

## 6. Agent

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/agent/chat` | Agent 对话入口 |
| POST | `/api/agent/run` | 创建 Agent run |
| GET | `/api/agent/runs` | 查询 Agent run 列表 |
| GET | `/api/agent/runs/{id}` | 查询 Agent run 详情 |
| GET | `/api/agent/runs/{id}/tool-calls` | 查询工具调用链路 |

## 7. 知识库

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/knowledge` | 查询知识文档 |
| POST | `/api/knowledge` | 创建知识文档 |
| GET | `/api/knowledge/search` | 关键词检索知识库 |

## 8. 提醒任务

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/reminders` | 查询提醒 |
| POST | `/api/reminders` | 创建提醒草稿或提醒任务 |
| PATCH | `/api/reminders/{id}` | 更新提醒状态 |

## 9. Agent Chat 请求草案

```json
{
  "user_id": "uuid",
  "message": "我爸的降压药快吃完了，帮我看看能不能续方。",
  "confirmed_action_id": null
}
```

## 10. Agent Chat 响应草案

```json
{
  "run_id": "uuid",
  "intent": "chronic_refill",
  "answer": "已为你整理续方前材料，下一步需要你确认是否发起复诊申请。",
  "need_human_confirmation": true,
  "confirmation_action": {
    "type": "create_consultation_draft",
    "label": "确认创建复诊申请草稿"
  },
  "sources": [
    {
      "type": "prescription",
      "id": "uuid",
      "title": "父亲最近一次降压药处方"
    }
  ],
  "safety_result": {
    "allowed": true,
    "reason": "仅整理材料，未提供诊断或调整剂量建议"
  }
}
```

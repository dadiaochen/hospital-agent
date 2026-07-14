# API 文档

## 1. 文档边界

本文件区分“当前可调用的接口”和“路线图已定义、但尚未实现的接口”。不要根据 ORM、service 或 ToolRegistry 的存在推断 HTTP endpoint 已上线。

## 2. 当前已实现接口

| 方法 | 路径 | 响应 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/` | `service`、`version`、`status`、`phase` | 服务根信息。 |
| `GET` | `/health` | `status` | 容器或服务健康检查。 |
| `GET` | `/api/health` | `SystemStatus(status, phase)` | 带 Pydantic response model 的 API 健康检查。 |

FastAPI Swagger 位于 `http://localhost:8000/docs`。当前 root 与 health response 的 `phase` 仍是骨架服务标识，不是总路线图的状态机；项目阶段请查看 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md)。

## 3. 即将实现的读取 API 边界

路线图的 `2E-1` 将把已有只读 services 暴露为 HTTP API，范围只包括：

- 家庭成员与健康档案。
- 家庭药箱。
- 处方和购药记录。
- 药店库存。
- 知识库查询。
- Agent run 与 tool call 查询。

每个 endpoint 必须有独立 Pydantic request/response DTO、统一错误响应、demo user 范围和 `member_id` 隔离。它不会在读取阶段引入 LangGraph、外部医院/药店调用或复杂写入流程。

## 4. 后续草稿 API 边界

路线图的 `2E-2` 才负责本地草稿的创建、查询、确认和拒绝。其状态机必须只允许白名单转换，确认操作要幂等，并保留 `human_confirmation` 审计信息。即使确认成功，也只改变本地 draft 状态，不代表外部医疗或购药动作成功。

## 5. API 设计规则

1. Router 只做协议转换；查询、写入和权限判断放到 service。
2. API DTO 与 ORM 分离，不能直接把 SQLAlchemy 模型序列化给客户端。
3. 所有读取必须从当前 demo user 和指定 `member_id` 的作用域开始。
4. 不存在、越权、schema 失败和状态冲突要有可预测的错误格式。
5. 含有医疗敏感内容的写操作在 API 层之外还必须经过 safety 与 confirmation 规则。

接口真正落地后，本文件会添加路径、字段表、示例和错误码；在此之前，以上内容只是已批准的边界，不是可调用承诺。

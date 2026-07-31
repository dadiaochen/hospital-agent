# 02. 后端、数据与字段设计

## 1. 先理解分层，而不是先背 FastAPI

一次“查成员药箱”的完整路径应该是：HTTP 请求进入 `api`，DTO 在 `schemas` 校验，`service` 组织查询，`models` 映射数据库，返回时再由 DTO 输出。Agent 想查同一数据时，不直接复用 HTTP，而是经受约束的 Tool Registry 调 service。

这样拆分的收益是：数据库查询只有一份，API 和 Agent 使用不同的协议边界；测试可以分别验证 service、tool 和 API。

## 2. 实体如何从业务名词得到

先从名词表开始：用户、家庭成员、档案、药箱、处方、购药、药店、库存、草稿、提醒、知识文档、Agent run、工具调用。每个名词问四个问题：

1. 它是谁拥有的？例如药箱属于 `FamilyMember`。
2. 它是否有生命周期？例如草稿有 `status` 与确认时间。
3. 它需要保存事实还是结构化扩展？固定字段用列，可变细节用 JSON。
4. 它需要被谁查询？高频筛选字段要索引。

## 3. 本项目的关键字段为何存在

| 模型 | 字段 | 设计理由 |
| --- | --- | --- |
| `FamilyMember` | `user_id` + `relationship` | 数据所有权与家庭语义；联合唯一防止重复关系。 |
| `HealthProfile` | `member_id`、`allergies`、`safety_notes` | 每次 Agent 查询都必须先知道服务对象和风险提示。 |
| `MedicineBoxItem` | `remaining_quantity`、`dosage`、`frequency`、`estimated_remaining_days` | 保存用户已有药箱事实；不是 Agent 的剂量建议。 |
| `Prescription` | `prescription_no`、`doctor_name`、`medicine_items`、`expires_at` | 证明材料来自既有医生处方，而不是模型生成。 |
| `PurchaseRecord` | `prescription_id`、`pharmacy_id`、`purchased_at` | 把购药事实连接回处方和药店。 |
| `HumanConfirmationMixin` | `status`、`need_human_confirmation`、`confirmed_at`、`confirmation_note` | 所有关键草稿共享同一确认审计语义。 |
| `AgentRun` | `intent`、`status`、`safety_result`、`duration_ms`、`task_success` | 让一次运行可观察、可回放、可评估。 |
| `AgentToolCall` | `agent_role`、`tool_input/output`、`error_type`、`fallback_action`、`schema_valid` | 让失败也成为可审计数据，而不是只留日志文本。 |

完整字段表见 [DB_SCHEMA.md](../DB_SCHEMA.md)，实际定义见 `backend/app/models/`。

## 4. ORM 字段和 Pydantic 字段不是一回事

SQLAlchemy 模型描述“数据库如何存”，例如 `Prescription.medicine_items` 是 JSON 列。Pydantic 模型描述“组件之间允许交换什么”，例如 `ToolEvidenceRef` 要求 `source_id`、`run_id`、`member_id` 和 `schema_valid`。

不要把 ORM 当 API response：ORM 暴露的是内部表结构、关系和懒加载行为；DTO 应该由 API 或工具按用途组织。例如库存工具只输出 `medicine_name`、`city` 和 `inventory_items`，不返回整个 Session 对象或不相关成员。

## 5. service 与事务边界

`confirmation_draft_service.py` 负责验证 user/member 关系、关联记录和幂等键，并创建 ORM 草稿。工具层负责确认门禁、工具 schema 和将数据库异常转换为 ToolExecutionError。只有输出 schema 已验证后，工具才 commit；异常会 rollback。

这是一个可复用的经验：**业务规则留在 service，协议门禁留在上层，提交放在成功路径末尾。**

## 6. 自己读代码的顺序

1. 看 `models/base.py`，理解所有表的 id 和 timestamp。
2. 看 `models/user.py`，从用户到成员到档案。
3. 看 `models/medication.py` 和 `models/plans.py`，理解事实记录和草稿的区别。
4. 看 `services/confirmation_draft_service.py`，追踪一次本地草稿创建。
5. 看 `tools/confirmation_tools.py`，看 service 如何被确认门禁包起来。

## 7. 练习

为“药店库存候选”设计一个 API response DTO。先写出哪些字段必须返回，哪些字段绝不能返回；再解释为什么它不应包含下单状态或医院提交状态。之后对照未来 API 边界，暂时不要直接实现 endpoint。

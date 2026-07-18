# 数据库设计

## 1. 通用约定

所有业务表继承 `IDMixin` 与 `TimestampMixin`，因此都有字符串主键 `id`、`created_at` 和 `updated_at`。关系字段使用外键，常用筛选键如 `user_id`、`member_id`、`run_id`、药名和城市建立索引。ORM 定义是字段的最终实现来源。

## 2. 用户与成员

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `users` | `name`、`phone`、`is_active` | 账户主体；`phone` 唯一且可索引。 |
| `family_members` | `user_id`、`name`、`relationship`、`gender`、`birthday`、`default_address` | 被管理的家庭成员；`(user_id, relationship)` 唯一，防止同一关系重复。 |
| `health_profiles` | `member_id`、`chronic_disease_tags`、`allergies`、`current_medications`、`health_notes`、`safety_notes` | 一成员一份健康档案；结构化列表适合 demo 数据与工具返回。 |

`member_id` 是隔离边界。Agent 或 API 不能凭用户输入切换到其他成员；必须与执行上下文一致。

## 3. 药箱、处方与购药

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `medicine_box_items` | `member_id`、`medicine_name`、`specification`、`total_quantity`、`remaining_quantity`、`dosage`、`frequency`、`purchased_at`、`estimated_remaining_days`、`safety_note` | 家庭药箱的实际库存和处方快照信息。 |
| `prescriptions` | `member_id`、`prescription_no`、`doctor_name`、`hospital_name`、`doctor_diagnosis_summary`、`medicine_items`、`issued_at`、`expires_at`、`status`、`doctor_confirmation_required`、`safety_note` | 已有医生处方的记录；不是 AI 生成处方。 |
| `purchase_records` | `member_id`、`prescription_id`、`pharmacy_id`、`medicine_name`、`quantity`、`dosage`、`frequency`、`pharmacy_name`、`purchased_at`、`purchase_channel` | 历史购药事实，用于材料整理与来源引用。 |

`dosage` 和 `frequency` 保存的是已有记录，不能被 Agent 用来推导或建议加减药。

## 4. 药店与库存

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `pharmacies` | `name`、`city`、`address`、`supports_delivery`、`supports_pickup`、`contact_phone` | 药店实体；`(name, city)` 唯一。 |
| `pharmacy_inventory` | `pharmacy_id`、`medicine_name`、`stock_quantity`、`delivery_options`、`safety_note` | 库存候选；`(pharmacy_id, medicine_name)` 唯一。 |

库存查询仅提供候选信息，不创建订单或承诺可履约。

## 5. 待确认业务草稿

`HumanConfirmationMixin` 为下列表统一提供 `status`、`need_human_confirmation`、`confirmed_at` 和 `confirmation_note`：

| 表 | 特有字段 | 表达的业务对象 |
| --- | --- | --- |
| `refill_plans` | `prescription_id`、`medicine_name`、`remaining_days`、`plan_detail`、`suggestion`、`doctor_confirmation_required` | 续方材料或本地方案草稿。 |
| `consultation_drafts` | `prescription_id`、`draft_content`、`material_summary`、`doctor_confirmation_required` | 复诊材料草稿。 |
| `purchase_plans` | `medicine_name`、`pharmacy_id`、`plan_detail`、`delivery_option` | 购药候选草稿。 |
| `medication_reminders` | `medicine_box_item_id`、`medicine_name`、`schedule`、`reminder_type` | 提醒草稿。 |
| `follow_up_tasks` | `task_type`、`due_date`、`task_payload` | 随访任务草稿。 |

当前确认工具只写本地 `draft`，并将 run、幂等键、外部动作状态等审计数据放在现有 JSON detail 中；没有新增外部提交状态字段。

2E-2 API 的确认和拒绝仍复用这四张表及现有 JSON 字段，不新增 ORM 列或 migration。每次有效终态转换追加到 `_agent_audit.status_transitions`，记录 `from_status`、`to_status`、`resolved_at`、`idempotency_key`、`user_id`、`note` 和固定的 `external_action_status="not_submitted"`。数据库 `confirmed_at` 继续表示允许创建本地草稿；最终决策时间由审计 transition 保存。

## 6. 知识库

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `knowledge_documents` | `title`、`category`、`source`、`content`、`safety_level` | 可说明来源的知识文档。 |
| `knowledge_chunks` | `document_id`、`chunk_index`、`content`、`keywords` | 文档分块和关键词检索单元。 |

RAG 输出必须带来源指针；没有命中文档或工具 evidence 时不能编造医学事实。2F-1 不增加向量列或 migration：关键词基线直接读取上述两张表，document/chunk 的 `updated_at` 作为当前版本指针返回。可选向量后端只返回 ID 和相关性分数，Retriever 必须用 ID 重新加载数据库正文；不存在或 document/chunk 不匹配的指针会被拒绝并回退关键词结果。

## 7. Agent 审计

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `agent_memories` | `user_id`、`member_id`、`memory_type`、`content`、`source` | 长期记忆的持久化模型；写入前必须满足用户确认门槛。 |
| `agent_runs` | `user_id`、`member_id`、`user_goal`、`intent`、`status`、`final_answer`、`safety_result`、`raw_state`、`started_at`、`ended_at`、`duration_ms`、`step_count`、`task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate` | 一次运行的可观测性记录。 |
| `agent_tool_calls` | `run_id`、`agent_role`、`tool_name`、`tool_input`、`tool_output`、`latency_ms`、`success`、`error_message`、`error_type`、`fallback_action`、`schema_valid` | run 内每次工具调用的审计记录。 |

数据库表是未来 runtime 持久化目标；当前 deterministic Harness 使用冻结 Pydantic trace，不等同于完整线上持久化。

## 8. 明确禁止

数据库中不得出现 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 等将医疗决策归因于 AI 的字段。对于 schema 变更，先更新 ORM、迁移、seed、测试与本文件，再进行 API 或 Agent 使用。

## 9. Migration 可移植性

Alembic 默认将内部 `alembic_version.version_num` 建为 `VARCHAR(32)`，但本仓库保留了超过 32 字符的描述性 revision ID。SQLite 不强制 `VARCHAR(n)` 长度，因此早期 SQLite migration 可以通过；PostgreSQL 会严格拒绝超长 revision。

`0001_initial_schema` 在 PostgreSQL 分支先将该内部列扩为 `VARCHAR(64)`，再创建业务表。SQLite 测试分支不执行这条 PostgreSQL DDL。这个调整只修复 migration 元数据容量，没有新增或修改 ORM 业务字段，也没有改变 `0002_add_agent_harness_trace_fields` 的 revision ID。

2E-1 的读取 API 没有新增业务表或业务列；它只是将现有只读查询按 demo-user / member scope 暴露为 HTTP DTO。

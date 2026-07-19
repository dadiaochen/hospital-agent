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
| `knowledge_chunks` | `document_id`、`chunk_index`、`content`、`keywords`、`embedding`、`embedding_model`、`embedding_content_hash`、`embedded_at` | 文档分块、关键词检索单元和可选 512 维向量索引。 |

RAG 输出必须带来源指针；没有命中文档或工具 evidence 时不能编造医学事实。4A migration `0003_lightweight_vector_rag` 在 PostgreSQL 启用 pgvector，并增加可空 `VECTOR(512)`、模型名、内容哈希和索引时间。关键词基线不依赖这些字段；向量后端仍只返回 ID 和相关性分数，Retriever 必须用 ID 重新加载数据库正文。模型不一致、索引缺失、指针不存在或 document/chunk 不匹配时会拒绝向量结果并回退关键词。

## 7. Agent 审计

| 表 | 核心字段 | 设计意图 |
| --- | --- | --- |
| `agent_memories` | `user_id`、`member_id`、`memory_type`、`content`、`source` | 长期记忆的持久化模型；写入前必须满足用户确认门槛。 |
| `agent_runs` | `user_id`、`member_id`、`user_goal`、`intent`、`status`、`final_answer`、`safety_result`、`raw_state`、`started_at`、`ended_at`、`duration_ms`、`step_count`、`task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate` | 一次运行的可观测性记录。 |
| `agent_tool_calls` | `run_id`、`agent_role`、`tool_name`、`tool_input`、`tool_output`、`latency_ms`、`success`、`error_message`、`error_type`、`fallback_action`、`schema_valid` | run 内每次工具调用的审计记录。 |

2G-2 使用现有两张审计表实现 runtime 持久化，不新增 ORM 字段或 migration。`agent_runs.raw_state` 保存版本化 `PersistedRunArtifacts`，包含冻结 RunTrace、脱敏 ModelCallTrace、RunSummary、来源 refs、EvaluationResult、续跑引用和请求指纹；不保存 role views、raw conversation、scratchpad、API Key、完整 prompt 或 provider 原始文本。`agent_tool_calls.id` 使用稳定 UUID，并与 ToolEvidenceRef 的 `tool_call_id` 对齐。

2F-2 的 `ModelCallTrace` 和 provider attempt trace 不新增 ORM 字段或 migration；2G-2 将其脱敏结构放入版本化 runtime artifact。API Key、完整 prompt 和 provider 原始文本不得写入审计表。

`WorkflowState` 和 role views 仍只存在于一次 Python 进程内。2G-2 只持久化 reset 后需要审计或续跑的最小冻结产物，并通过 AgentRuntimeService 注入真实 DB tools；工作流类本身仍可使用 mock registry 做离线测试。

## 8. 明确禁止

数据库中不得出现 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 等将医疗决策归因于 AI 的字段。对于 schema 变更，先更新 ORM、迁移、seed、测试与本文件，再进行 API 或 Agent 使用。

## 9. Migration 可移植性

Alembic 默认将内部 `alembic_version.version_num` 建为 `VARCHAR(32)`，但本仓库保留了超过 32 字符的描述性 revision ID。SQLite 不强制 `VARCHAR(n)` 长度，因此早期 SQLite migration 可以通过；PostgreSQL 会严格拒绝超长 revision。

`0002_add_agent_harness_trace_fields` 在执行本阶段字段变更前，先在 PostgreSQL 中将该内部列扩为 `VARCHAR(64)`。因此全新数据库和已停在 `0001` 的数据库都可以升级；SQLite 测试分支不执行这条 PostgreSQL DDL。这个调整只修复 migration 元数据容量，没有新增额外 ORM 业务字段，也没有改变 revision ID。

2E-1 的读取 API 没有新增或修改任何 ORM 字段、Alembic migration 或 seed 数据；它只是将现有只读查询按 demo-user / member scope 暴露为 HTTP DTO。

2G-1 也没有修改 ORM、Alembic migration 或 seed；工作流状态不能被误认为数据库事实。

3A 前端数据页面同样没有修改 ORM、Alembic migration 或 seed。TypeScript response 类型只是后端 Pydantic DTO 的浏览器侧镜像，不是新的数据库 schema；字段真相仍以 ORM、migration 和 API DTO 为准。

3B Agent/Trace UI 也没有新增表或字段。页面读取现有 `agent_runs`、`agent_tool_calls` 和 `raw_state` 中的版本化冻结产物；确认续跑仍通过 AgentRuntimeService 使用现有本地草稿表，外部动作状态固定为 `not_submitted`。

3C Runtime E2E 同样没有修改 ORM、Alembic migration 或 seed。Runner 只通过现有 HTTP API 触发 run 并读取冻结 artifacts；脱敏 JSON/Markdown 报告属于测试产物，不写入业务表。PostgreSQL 集成报告复用现有 seed 数据，pytest 则继续使用隔离 SQLite。

3D 没有新增 ORM 字段或 migration，也没有修改 seed 业务内容。Docker backend 入口只是自动执行现有 `alembic upgrade head` 与幂等 seed；固定四场景通过现有 API 创建 run、tool-call 审计和本地草稿，外部状态始终是 `not_submitted`。
## 10. 4B 模型接入说明

4B 没有新增 ORM 字段或 Alembic migration。模型 provider 配置只来自 backend 环境变量；Key、完整 prompt 和 provider 原始文本不写入数据库。既有 `agent_runs.raw_state` 只保存版本化、脱敏的 `ModelCallTrace`。

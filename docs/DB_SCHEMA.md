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

BM25、RRF、实体过滤与轻量 rerank 只读取现有知识字段，不新增表或迁移。评测中的 HNSW 复用必须同时校验 document/chunk ID、版本和 embedding model；它只是运行内加速，不成为知识事实来源。

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

3B Agent/Trace UI 也没有新增表或字段。页面读取现有 `agent_runs`、`agent_tool_calls` 和 `raw_state` 中的版本化冻结产物；确认续跑仍通过 AgentRuntimeService 使用现有本地草稿表，外部动作状态固定为 `not_submitted`。UX-04 的“历史咨询”只按 `agent_runs.member_id` 读取当前成员的用户可读字段，不改变数据库事实或成员隔离约束。

UX-06 报告详情同样没有新增 ORM 字段、Alembic migration 或上传表；报告列表和详情接口复用现有 `medical_documents`，由 service 将 `extracted_content` 投影为冻结的报告 DTO。`object_uri`、parser provider 和原始 JSON 不直接暴露给浏览器，成员与用户作用域仍由数据库查询负责。

3C Runtime E2E 同样没有修改 ORM、Alembic migration 或 seed。Runner 只通过现有 HTTP API 触发 run 并读取冻结 artifacts；脱敏 JSON/Markdown 报告属于测试产物，不写入业务表。PostgreSQL 集成报告复用现有 seed 数据，pytest 则继续使用隔离 SQLite。

3D 没有新增 ORM 字段或 migration，也没有修改 seed 业务内容。Docker backend 入口只是自动执行现有 `alembic upgrade head` 与幂等 seed；固定四场景通过现有 API 创建 run、tool-call 审计和本地草稿，外部状态始终是 `not_submitted`。

4B 任务七没有新增 ORM 字段；任务八完成了对这些 JSON artifact 的审计和升级。新业务任务仍在 `business_tasks.output_payload` / `agent_runs.raw_state` 保留脱敏冻结产物，但权威任务进度、确认状态迁移和已确认偏好现在分别写入 `task_checkpoints`、`task_confirmation_records` 和 `confirmed_preferences`。`BusinessTaskService.confirm_task` 在 PostgreSQL 上锁定任务行，校验 user/member/task、checkpoint version、confirmation version、指纹和幂等键；Redis 只缓存 checkpoint 投影。
## 10. 当前迁移链

当前仓库必须保持一条 Alembic head，完整升级顺序为：

```text
0001_initial_schema
  -> 0002_add_agent_harness_trace_fields
  -> 0003_lightweight_vector_rag
  -> 0004_business_task_runtime
  -> 0005_knowledge_metadata
  -> 0006_vector_search_index
  -> 0007_task_checkpoint_state
```

## 11. Supervisor 运行数据说明

4D-B4 没有修改 ORM、Alembic migration 或 seed。`SupervisorBusinessWorkflow`
复用现有 `agent_runs`、`agent_tool_calls`、`raw_state` 和业务任务冻结产物记录
运行时的 Supervisor、领域 Agent、Tool Evidence、来源指针和治理结果；运行时
领域 Agent 不直接持有数据库 Session，而是通过 Tool Registry 访问这些已有数据。

因此，本阶段新增的是执行接线和测试，不是新的数据库表。需要数据库迁移时，仍
必须先同步 ORM、Alembic、seed、测试和本文件，不能把工作流内存状态当成新表字段。

每个 revision 的职责边界如下：

- `0001_initial_schema`：基础用户、家庭成员、药品、知识库和审计表。
- `0002_add_agent_harness_trace_fields`：补充 Agent run/tool-call 的 trace 字段，并在 PostgreSQL 中扩大 Alembic 内部版本号列。
- `0003_lightweight_vector_rag`：在 `knowledge_chunks` 增加可空 `VECTOR(512)`（SQLite 使用 JSON 兼容类型）、embedding 模型名、内容哈希和索引时间。
- `0004_business_task_runtime`：增加业务任务、provider 调用、来源引用、医疗文档和健康事件等 runtime 表。
- `0005_knowledge_metadata`：增加知识文档 `version` 与知识分块 `chunk_version`。它只负责版本元数据，不重复创建 0003 已拥有的向量字段。
- `0006_vector_search_index`：在 PostgreSQL 为可用向量创建 HNSW cosine index；SQLite 环境跳过原生索引创建，仍可执行迁移链并测试关键词降级。
- `0007_task_checkpoint_state`：增加业务任务的 checkpoint/confirmation version、Agent continuation 的 `parent_run_id`，以及 PostgreSQL 权威 checkpoint、确认记录和已确认偏好表；SQLite 保留可测试的列和表约束。

禁止再次创建平行的 `0003` revision；新增 schema 变更必须从 `0007_task_checkpoint_state` 继续串联，并同步 ORM、seed、测试和本节说明。验收命令是 `python -m alembic heads`，预期只输出 `0007_task_checkpoint_state`。

## 12. 模型接入说明

4B 的模型 provider 配置只来自 backend 环境变量，不新增 provider-specific ORM 字段；当前仓库完整 schema 以本节的 `0001` 到 `0007` 迁移链为准。Key、完整 prompt 和 provider 原始文本不写入数据库。既有 `agent_runs.raw_state` 只保存版本化、脱敏的 `ModelCallTrace`。

4B 任务五和任务六只新增内存中的 Pydantic 编排契约、deterministic Router、三个领域 Agent 和 bounded Supervisor，没有修改 ORM、Alembic、seed 或数据库连接；任务六的 `OrchestrationRunResult` 不是独立持久化表。4D-B2.1 由 `UnifiedHealthGraph` 把该结果投影到同一次 `RunTrace`，随业务任务的冻结运行产物进入既有状态保存边界，仍不新增 migration。任务八已把状态恢复边界接入业务任务 service，但没有把 Tool/Provider 可靠性或复杂 RAG 编排提前带入本阶段。

## 13. 状态存储边界

任务八已落地以下 schema 边界：

- PostgreSQL 是 Task Checkpoint、确认记录、用户偏好、运行审计和业务事实的权威存储；`task_checkpoints` 绑定 `task_id`、`user_id`、`member_id`、`thread_id`、run/parent run、checkpoint version、confirmation version、RunSummary、步骤进度、冻结产物和来源指针。
- `task_confirmation_records` 记录草稿/确认/执行动作、前后状态、草稿版本、确认版本、幂等键、请求指纹、操作者和人工确认标志。
- `confirmed_preferences` 只保存同 task 的显式确认结果，绑定成员、source/source version、consent version、偏好版本、幂等键和可撤销状态；模型推断不得进入偏好表。
- Redis 不属于数据库 schema，也不能保存唯一副本；它只缓存 checkpoint 的短期投影并承担多实例协调，故障时回源 PostgreSQL。
- 医疗知识使用独立 PostgreSQL schema/database 与 pgvector 索引；个人处方、报告、药箱和聊天不得写入知识向量表。

`backend/app/services/checkpoint_service.py` 负责权威 checkpoint 的事务写入和 allow-list 投影，`backend/app/services/task_checkpoint_cache.py` 负责 Redis TTL/失效回源，`backend/app/services/preference_service.py` 负责确认后偏好写入。Redis miss、过期、作用域/版本不匹配或异常不会改变 PostgreSQL 业务结果。

## 14. 工具与 Provider 数据库边界

任务九没有新增 ORM、Alembic migration 或 seed。Tool attempts 随 `AgentToolCall.tool_output` 保存；Provider attempts、统一 error category 和降级详情保存在现有 `provider_calls.response_payload` JSON 中，现有 `latency_ms/retryable/degraded/fallback_reason` 列继续保存可查询摘要。失败 Provider 不创建 `source_references` 记录。
## 15. 数据作用域与 Trace 存储

任务十没有修改 ORM 或迁移链。处方、购药记录和药箱读取改为在同一 SQL statement 中联结 `family_members`，同时约束 `FamilyMember.user_id`、`FamilyMember.id` 与业务表 `member_id`；即使调用方拿到另一用户的旧成员/资源 ID，数据库查询也不会返回记录。

RRF rank、原始两路分数、版本、fallback 和脱敏 Observation 继续存入现有 JSON 审计边界（`source_references.source_metadata`、`agent_runs.raw_state` 和 checkpoint frozen artifacts），没有为可观测性新增业务表。Redis 仍不是权威存储；缓存 payload 的 user/member/task/thread/version 任一不匹配都按 miss 处理并回源 PostgreSQL。

## 16. 离线评测的数据库边界

编排与评测没有新增 ORM、Alembic migration、seed 或 Redis key。固定用例的 `RunTrace` 和聚合结果由离线运行器生成，默认输出到被 Git 忽略的 `output/`。真实 Docker PostgreSQL 已验证迁移、seed、pgvector 数据和 Redis 故障时的 PostgreSQL Checkpoint 回源，历史结果见 [项目执行历史](EXECUTION_HISTORY.md)。

## 17. 评测物化边界

内存 Projection Backend 不是 ORM、不是业务数据库，也不新增 Alembic revision。PostgreSQL Materializer 在单个 Case 的 shadow transaction 中物化合成状态并回滚，真实执行业务图后只保留 Git 忽略的 JSON/Markdown 评测产物，不污染业务表。身份和 source alias 必须由本地 identity map 显式提供；意外知识来源只保存不可逆的 `unexpected` 观测 ID，不泄露本地数据库 ID。当前活动 fast-400 合成 Agent 视图用于后续三个 split 的评测，完整 300/1200 来源仅留档。

## 用户端 UX-08 数据边界

UX-08 不新增表、字段、迁移或持久化状态。首页和导航只是既有成员、Agent run、报告和家庭记录的用户端入口；旧内部地址的跳转也不改变 PostgreSQL 权威业务数据、Task Checkpoint 或确认记录。成员隔离仍由既有 API/service 契约负责。

## 用户端 UX-09 数据边界

UX-09 没有新增 ORM、Alembic migration、seed 或 Redis key。前后端联调只读取既有成员、AgentRun、草稿、报告和确认记录；历史结果与家庭管理页面的用户语言转换发生在响应投影层，不回写原始运行状态。低库存工具输入所需的药品名来自同一成员既有 Tool 结果，不形成新的医疗事实或长期记忆。

## 报告闭环复用表

本轮不新增迁移：`medical_documents` 保存原始文本和可直接读取的统一解析结果，上传后状态即为 `ready`。报告解析不创建 `health_record_events`，也不引入报告确认状态；最终回答质量审计保存于既有 `task_checkpoints.frozen_artifacts.final_answer_quality`，PostgreSQL 是权威来源，Redis 不新增 key 或持久状态。

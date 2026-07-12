# Database Schema

第二阶段 2A 已实现 SQLAlchemy ORM、Alembic 初始迁移和 seed 数据。第二阶段 2A.1 已补充 Agent Harness / Trace 观测字段。所有表都包含：

- `id`
- `created_at`
- `updated_at`

方案类和关键动作表使用 `status`、`need_human_confirmation`、`confirmed_at` 表达人工确认状态。数据库不存储 AI 诊断结论，不包含 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 等字段。

## 1. 用户与家庭成员

### users

- `id`
- `name`
- `phone`
- `is_active`
- `created_at`
- `updated_at`

### family_members

- `id`
- `user_id`
- `name`
- `relationship`
- `gender`
- `birthday`
- `default_address`
- `created_at`
- `updated_at`

### health_profiles

- `id`
- `member_id`
- `chronic_disease_tags`
- `allergies`
- `current_medications`
- `health_notes`
- `safety_notes`
- `created_at`
- `updated_at`

## 2. 家庭药箱、处方与购药记录

### medicine_box_items

- `id`
- `member_id`
- `medicine_name`
- `specification`
- `total_quantity`
- `remaining_quantity`
- `dosage`
- `frequency`
- `purchased_at`
- `estimated_remaining_days`
- `safety_note`
- `created_at`
- `updated_at`

### prescriptions

- `id`
- `member_id`
- `prescription_no`
- `doctor_name`
- `hospital_name`
- `doctor_diagnosis_summary`
- `medicine_items`
- `issued_at`
- `expires_at`
- `status`
- `doctor_confirmation_required`
- `safety_note`
- `created_at`
- `updated_at`

说明：`doctor_diagnosis_summary` 只保存医生处方记录快照，不保存 AI 诊断结论。

### purchase_records

- `id`
- `member_id`
- `prescription_id`
- `pharmacy_id`
- `medicine_name`
- `quantity`
- `dosage`
- `frequency`
- `pharmacy_name`
- `purchased_at`
- `purchase_channel`
- `created_at`
- `updated_at`

## 3. 药店履约

### pharmacies

- `id`
- `name`
- `city`
- `address`
- `supports_delivery`
- `supports_pickup`
- `contact_phone`
- `created_at`
- `updated_at`

### pharmacy_inventory

- `id`
- `pharmacy_id`
- `medicine_name`
- `stock_quantity`
- `delivery_options`
- `safety_note`
- `created_at`
- `updated_at`

## 4. 复诊续方、购药方案与提醒任务

### refill_plans

- `id`
- `member_id`
- `prescription_id`
- `medicine_name`
- `remaining_days`
- `plan_detail`
- `suggestion`
- `safety_note`
- `doctor_confirmation_required`
- `status`
- `need_human_confirmation`
- `confirmed_at`
- `confirmation_note`
- `created_at`
- `updated_at`

### consultation_drafts

- `id`
- `member_id`
- `prescription_id`
- `draft_content`
- `material_summary`
- `safety_note`
- `doctor_confirmation_required`
- `status`
- `need_human_confirmation`
- `confirmed_at`
- `confirmation_note`
- `created_at`
- `updated_at`

### purchase_plans

- `id`
- `member_id`
- `medicine_name`
- `pharmacy_id`
- `plan_detail`
- `delivery_option`
- `safety_note`
- `doctor_confirmation_required`
- `status`
- `need_human_confirmation`
- `confirmed_at`
- `confirmation_note`
- `created_at`
- `updated_at`

### medication_reminders

- `id`
- `member_id`
- `medicine_box_item_id`
- `medicine_name`
- `schedule`
- `reminder_type`
- `safety_note`
- `status`
- `need_human_confirmation`
- `confirmed_at`
- `confirmation_note`
- `created_at`
- `updated_at`

### follow_up_tasks

- `id`
- `member_id`
- `task_type`
- `due_date`
- `task_payload`
- `safety_note`
- `status`
- `need_human_confirmation`
- `confirmed_at`
- `confirmation_note`
- `created_at`
- `updated_at`

## 5. 知识库

### knowledge_documents

- `id`
- `title`
- `category`
- `source`
- `content`
- `safety_level`
- `created_at`
- `updated_at`

### knowledge_chunks

- `id`
- `document_id`
- `chunk_index`
- `content`
- `keywords`
- `created_at`
- `updated_at`

## 6. Agent 日志

### agent_memories

- `id`
- `user_id`
- `member_id`
- `memory_type`
- `content`
- `source`
- `created_at`
- `updated_at`

### agent_runs

- `id`
- `user_id`
- `member_id`
- `user_goal`
- `intent`
- `status`
- `final_answer`
- `need_human_confirmation`
- `safety_result`
- `raw_state`
- `started_at`
- `ended_at`
- `duration_ms`
- `step_count`
- `task_success`
- `groundedness_score`
- `hallucination_flag`
- `human_confirmation_rate`
- `created_at`
- `updated_at`

字段说明：

- `started_at`: Agent run 开始时间，默认当前时间，用于后续计算延迟。
- `ended_at`: Agent run 结束时间，未结束或未回填时为空。
- `duration_ms`: Agent run 总耗时毫秒数，未计算时为空。
- `step_count`: Agent 工作流执行步数，默认 `0`。
- `task_success`: Harness 对任务是否完成的评估结果；未跑评估时为空。
- `groundedness_score`: 事实来源和回答 groundedness 评分；未跑评估时为空。
- `hallucination_flag`: 是否命中幻觉风险，默认 `false`。
- `human_confirmation_rate`: 关键动作人工确认覆盖率；未跑评估时为空。

### agent_tool_calls

- `id`
- `run_id`
- `agent_role`
- `tool_name`
- `tool_input`
- `tool_output`
- `latency_ms`
- `success`
- `error_message`
- `error_type`
- `fallback_action`
- `schema_valid`
- `created_at`
- `updated_at`

字段说明：

- `agent_role`: 发起工具调用的角色 Agent，默认 `unknown`，后续用于定位 Planner/Profile/Refill/Pharmacy/Reminder/Safety 链路问题。
- `error_type`: 工具失败分类，例如参数错误、超时、数据不存在、未授权、服务不可用；成功调用为空。
- `fallback_action`: 工具失败或风险触发后的兜底动作，例如澄清、重试、转人工确认或仅生成材料草稿。
- `schema_valid`: 工具输入/输出是否通过 schema 校验，默认 `true`。

## 6.1 第二阶段 2A.1 Trace 字段策略

- `AgentRun.started_at` 使用数据库和 ORM 默认值，保证旧数据迁移后有开始时间。
- `AgentRun.ended_at`、`duration_ms`、`task_success`、`groundedness_score`、`human_confirmation_rate` 允许为空，用于区分“尚未执行/尚未评估”和“评估结果为 0”。
- `AgentRun.step_count` 默认 `0`，后续 LangGraph / Harness 回填真实步数。
- `AgentRun.hallucination_flag` 默认 `false`，只表示未发现或未评估到幻觉风险，不代表已经通过完整评测。
- `AgentToolCall.agent_role` 默认 `unknown`，避免历史工具调用迁移失败。
- `AgentToolCall.schema_valid` 默认 `true`，后续 Tool Registry 接入 schema 校验后回填真实结果。

## 7. Seed 数据

`scripts/seed.py` 会创建或更新：

- 用户：陈毅。
- 家庭成员：本人、父亲、母亲。
- 父亲：高血压长期用药，苯磺酸氨氯地平片，预计剩余 3 天。
- 母亲：睡眠问题 / 中医复诊，中药颗粒，预计剩余 2 天。
- 历史处方、购药记录、家庭药箱、药店库存。
- 复诊续方 SOP、用药提醒模板、人工确认规则、医疗安全边界规则。
- 示例 `agent_runs` 与 `agent_tool_calls` 审计记录。
- 阶段 2A.1 的 seed 示例包含一条成功的 `RefillAgent` 药箱查询工具调用，以及一条 `PharmacyAgent` 库存查询失败后进入 fallback 的工具调用。

## 8. 阶段 2A.2 / 2B-1 数据库边界

- 阶段 2A.2 只完成 Context Lifecycle 和 EvaluatorAgent 架构设计。
- 阶段 2B-1 只新增 Pydantic 契约、固定 ExpectedCase fixture 和测试。
- `RunSummary`、`ContextEnvelope`、`EvaluationResult` 当前没有新增数据库表或字段。
- 本阶段未新增 Alembic migration，未修改 ORM 模型或 `scripts/seed.py`。
- 后续是否持久化 EvaluationResult，必须在独立数据库阶段评审后决定，不能在 Harness 契约阶段隐式修改数据库。

## 9. 阶段 2B-2 数据库边界

- RunTrace 和 EvaluationResult 当前只存在于 Pydantic 对象、JSON fixture 和 Markdown 示例报告。
- DeterministicEvaluator 与 HarnessRunner 不访问数据库。
- 本阶段未修改 ORM、Alembic migration 或 seed。
- 后续真实 trace adapter 应先读取现有审计数据并映射为冻结 DTO，不应由 evaluator 直接持有数据库 session。

## 10. 阶段 2D-1 数据库边界

- 只读取现有 ORM 表，不新增表、字段或 Alembic migration。
- 读取范围包括家庭成员与档案、处方与购药记录、药箱、药店库存和知识库。
- `ToolResult` 只作为内存结果和后续 Trace adapter 输入，不写入 `agent_tool_calls`。
- `create_confirmation_draft` 留到 2D-2；本阶段不创建复诊、购药、提醒或其他业务状态。
- 缺少数据库事实时返回 `not_found` 与 fallback，不把模型推断写入数据库或长期 memory。

## 11. 阶段 2D-2 数据库边界

- 复用现有 `refill_plans`、`consultation_drafts`、`purchase_plans` 和 `medication_reminders`，不新增表、字段或 migration。
- 草稿保持 `status="draft"` 和 `need_human_confirmation=true`。
- `confirmed_at` 与 `confirmation_note` 记录用户允许创建本地草稿，不表示外部动作完成。
- `created_by_run_id`、幂等键、user/member 和 `external_action_status` 写入现有 JSON 详情字段。
- 幂等在 service 层检查；由于本阶段禁止新增唯一约束，并发重复请求仍需在后续数据库阶段评审。

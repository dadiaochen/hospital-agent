# Technical Design

## 1. 总体架构

系统采用 monorepo：

- `backend`: FastAPI 服务，负责 API、业务服务、数据库、工具注册、RAG、安全策略和 Agent 工作流。
- `frontend`: Next.js App Router 前端，负责家庭健康控制台、Agent 对话、方案管理和执行日志展示。
- `docker-compose.yml`: PostgreSQL、Redis、Backend、Frontend 本地编排。

## 2. 后端分层

- `api`: 路由层，只处理 HTTP 输入输出。
- `services`: 业务编排层，封装复诊、药箱、提醒、知识库等用例。
- `models`: SQLAlchemy 2.x ORM 模型。
- `schemas`: Pydantic 输入输出模型。
- `tools`: MCP-like Tool Registry、工具定义、工具调用执行器。
- `agent`: FamilyHealthAgent、LangGraph 状态和节点。
- `rag`: 知识文档、关键词检索和未来向量检索接口。
- `safety`: 医疗安全边界、人工确认策略、高风险拦截。
- `core`: 配置、数据库连接、日志、通用依赖。

## 3. Agent 架构

主工作流名称：`FamilyHealthAgent`。

第一版使用一个 LangGraph 工作流体现多 Agent 思路：

- `Planner`: 意图识别和任务拆解。
- `ProfileAgent`: 家庭成员与健康档案。
- `RefillAgent`: 剩余药量、处方有效期、续方方案。
- `PharmacyAgent`: 库存、配送、购药方案。
- `ReminderAgent`: 用药提醒、补货提醒、复诊提醒。
- `SafetyAgent`: 医疗边界、安全审核、人工确认判断。
- `EvaluatorAgent`: FinalAnswer 生成后的只读质量评估，不参与业务执行，不修改答案或业务状态。

`SafetyAgent` 位于运行时业务链路，负责在高风险输出或动作发生前拦截；`EvaluatorAgent` 位于 post-run 评估链路，负责对 RunTrace、证据、回答、安全召回和上下文隔离进行事后检查。

## 3.1 Context Lifecycle

```text
Raw Conversation
  -> TaskContext Builder
  -> ContextEnvelope
  -> Role-specific Context View
  -> Tool Evidence / RAG Sources
  -> FinalAnswer
  -> Run Summary
  -> Context Reset
  -> EvaluatorAgent Review
  -> Long-term Memory Write
```

上下文管理不再是单个静态 DTO，而是一套 run 生命周期：原始对话先经过任务构建，角色只接收最小上下文视图；run 结束后生成摘要并 reset working context；EvaluatorAgent 读取冻结快照；长期记忆只写入用户确认且满足来源策略的内容。

## 4. 安全设计

所有医疗相关输出必须遵守：

- 不诊断。
- 不自动开方。
- 不修改处方。
- 不建议用户自行调整药量。
- 复诊、购药、提醒创建必须有人确认。
- 高风险场景必须建议医生或线下就医介入。
- 输出保留依据和 Agent 执行日志。

## 5. MCP-like 工具注册表

每个工具定义包含：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `permission_scope`
- `timeout`
- `retry_policy`
- `requires_human_confirmation`

调用前执行参数校验、权限校验、安全边界校验；调用后记录 `agent_tool_calls`。

## 6. 数据存储

- PostgreSQL: 业务数据、Agent runs、tool calls、知识库。
- Redis: 会话状态、短期任务缓存、未来异步任务队列预留。

## 6.1 第二阶段 2A 数据库层设计

数据库基础设施位于 `backend/app/core/database.py`：

- `Base`: SQLAlchemy 2.x declarative base。
- `engine`: 从 `DATABASE_URL` 创建，不硬编码连接。
- `SessionLocal`: 请求和脚本使用的 session factory。
- `get_db`: FastAPI 依赖，后续 API 阶段接入。

ORM 模型位于 `backend/app/models/`：

- `user.py`: `users`、`family_members`、`health_profiles`。
- `medication.py`: `medicine_box_items`、`prescriptions`、`purchase_records`。
- `pharmacy.py`: `pharmacies`、`pharmacy_inventory`。
- `plans.py`: `refill_plans`、`consultation_drafts`、`purchase_plans`、`medication_reminders`、`follow_up_tasks`。
- `knowledge.py`: `knowledge_documents`、`knowledge_chunks`。
- `agent_log.py`: `agent_memories`、`agent_runs`、`agent_tool_calls`。

Alembic 配置位于项目根目录 `alembic.ini` 和 `backend/alembic/`。`env.py` 导入 `Base.metadata` 和 `app.models`，支持基于 ORM metadata 生成迁移。

Seed 脚本位于 `scripts/seed.py`，通过查询后创建或更新的方式保证重复执行不会破坏基础数据。

医疗安全边界在模型层体现为：

- 方案类表只存储 `draft_content`、`plan_detail`、`suggestion`、`safety_note`、`doctor_confirmation_required` 等辅助字段。
- 关键动作表包含 `status`、`need_human_confirmation`、`confirmed_at`。
- 不包含 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 等字段。

## 6.2 第二阶段 2A.1 Langflow-like Trace / Observability 设计

阶段 2A.1 对齐 Agent Harness 所需的可观测字段，不实现业务 API、ToolRegistry 业务工具、Multi-Agent 编排或 LangGraph 工作流。

本阶段 trace 设计参考 Langflow 的 flow runtime 和 trace 思路，但保留互联网医院业务安全边界：

- `agent_runs.started_at`、`ended_at`、`duration_ms` 记录 run 级耗时。
- `agent_runs.step_count` 记录后续工作流步数，避免 Multi-Agent 循环不可控。
- `agent_runs.task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate` 为后续 Harness 评估指标预留字段；真实指标未跑出前只能写为设计目标或示例数据。
- `agent_tool_calls.agent_role` 标记调用来自 `Planner`、`ProfileAgent`、`RefillAgent`、`PharmacyAgent`、`ReminderAgent` 或 `SafetyAgent`。
- `agent_tool_calls.error_type` 和 `fallback_action` 用于区分参数错误、工具超时、数据不存在、未授权、服务不可用和人工确认兜底。
- `agent_tool_calls.schema_valid` 用于记录工具输入/输出 schema 校验结果。

后续 Agent Harness 会基于这些字段统计 `task_success`、`tool_call_accuracy`、`groundedness`、`schema_valid`、`hallucination_rate`、`safety_recall`、`human_confirmation_rate` 和 `p95_latency`。

## 6.3 第二阶段 2A.2 Context / Evaluator 设计

阶段 2A.2 只更新架构设计和文档，不修改 ORM、迁移、seed、业务 API、ToolRegistry、Agent 运行代码或前端。

Context 设计：

- `TaskContext Builder` 从原始对话提取 `task_id`、`member_id`、意图、已确认槽位和候选推断。
- `ContextEnvelope` 保存当前任务的结构化工作集和 Tool/RAG 引用，不保存完整聊天历史。
- `Role-specific Context View` 按职责投影最小字段、`allowed_tools`、`member_id` 和 source pointer。
- 每次 run 结束后生成 `RunSummary`，清理 scratchpad、未确认推断、无关历史和临时工具结果。
- 同一任务允许 compaction，但必须保留 `source_id`；不相关任务和成员切换必须 reset。
- 长期 memory 只接受用户确认后的提醒偏好、草稿状态和常用视图。

Evaluator 设计：

- `EvaluatorAgent` 在 FinalAnswer 后运行，只读 `RunTrace`、`ContextEnvelope`、`ToolEvidence`、`RAGSources`、`FinalAnswer` 和 `ExpectedCase`。
- 输出 `EvaluationResult`，包含任务成功、工具准确性、groundedness、schema、安全召回、确认、隔离、延迟和失败原因。
- EvaluatorAgent 不修改用户答案，不调用业务工具，不生成医疗建议，不写业务状态。
- 后续 AgentHarness 汇总多个结果生成 `agent_eval_report.md`。

详细设计见 `docs/CONTEXT_MANAGEMENT.md` 和 `docs/EVALUATOR_AGENT.md`。

## 6.4 阶段 2B-1 Pydantic 契约层

契约代码位于 `backend/app/agent/`：

- `context_schemas.py`: ContextEnvelope、TaskState、ToolEvidenceRef、RAGSourceRef、RoleSpecificContextView、RunSummary 及辅助模型。
- `eval_schemas.py`: ExpectedCase、ExpectedSource、EvaluationResult。

设计原则：

- 使用 Pydantic 2.x 和 `extra="forbid"`，禁止未声明状态进入上下文或评估结果。
- intent、action type、agent role、final status 和 case category 使用受限 Literal。
- 工具证据必须匹配当前 `run_id` / `member_id`；成员专属 RAG 与 memory 引用必须匹配当前成员。
- 长期 `memory_refs` 只接受用户确认内容。
- 分数限制在 `0..1`，不适用指标显式为 `null`。
- `failure_reasons` 为 EvaluationResult 必填字段，失败任务不能返回空失败原因。

固定用例位于 `backend/tests/fixtures/agent_harness_cases.json`，只描述预期，不执行工具或 Agent。

## 7. RAG 设计

第一版使用关键词检索，后续预留向量检索：

- `knowledge_documents`: 知识文档。
- `knowledge_chunks`: 分块内容。
- 输出必须标记来源，不允许模型凭空生成医疗建议。

## 8. 阶段实现边界

第一阶段只实现：

- 文档。
- 可启动 FastAPI。
- 可启动 Next.js。
- 后端分层目录。
- Tool Registry 和 FamilyHealthAgent 的轻量骨架。
- Docker、docker-compose、`.env.example`。

第二阶段 2A 已实现数据库模型、迁移和 seed。第二阶段 2A.1 已实现 Agent Harness / Trace 观测字段对齐。第二阶段 2A.2 已完成 Context Reset / Compaction、角色视图和 EvaluatorAgent 的架构设计。真实 API、工具执行、EvaluatorAgent、Agent Harness、Multi-Agent 编排和 LangGraph 节点仍在后续阶段实现。

## 9. 第二阶段 2A 验证记录

- `python -m pytest backend\tests -q`: 已通过，结果为 `8 passed`。
- `python scripts\seed.py`: 已在 SQLite 本地烟测库重复执行通过。
- `alembic upgrade head`: 当前本机未安装 Alembic，联网安装审批未返回，因此未在本机实际执行；项目已提供 Alembic 配置和初始迁移。

## 10. 第二阶段 2A.1 变更记录

- 新增迁移 `backend/alembic/versions/0002_add_agent_harness_trace_fields.py`，补充 `agent_runs` 和 `agent_tool_calls` 的 trace 字段，支持 `upgrade` / `downgrade`。
- 更新 `backend/app/models/agent_log.py`，为 `AgentRun` 和 `AgentToolCall` 增加 Harness 观测字段。
- 更新 `scripts/seed.py`，示例 run/tool call 包含角色、schema 校验、错误类型和 fallback 动作。
- 更新 `backend/tests/test_models.py`，覆盖新增字段、禁用字段、seed 幂等和迁移文件存在性。
- 更新 `AGENTS.md` 和 `docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`，记录 Multi-Agent 边界、ContextEnvelope、Tool Registry、幻觉控制和 Harness 验收口径。

运行方式：

```bash
python -m alembic upgrade head
python scripts/seed.py
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

下一步建议：进入基础 API 或工具层阶段时，再基于这些字段实现 ToolRegistry 调用记录和 Harness 评估报告，不在数据库对齐阶段提前实现复杂 Agent 工作流。

## 11. 第二阶段 2A.2 变更记录

- 新增 `docs/CONTEXT_MANAGEMENT.md`，定义 Context Lifecycle、Reset、Compaction、Role-specific Context View、RunSummary 和长期记忆写入门槛。
- 新增 `docs/EVALUATOR_AGENT.md`，定义 EvaluatorAgent 只读输入、ExpectedCase、EvaluationResult、Safety/Evaluator 边界和报告聚合口径。
- 更新 `AGENTS.md`、`README.md`、`family_health_agent_project_prompt.md`、Harness 计划、Agent 工作流、技术设计和简历说明。
- README 的“当前文件结构”已清理为项目树，不再包含代码审查文本。
- 本阶段没有数据库或运行时代码改动，不新增 Alembic migration，不修改 seed、后端模型或前端。

验证方式：

```powershell
rg -n "Context Reset|Context Compaction|EvaluatorAgent|EvaluationResult" AGENTS.md README.md family_health_agent_project_prompt.md docs
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

简历可表述为“设计了 Context Reset / Context Compaction / EvaluatorAgent / Agent Harness”。真实指标在评估用例和 `agent_eval_report.md` 跑通前只能标记为目标指标或评估维度。

下一阶段建议先落地 Context / Evaluation Pydantic 契约、ExpectedCase fixture 和确定性校验，再实现实际 post-run evaluator。

## 12. 阶段 2B-1 变更记录

- 实现 8 个目标 Pydantic schema 和必要辅助引用类型。
- 新增 16 条固定 ExpectedCase fixture。
- 新增契约测试，覆盖 schema、安全、memory、成员隔离和 fixture 分类。
- 同步 README、项目提示词和 Context/Evaluator/Harness/API/DB/简历文档。
- 未修改 ORM、Alembic、seed、API、ToolRegistry、LangGraph 或前端。

验证命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

下一阶段建议实现 deterministic ExpectedCase evaluator 与 fixture runner，并将真实结果输出为结构化 EvaluationResult；暂不接入模型评分。

## 13. 阶段 2B-2 Deterministic Harness

实现模块：

- `run_trace_schemas.py`: 冻结 run/tool/RAG/safety/final answer 快照。
- `evaluator.py`: 纯规则 ExpectedCase vs RunTrace 评估。
- `harness_runner.py`: fixture 加载、case 配对、指标聚合和 Markdown 渲染。
- `mock_run_traces.json`: 16 条冻结 mock run artifact。

聚合采用算术平均和 nearest-rank p95。`human_confirmation_rate` 只统计 ExpectedCase 要求确认的用例；`safety_recall_rate` 只聚合有 expected safety flags 的结果。高风险 safety case 缺任一预期 flag 时单例 recall 为 0。

本阶段不调用模型、数据库、API、ToolRegistry 或 LangGraph。示例报告仅证明 deterministic 规则能够识别注入错误。

## 14. 阶段 2B-3 ContextManager

`backend/app/agent/context_manager.py` 实现纯内存上下文管理器：

- `build_envelope`: 将用户输入摘要、任务元数据、证据引用和安全标记组装为 `ContextEnvelope`。
- `build_role_view`: 基于角色 allowlist 裁剪 `allowed_tools`、`visible_task_state`、`visible_tool_evidence_refs`、`visible_rag_source_refs` 和 `safety_flags`。
- `compact`: 合并同一 task/member 的上下文，保留 source pointer。
- `create_run_summary`: 将运行结果冻结为 `RunSummary`。
- `reset_after_run`: 清理临时 working context，返回只含审计引用的 reset state。

角色策略：

- Planner 不看工具证据。
- Profile / Refill / Pharmacy / Reminder 只看本角色证据。
- SafetyAgent 可看 safety RAG 和必要 evidence。
- EvaluatorAgent 被拒绝进入业务角色视图，只能读取 frozen run artifacts。

本阶段没有数据库、API、ToolRegistry、LangGraph 或 LLM 调用。

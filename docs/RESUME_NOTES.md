# Resume Notes

## 当前阶段

Phase 2B-2: deterministic Agent Harness runner, frozen RunTrace contracts, mock trace replay and aggregated evaluation report.

## 已完成

- 读取并理解项目提示词。
- 创建 `docs` 文档：
  - `PRD.md`
  - `TECH_DESIGN.md`
  - `API_SPEC.md`
  - `DB_SCHEMA.md`
  - `AGENT_WORKFLOW.md`
  - `RESUME_NOTES.md`
- 创建 `AGENTS.md` 协作说明。
- 创建后端 FastAPI 最小项目。
- 创建前端 Next.js App Router 最小项目。
- 创建 `docker-compose.yml` 和 `.env.example`。
- 创建 README 和简历表达章节。

## 验证状态

- Python 语法校验通过：`python -m compileall backend\app backend\tests`。
- 后端 TestClient 测试通过：`python -m pytest backend\tests -q`，结果为 `2 passed`。
- FastAPI 前台启动命令可运行：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。
- 前端依赖未安装：`npm install` 在当前沙箱内超时，联网权限审核未返回。
- Docker 未验证：当前环境未识别 `docker` 命令。

## 第二阶段 2A 已完成

- 新增 `backend/app/core/database.py`，提供 `Base`、`engine`、`SessionLocal`、`get_db`。
- 新增 18 张 SQLAlchemy ORM 模型。
- 新增根目录 `alembic.ini`、`backend/alembic/env.py`、`backend/alembic/versions/0001_initial_schema.py`。
- 新增 `scripts/seed.py` 和 `scripts/__init__.py`。
- 新增 `backend/tests/test_models.py` 和 `backend/tests/conftest.py`。
- 更新 README、AGENTS 和 docs。

## 第二阶段 2A 验证状态

- `python -m compileall backend\app backend\tests scripts`: 通过。
- `python -m pytest backend\tests -q`: 通过，结果为 `8 passed`。
- `python scripts\seed.py`: 使用 SQLite 本地烟测库重复执行通过。
- `alembic upgrade head`: 本机未安装 Alembic，且依赖安装联网审批未返回，未实际执行。

## 第二阶段 2A.1 已完成

- 合并 `hospital_AGENTS.md` 中的 Agent 项目规则到根目录 `AGENTS.md`，保留原工程分层、医疗安全和文档同步规则。
- 新增 `docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`，整理 Langflow-like trace / harness 落地计划。
- 为 `AgentRun` 设计并落地 trace 字段：`started_at`、`ended_at`、`duration_ms`、`step_count`、`task_success`、`groundedness_score`、`hallucination_flag`、`human_confirmation_rate`。
- 为 `AgentToolCall` 设计并落地 trace 字段：`agent_role`、`error_type`、`fallback_action`、`schema_valid`。
- 新增迁移 `0002_add_agent_harness_trace_fields.py`，支持 upgrade/downgrade，不改写 `0001_initial_schema`。
- 更新 seed 示例，包含成功工具调用和失败 fallback 工具调用。
- 更新测试，覆盖新增字段、禁用字段、seed 幂等和迁移文件存在性。

## 第二阶段 2A.1 简历表达边界

可以写：

- 设计并落地 Agent Harness 所需 trace 字段，覆盖 run 耗时、step 数、工具角色、schema 校验、错误类型和 fallback 动作。
- 规划 ContextEnvelope、Tool Registry 与 Harness 指标体系，为后续 Multi-Agent 可回放、可观测和可评估打基础。

不能写：

- 已达成 `groundedness 100%`、`safety_recall 100%`、`schema_valid 95%+`、`p95_latency` 等真实指标。
- 已实现 ToolRegistry 业务工具、Multi-Agent 编排、LangGraph 工作流或 Agent Harness 自动评估。

真实指标必须等后续 harness、mock tools、评估用例和 `agent_eval_report.md` 跑通后再补。

## 第二阶段 2A.2 已完成

- 设计完整 Context Lifecycle：`Raw Conversation -> TaskContext Builder -> ContextEnvelope -> Role-specific Context View -> Tool Evidence / RAG Sources -> Run Summary -> Context Reset -> EvaluatorAgent Review -> Long-term Memory Write`。
- 设计 Context Reset：run 结束后生成 RunSummary，清理临时 working context，保留工具证据、RAG source id、trace、FinalAnswer 和 eval 引用。
- 设计 Context Compaction：旧对话只进入结构化摘要，事实保留 `source_id`，多成员按 `member_id` 隔离。
- 新增独立 `EvaluatorAgent` 设计，明确其只在 FinalAnswer 后运行，只读 run 产物，不修改答案、不生成医疗建议、不写业务状态。
- 定义 `ExpectedCase`、`EvaluationResult` 和 `agent_eval_report.md` 聚合维度。
- 明确 `SafetyAgent` 负责运行时安全拦截，`EvaluatorAgent` 负责事后质量评估。
- 修复 README “当前文件结构”区域混入代码审查文本的问题。

## 第二阶段 2A.2 简历表达边界

可以写：

- 设计 Context Reset / Context Compaction，通过任务级摘要、source pointer 和 member isolation 控制 Multi-Agent 上下文污染。
- 设计独立 post-run EvaluatorAgent 与 Agent Harness，覆盖任务成功、工具准确性、groundedness、schema、安全召回、人工确认、上下文隔离和延迟等评估维度。
- 区分运行时 SafetyAgent 与事后 EvaluatorAgent，形成“执行前拦截 + 执行后评估”的安全质量架构。

不能写：

- 已实现或上线 EvaluatorAgent、AgentHarness、16 条自动评估用例或 `agent_eval_report.md` 生成器。
- 已达到 100% safety recall、0 hallucination、100% groundedness 或任何 p95 latency 数值。
- 已通过真实线上医疗安全效果验证。

本阶段所有指标仍是“评估维度 / 目标指标”，不是实测结果。

## 第二阶段 2A.2 修改与验证

修改文件：`AGENTS.md`、`README.md`、`family_health_agent_project_prompt.md`、`docs/CONTEXT_MANAGEMENT.md`、`docs/EVALUATOR_AGENT.md`、`docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`、`docs/AGENT_WORKFLOW.md`、`docs/TECH_DESIGN.md`、`docs/RESUME_NOTES.md`。

文档检查命令：

```powershell
rg -n "Context Reset|Context Compaction|EvaluatorAgent|EvaluationResult" AGENTS.md README.md family_health_agent_project_prompt.md docs
```

现有后端回归命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

本阶段未新增运行时代码，因此没有真实 evaluator 指标报告。

## 关键约束

- 系统不是 AI 医生。
- 不诊断、不自动开方、不修改医生处方。
- 关键动作必须经过人工确认。
- 工具调用必须纳入 `agent_tool_calls`。
- MVP 只聚焦四个场景。

## 下一步

该最小契约阶段已在 2B-1 完成。后续优先实现 deterministic fixture runner 和 EvaluationResult 计算，再接入真实 AgentHarness。

## 阶段 2B-1 已完成

- 实现 ContextEnvelope、TaskState、ToolEvidenceRef、RAGSourceRef、RunSummary 和 RoleSpecificContextView。
- 实现 ExpectedCase、ExpectedSource 和 EvaluationResult。
- 使用 Pydantic 2.x 严格枚举、额外字段拒绝、run/member 隔离和用户确认 memory 校验。
- 准备 16 条固定 fixture，覆盖 3 续方、3 复诊材料、3 提醒、4 高风险和 3 异常/隔离/无来源场景。
- 新增测试，验证非法 intent/role、raw conversation 拒绝、fixture 加载、failure reasons、安全 flag 和成员隔离。

可以写：

- 设计并实现 Agent Harness Pydantic 契约层，将 Context Reset、角色最小视图、证据引用和 post-run 评估输入输出固化为强类型 DTO。
- 构建 16 条医疗业务固定评估用例，覆盖正常流程、高风险拦截、工具异常、无来源回答和跨成员串扰。

不能写：

- 已实现真实 EvaluatorAgent、自动指标计算、模型评分或 `agent_eval_report.md`。
- 已达到任何 safety recall、hallucination rate、groundedness 或 p95 latency 数值。

下一步：实现 deterministic fixture runner 和 EvaluationResult 计算规则，再评估是否需要模型辅助评分。

## 阶段 2B-2 已完成

- 实现冻结 `RunTrace`、`ToolCallTrace`、`FinalAnswerTrace`、`SafetyTrace` 和 `RAGTrace`。
- 实现不调用模型的 `DeterministicEvaluator`，按 ExpectedCase 检查 intent、member、工具、来源、安全、确认、schema 和隔离。
- 实现 `HarnessRunner`，加载 16 对 case/trace，生成 EvaluationResult、聚合指标和 Markdown 报告。
- mock traces 同时覆盖成功路径和 6 类故意失败：缺工具、缺安全标记、禁用短语、跨成员串扰、无来源硬答、缺人工确认。
- 示例报告中的指标是固定 mock fixture 的计算结果，不是线上、生产或临床指标。

可以写：

- 设计并实现 deterministic Agent Harness runner，通过冻结 RunTrace 与固定 ExpectedCase 对 Agent 输出进行可重复、可解释的规则评估。
- 构建工具覆盖率、groundedness、安全召回、人工确认、上下文隔离与 p95 延迟聚合，并生成 Markdown 评估报告。

不能写：

- 已实现 LLM-as-a-Judge、真实在线 EvaluatorAgent 或临床安全评估。
- mock fixture 报告中的数值代表生产环境效果。
- 已达到 100% safety recall、0 hallucination 或任何线上 p95 指标。

下一步：接入脱敏真实 RunTrace adapter、数据集版本号和 JSON/Markdown 双格式报告，再考虑对解释性质量使用可选 LLM evaluator。

## 阶段 2B-3 已完成

- 实现 `ContextManager`，支持 `build_envelope`、`build_role_view`、`compact`、`create_run_summary` 和 `reset_after_run`。
- 实现 role-specific context view 裁剪：Planner 不看工具证据，业务 Agent 只看自身证据，SafetyAgent 看安全相关引用，EvaluatorAgent 不能获取业务上下文。
- compact 保留 `source_id`、`tool_call_id` 和 `member_id`。
- reset_after_run 生成 RunSummary，保留 ToolEvidence refs、RAG refs、FinalAnswer ref 和 EvaluationResult ref，清理候选推断和 working context。
- 新增测试覆盖成员隔离、raw conversation 隔离、工具裁剪、compact、reset 和 invalid role。

可以写：

- 实现 ContextManager 的 role-specific context view、Context Reset 和 Context Compaction 纯内存逻辑，控制 Multi-Agent 上下文污染。

不能写：

- 已实现数据库持久化上下文、LangGraph 真实编排、ToolRegistry 业务调用或长期记忆写入。

下一步：实现脱敏真实 run artifact 到 ContextEnvelope / RunTrace 的 adapter，并考虑将 reset state 持久化为审计报告。

## 阶段 2C-1 已完成

- 实现 Tool Registry 契约层：`ToolSpec`、`ToolExecutionContext`、`ToolResult`、`RetryPolicy` 和 `ToolPermissionScope`。
- 实现 6 个 deterministic mock 工具。
- `ToolRegistry.call` 统一处理工具存在性、角色权限、schema 校验、人工确认门和失败 fallback。
- `ToolResult` 可映射为 `ToolCallTrace` 所需字段。

可以写：

- 设计并实现 Tool Registry 契约层，通过 ToolSpec / ToolExecutionContext / ToolResult 统一工具权限、schema 校验、人工确认和 trace 映射。

不能写：

- 已实现真实数据库查询工具、真实药店库存查询、真实复诊/购药/提醒提交。

## 阶段 2C-2 已完成

- 实现 mock Agent Harness Runtime，可串联 ContextManager、ToolRegistry、RunTrace 和 DeterministicEvaluator。
- 支持单条 `run_case` 和批量 `run_all`，可回放 16 条固定 ExpectedCase fixture。
- Runtime 通过 `ToolRegistry.call` 调用 mock tools，不直接调用 mock handler。
- Runtime 从 `ToolResult` 构造 `ToolCallTrace`，并生成 `RAGTrace`、`SafetyTrace`、mock `FinalAnswerTrace` 和 `EvaluationResult`。
- 新增测试覆盖正常续方、高风险安全、权限失败、缺工具失败、人工确认、成员隔离、trace 来源和无外部依赖。

可以写：

- 实现 mock Agent Harness Runtime，可回放 fixture 并生成 EvaluationResult，用于验证上下文、工具调用、trace 和评估链路。

不能写：

- 已接入真实业务数据库。
- 已实现线上 Agent 评估。
- mock runtime 指标代表真实 safety recall、hallucination rate、groundedness 或 p95 latency。
- 已实现 LangGraph 真实业务编排或在线 EvaluatorAgent。

下一步：实现 ToolResult / RunTrace 到持久化审计记录的 adapter，并为 mock runtime 增加 JSON/Markdown 双格式报告输出。

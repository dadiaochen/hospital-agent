# 5A 业务闭环与分层评测差距审计

## 结论

本轮采用增量补齐，不重构既有确定性 Router、一次性 Planner、bounded Supervisor、三个领域 Agent、固定安全治理和 post-run Agent 评测边界。基线已由本地分支 `codex/backup-before-5a-business-closure-20260810` 固定；该分支只指向实施开始前的 HEAD，不包含本轮变更。

## 已复用能力

| 能力 | 已有实现 | 本轮复用方式 |
| --- | --- | --- |
| 正式业务入口 | `UnifiedHealthGraph` → `SupervisorBusinessWorkflow` | 在图入口增加前置 Scope Guard，不改 Supervisor 职责 |
| Agent 编排 | 确定性 Router、一次性 Planner、bounded Supervisor、Triage/Medication/Report | Scope 允许后维持原有执行路径 |
| 医疗安全 | Request / Action / Final Output 三层固定治理 | Scope Guard 只判断产品范围，不合并或替换 Agent 安全 |
| 状态恢复 | PostgreSQL 权威 Checkpoint、Redis TTL 缓存回源 | Scope 终止态也沿用既有冻结与 checkpoint 持久化 |
| RAG | FastEmbed、pgvector HNSW、关键词、RRF、版本过滤、来源引用 | Task 2 在现有 Retriever 和 synthetic Gold 上补齐分层指标 |
| 评测 | RunTrace、FinalClaim、确定性 Evaluator、synthetic RAG 脚本 | Task 2–3 只在离线 Harness 追加 RAGAS 适配和三类评测视图 |
| 报告 | `parse_medical_document`、健康记录草稿、确认状态机、报告读取 API | 已补统一 Parser 与上传后的直接结构化读取；上传报告不再走健康记录草稿 |

## 本轮确实缺口与顺序

| Task | 状态 | 缺口 |
| --- | --- | --- |
| 0：审计与基线 | DONE | 已完成代码审计、基线分支和执行边界冻结 |
| 1：RequestScopeGuard | DONE | 已完成前置范围判断、零下游调用终止和 Trace 观察点 |
| 2：RAG 分层评测 | DONE | 已完成 nDCG、检索 bad case 归因和可选 RAGAS Adapter；全量 RAGAS 批量结果转换异常记录在统一指标文档，不阻断确定性评测 |
| 3：Synthetic → Harness | DONE | 125/500 冻结数据已经生成 Entry / Retrieval / Answer 三视图并统一驱动 Harness |
| 4：Triage 多轮槽位 | DONE | 已完成最小槽位状态机、PostgreSQL Checkpoint 和新 run 安全续跑 |
| 5：DocumentParserService | IN PROGRESS | 按唯一路线图进入统一文档解析 |
| 6：报告结构化读取 | DONE | 上传、文本/表格/PDF/OCR 解析、持久化与成员隔离读取已完成；不创建报告确认草稿 |
| 7：FinalAnswerQualityGate | PLANNED | 需要在冻结前增加一次受限质量修复，不重跑业务链路 |
| 8：Context / Checkpoint 收口 | PLANNED | 需要核对所有新增状态只落既有 PostgreSQL Checkpoint |
| 9：E2E 与冻结 | PLANNED | 需要在前述任务完成后做分层报告和端到端回归 |

## Task 1 实施结论

`RequestScopeGuard` 位于 `UnifiedHealthGraph` 的第一节点。高置信度天气、编程、股票、旅游、娱乐和非医疗写作请求直接终止；模糊输入返回澄清；出现健康信号或混合健康意图时保守放行。拒绝与澄清都不会调用 Router、Planner、Supervisor、领域 Agent、RAG、Tool、Provider 或 Model Gateway。

决策以 `ScopeDecision` 保存：`action`、`reason_code`、`confidence`、`latency_ms`。冻结 `RunTrace` 额外记录 `scope_guard` 观察事件；该事件不保存原始输入。Scope Guard 不是医疗诊断或用药安全判断，医疗风险仍交由原有三层 Agent 安全处理。

## 计划修改范围

- Task 2–3：`backend/app/rag/`、离线 Harness、synthetic RAG 脚本、对应测试和 RAG/评测文档。
- Task 4：Triage 运行时 Agent、Checkpoint schema/service、业务任务 API 测试。
- Task 5–6：Parser service、报告 schema/service/API、成员隔离测试。
- Task 7：最终答案生成前的独立质量 Gate；不修改 Router、Planner、业务 Tool 或 Evaluator 的只读边界。

## Task 2–3 完成记录

- Task 2 已完成：`RagasEvaluationAdapter` 固定适配 `ragas==0.2.9`，只读取已经冻结的用户问题、模型回答、检索文本和答案 Gold。无配置、缺少依赖、Judge 异常、超时或返回格式异常时，逐条记录 `skipped/failed`，不影响主链路、bad case、退出状态或任何业务状态。
- Task 3 已完成：`SyntheticCaseHarnessAdapter` 从同一份冻结 125 个基础 Case / 500 条 Query 投影 `EntryHarnessView`、`RetrievalHarnessView`、`AnswerHarnessView`。三个视图保留 `query_id`、`base_case_id`、split 和冻结 Gold 来源，避免由本次 Agent 输出反向制造标签。
- 本地已安装 `ragas==0.2.9` 并配置独立 Judge；已修复单条格式异常拖垮整批的问题，并直接复用冻结记录完成 320 条离线复评：300 条三项齐全、20 条部分评分。剩余 N/A 来自 Judge 超时/格式异常及补跑时账户余额不足，不与既有确定性指标混写。统一状态见 [RAG 合成评测统一报告](../RAG_SYNTHETIC_EVALUATION_DATASET.md)。

## Task 4 完成记录

- Triage 缺少 `symptoms` 时冻结 `missing_slots`、`confirmed_slots` 与澄清轮次，不执行科室、号源或草稿工具。
- 新的 `/clarify` 续跑必须匹配任务幂等键、当前 Checkpoint 版本、用户和成员范围；服务以新 `AgentRun` 和 `parent_run_id` 从 PostgreSQL 权威 Checkpoint 恢复，不复用旧 scratchpad。

## 已知限制

- 合成 RAG 数据集和运行产物位于被 Git 忽略的 `output/benchmarks/rag_synthetic/`，不进入仓库。
- RAGAS 仅能作为离线可选评测适配器；不可用、超时或解析失败不能影响业务回答。
- 当前有既存 `.pytest-supervisor-elevated/` 权限问题导致 Git 显示历史测试产物删除；本轮不处理、不提交这些文件。

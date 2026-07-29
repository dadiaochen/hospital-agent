# 4B 任务十交付报告：RAG、成员隔离与可观测性

## 1. 范围

本任务只补强现有 hybrid RAG、成员资源读取、Redis checkpoint 防污染和冻结 RunTrace。没有新增 ORM/Alembic、业务 API、外部 Provider、OpenTelemetry/Jaeger、LLM Judge 或 32 条 Harness。

## 2. RAG

- Hybrid 排序改为 RRF，公式为 `sum(1 / (60 + rank))`。
- 保留 `keyword_score/vector_score`、`keyword_rank/vector_rank` 和 `rrf_score`；原始分数不跨量纲比较。
- `VectorMatch` 携带 document version、chunk version 和 embedding schema；hydration 必须与 PostgreSQL 当前记录一致。
- 全部向量来源过期时降级关键词并记录 `vector_source_version_mismatch`；部分过期时忽略旧来源并记录 `stale_vector_sources_ignored`。
- SourceRef metadata 保存 rank、RRF、版本、embedding schema 和 fallback reason，正文仍从权威知识表回填。

## 3. 成员隔离

- 档案、处方、购药记录和药箱查询在同一 SQL 中约束用户、成员和资源归属。
- Tool execution context 仍做第一层 user/member 校验，Pydantic `extra=forbid` 拒绝 Prompt/身份附加字段。
- Redis payload 即使留在预期 key，只要 user/member/task/thread/version 不一致就按 miss 处理。
- 攻击回归覆盖另一用户旧成员/处方 ID、伪造执行成员、Prompt 注入和跨成员缓存残留；失败不产生来源。

## 4. Observation

`ObservationTrace` 为 frozen、`extra=forbid` 契约，覆盖 request/task/run/member、node、Tool、Provider、latency、retry、fallback、source、model 和 Provider 返回的 token usage。服务端不估造 token 数。

以下内容不进入 Observation：user input、input payload、Tool 输入输出、Provider 请求响应、模型 messages/raw response、RAG 正文、FinalAnswer 正文、API Key、Authorization、Cookie 和访问凭据。Observation 只记录被删去的字段名，不能用于恢复业务内容，也不能修改业务状态。

## 5. 修改文件

- RAG：`backend/app/rag/retrieval_schemas.py`、`retriever.py`、`vector_backend.py`、`vector_store.py`。
- Trace/模型：`backend/app/agent/run_trace_schemas.py`、`observability.py`、`product_artifacts.py`、`product_workflow.py`、`model_gateway.py`、`model_gateway_schemas.py`、`runtime_trace_adapter.py`。
- 隔离：`backend/app/services/agent_tool_query_service.py`、`backend/app/tools/db_tools.py`、`backend/app/tools/business_tools.py`。
- 测试：hybrid/vector RAG、DB Tool、cache、Model Gateway、business API 与 `test_task10_observability.py`。
- 文档：README、路线图及 Agent/RAG/API/DB/Tool/Safety/Context/Evaluator/测试/简历相关文档。

## 6. 验证结果

2026-07-29 在本地 `.venv` 执行：

- 任务十定向回归：`84 passed`。
- 后端全量回归：`287 passed`，4 个已知 warning。
- `compileall` 使用 `output/pycache-task10` 独立缓存通过；仓库旧 `__pycache__` 和 `.pytest_cache` 存在 Windows ACL warning，不影响测试结论。

这些结果只证明本地代码契约和攻击式回归通过，不代表真实 FastEmbed 召回率、线上 p95、零泄漏、临床安全或生产可用性。

## 7. 未实现

- 本报告生成时尚未实现的任务十一 32 条 Harness 与消融，现已在 [任务十一报告](agent_ablation_report.4b.md) 完成。
- 真实 FastEmbed + PostgreSQL pgvector Recall@K/引用正确率评测。
- 真实 Provider/LLM token、成本、延迟和稳定性报告。
- OpenTelemetry/Jaeger、生产日志平台和外部医疗系统接入。

本报告完成时的下一项是任务十一；当前唯一下一项只以总路线图为准。

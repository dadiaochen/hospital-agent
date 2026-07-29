# 4B 任务十二：PostgreSQL/Redis/Docker 后端验收报告

## 范围

本报告记录 2026-07-29 在本机 Docker Compose 开发环境中的后端验收。栈包含 PostgreSQL/pgvector、Redis、FastAPI 和 Next.js；验收脚本是 `scripts/task12_acceptance.py`。脚本不调用 LLM、不访问真实医院或药店 Provider，也不执行外部写操作。

## 结果

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| baseline | 19/19 checks passed | migration、seed、pgvector、三条业务 API、知识检索、422 映射、并发确认和前端 health |
| Redis 故障 | 18/18 checks passed | Redis 连接失败被检测，业务任务从 PostgreSQL 恢复 checkpoint |
| 并发确认 | 通过 | 4 个相同请求中 1 个真实执行，3 个返回状态冲突，执行记录为 1 |
| RAG 数据 | 通过 | `knowledge_chunks` 中 4 个向量，维度 512，与配置一致 |
| 迁移 | 通过 | Alembic head 为 `0007_task_checkpoint_state` |

## Wall-clock 记录

- baseline：13 个 HTTP 样本，p95 为 `426.67 ms`。
- Redis 故障：10 个 HTTP 样本，p95 为 `9407.17 ms`。

Redis 故障场景的 p95 包含连接失败等待和重试开销，只是本机故障回归记录，不是生产 SLO、容量压测结果或可对外承诺的延迟指标。

## 运行方式

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
docker compose up -d --build --wait --wait-timeout 300
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

Redis 故障回归需要临时停止 Redis，执行 `--mode redis-failure --require-vector --skip-index`，完成后立即 `docker compose start redis`。建议在本地终端操作，避免把 Redis 停止状态留给下一次开发。

## 限制

- deterministic embedding 只证明索引、维度和数据链路可用，不证明 FastEmbed 语义质量或 Recall@K。
- 本报告不证明真实模型回答质量、医疗安全召回率、用户采纳率、生产高可用或真实外部 Provider 成功率。
- 任务十三仍需复核文档、完整测试和 Git 回滚点；4B 在任务十三完成前不标记为最终完成。

# 4B PostgreSQL 迁移验证报告

## 验证范围

本报告记录 2026-07-26 在本机 Docker Desktop 上对当前提交 `e73a616` 的一次真实开发环境验证。验证目标是确认 PostgreSQL、pgvector、Alembic、seed 和 FastAPI 能够协同启动；这不是生产部署、临床验证或模型质量评测报告。

## 执行命令

```powershell
docker compose up -d --wait --wait-timeout 180 postgres redis

$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py

docker compose up -d --build --wait --wait-timeout 300 backend
docker compose ps
```

## 结果

- PostgreSQL 和 Redis healthcheck 通过。
- Alembic 从 `0003_lightweight_vector_rag` 升级到 `0004_business_task_runtime`，再升级到 `0005_knowledge_metadata`。
- PostgreSQL `alembic_version` 为 `0005_knowledge_metadata`，只有一个 head。
- PostgreSQL 已启用 `vector` 扩展。
- `knowledge_chunks` 存在 `embedding`、`embedding_model`、`embedding_content_hash`、`embedded_at` 和 `chunk_version`，没有重复列。
- 业务 runtime 表 `business_tasks`、`provider_calls`、`source_references`、`medical_documents` 和 `health_record_events` 均已创建。
- 幂等 seed 成功，测试数据包含 1 个用户、3 个家庭成员和 4 篇知识文档。
- backend 容器启动时自动执行 migration 和 seed，并显示 `healthy`。
- `GET /health` 返回 `{"status":"ok"}`。
- `GET /api/knowledge/search?q=确认&category=human_confirmation` 成功返回 1 条结果。

## 边界与清理

> 历史记录说明：本报告记录的是 `0006_vector_search_index` 引入前的 `0005_knowledge_metadata` 验证时点。当前迁移 head 已继续串联到 `0007_task_checkpoint_state`；本报告只证明当时的 PostgreSQL/Docker migration 快照，不能替代任务八的 checkpoint/cache 专项回归或后续真实 Docker 验收。

本次没有启动 frontend，也没有调用真实医院、药店、通知服务、LLM 或真实 Embedding 下载；使用的是 deterministic provider 和已存在的本地 PostgreSQL seed。停止服务使用：

```powershell
docker compose down
```

不要使用 `docker compose down -v`，否则会删除本地 PostgreSQL/Redis volume。该报告只证明本地开发链路可复现，不代表生产可用性或医疗安全指标达标。

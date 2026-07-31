# 4B 任务八：分层状态与两次 run 续跑交付报告

## 1. 状态

`DONE`。本报告完成时的下一项是 4B 任务九“Tool 与三类 Provider 可靠性”；当前阶段顺序以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为准。

## 2. 任务拆分

1. 把任务进度、确认记录和已确认偏好从运行时 JSON 投影提升为 PostgreSQL 权威数据。
2. 为 checkpoint 建立带 user/member/task/thread/version 作用域的 Redis 短期缓存，并验证 miss、过期和不可用回源。
3. 让首次 run 与 confirmation continuation run 使用同一 `task_id`、不同 `run_id`，只恢复最小结构化进度，不恢复 scratchpad 或未确认推断。
4. 用 checkpoint version、confirmation version、幂等键和来源版本阻断陈旧确认及未确认偏好写入。

## 3. 完成内容

- Alembic `0007_task_checkpoint_state` 新增 `task_checkpoints`、`task_confirmation_records`、`confirmed_preferences`，并为 `business_tasks` 增加当前版本字段、为 `agent_runs` 增加 `parent_run_id`。
- `TaskCheckpointService` 在事务内保存不可变 checkpoint，包含 RunSummary、步骤进度、确认状态、冻结产物和来源指针；Redis 只保存 allow-listed 短期投影。
- `TaskCheckpointCache` 的 key 固定包含 `user_id`、`member_id`、`task_id`、`thread_id` 和 `checkpoint_version`，缓存校验失败即视为 miss 并回源 PostgreSQL。
- continuation run 从 PostgreSQL/Redis checkpoint 投影最小恢复状态，重新读取可变业务事实；旧 run 的 raw conversation、scratchpad、候选推断和 provider 原始响应不会进入新 working state。
- `/api/business-tasks/{task_id}/confirm` 支持 checkpoint/confirmation version 乐观并发控制，并记录 `parent_run_id` 与确认状态转换。
- `/api/preferences` 只接受同 task 的已执行人工确认、匹配成员和 `SourceReference` 版本的可撤销偏好；处方、报告、库存、过敏史和症状不会进入偏好。

## 4. 修改文件

主要代码与测试：

- `backend/app/models/checkpoint.py`
- `backend/app/models/business_task.py`
- `backend/app/models/agent_log.py`
- `backend/app/schemas/checkpoint.py`
- `backend/app/schemas/business_task.py`
- `backend/app/services/checkpoint_service.py`
- `backend/app/services/task_checkpoint_cache.py`
- `backend/app/services/preference_service.py`
- `backend/app/services/business_task_service.py`
- `backend/app/api/routes/preferences.py`
- `backend/app/api/routes/business_tasks.py`
- `backend/app/api/router.py`
- `backend/app/core/config.py`
- `backend/alembic/versions/0007_task_checkpoint_state.py`
- `scripts/seed.py`
- `backend/tests/test_business_task_api.py`
- `backend/tests/test_task_checkpoint_cache.py`
- `backend/tests/test_migration_chain.py`

同步文档：

- `README.md`
- `docs/DEVELOPMENT_ROADMAP.md`
- `docs/TECH_DESIGN.md`
- `docs/API_SPEC.md`
- `docs/DB_SCHEMA.md`
- `docs/CONTEXT_MANAGEMENT.md`
- `docs/BUSINESS_WORKFLOWS.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/TOOL_CONTRACTS.md`
- `docs/SAFETY_POLICY.md`
- `docs/EVALUATOR_AGENT.md`
- `docs/RAG_RETRIEVAL.md`
- `docs/TESTING_GUIDE.md`
- `docs/RESUME_NOTES.md`

## 5. 运行与测试

正常开发环境：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
python -m pytest backend\tests\test_business_task_api.py backend\tests\test_task_checkpoint_cache.py -q -p no:cacheprovider --basetemp=var\pytest\4b-task8
```

本次离线回归在当前环境通过一次性测试 shim 提供 `pgvector.sqlalchemy.Vector`，不修改仓库依赖或生产代码。任务八专项测试结果为 `12 passed`；完整 backend 回归此前结果为 `266 passed`。最新完整回归有 5 个既有 `tmp_path` fixture 因 Windows `--basetemp` 目录权限在 setup 阶段失败，已完成的 261 条测试均通过；这不是业务断言失败。

## 6. 风险与未完成项

- 当前环境未安装 `pgvector` Python 包，直接运行 pytest 会在 collection 阶段失败；应在完整开发环境按依赖清单安装后再做无 shim 回归。
- Redis/PostgreSQL Docker wall-clock、真实并发回归和迁移后运行链路已在任务十二验收；真实 Provider 联调仍未完成，不在任务八报告中宣称完成。详见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。
- 本报告生成时，任务九 Tool/Provider、任务十 RRF/攻击式隔离和任务十一 32 条 Harness 均尚未实现；后续完成状态以总路线图为准。
- `EXECUTED` 仍只表示本地状态迁移成功，外部医院、药店、支付和通知系统状态固定为 `not_submitted`。

## 7. 简历亮点与下一步

简历/面试可以准确表述为：设计并实现 PostgreSQL 权威 Task Checkpoint 与 Redis TTL 短期缓存回源，使用同一 task 下的双 run 续跑、parent run 追踪和 confirmation version 乐观并发控制；确认后偏好写入绑定成员、来源版本和显式人工确认，避免将模型推断写入长期状态。

下一步唯一任务是 4B 任务九：统一 Tool 与三类 Provider 的错误分类、有限重试、降级和来源审计。

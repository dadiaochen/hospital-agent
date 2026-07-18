# 测试与代码审查指南

测试的目标不是只把绿灯跑出来，而是证明关键边界不会被后续改动悄悄绕开：成员隔离、来源约束、人工确认、schema 契约与医疗安全。

## 测试分层

| 层级 | 目录或模块 | 重点 |
| --- | --- | --- |
| 模型 | `test_models.py` | 表、关系、禁用字段、seed 可重复性。 |
| 契约 | `test_agent_contract_schemas.py` | Pydantic 字段、枚举、extra forbid、memory 门槛。 |
| 上下文 | `test_context_manager.py` | 角色视图、成员隔离、压缩和 reset。 |
| 工具 | `test_tool_registry.py`、`test_mock_tools.py`、`test_db_backed_tools.py` | 权限、schema、evidence、只读和失败 fallback。 |
| 草稿写入 | `test_confirmation_draft_tool.py` | 确认门禁、幂等、事务回滚、只写本地 draft。 |
| 草稿 API 状态机 | `test_confirmation_draft_api.py` | 显式确认、四类草稿、成员隔离、幂等确认/拒绝、非法终态转换和 OpenAPI。 |
| Harness | `test_deterministic_evaluator.py`、`test_harness_runner.py`、`test_harness_runtime.py` | 固定用例回放、评估规则和汇总报告。 |
| RAG | `test_hybrid_rag.py` | 固定安全/SOP 召回、来源版本、向量回填、去重和失败降级。 |
| API | `test_health.py`、`test_read_api.py`、`test_confirmation_draft_api.py` | 健康检查、只读资源和本地草稿状态机。 |

## 运行命令

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

只验证某个改动时，先跑对应测试文件；准备提交前再跑完整套件。Harness 的 fixture 位于 `backend/tests/fixtures/`，它们是 deterministic 演示输入，不是临床数据或线上评估数据。

## 如何 review 一个改动

按这个顺序读 diff，通常最省力：

1. **范围**：它是否只实现路线图当前阶段？是否偷带下一阶段 API、图工作流或前端功能？
2. **契约**：新增输入输出是否由 Pydantic 描述？`extra="forbid"`、字段约束和失败信息是否足够明确？
3. **隔离**：是否从 execution context 而不是请求体信任 `user_id` / `member_id`？跨成员数据会不会混入？
4. **安全**：草稿是否仍需确认？有没有医疗建议越过“信息整理与流程辅助”的边界？
5. **可追踪性**：工具调用是否能产生 run、role、输入、输出、延迟、schema 和 fallback 记录？
6. **失败路径**：没有数据、权限不足、schema 失败、数据库失败时，是否返回可解释的 fallback，而不是模型猜测？
7. **测试与文档**：新增规则是否有一个正例、一个失败例和同步说明？

Review RAG 时还要区分相关性与事实正确性：`score` 只能用于排序；正文必须来自可回溯的数据库 chunk，向量后端返回的未知或错配 ID 不能被 Agent 使用。

## 当前常见风险

- 真实 Agent API、LangGraph、多模型调用和外部医院/药店集成尚未实现，不能用 mock 成功结果替代真实验证。
- `agent_eval_report.example.md` 是固定 mock fixture 的计算结果，不是生产质量、临床效果或安全率证明。
- 本项目的配置示例只用于本地开发。生产环境必须从安全的环境变量或秘密管理系统注入连接信息和模型 Key。

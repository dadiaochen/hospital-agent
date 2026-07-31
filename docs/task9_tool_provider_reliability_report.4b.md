# 4B 任务九：Tool 与三类 Provider 可靠性交付报告

## 1. 完成范围

本任务实现统一错误分类、Tool/Provider 有限重试、逐次 attempt trace，以及三类重点 Provider 的强 schema 与来源边界。实现不调用 LLM，不新增数据库表，不执行医院挂号、问诊提交、药店下单或通知推送。

重点 Provider：

1. `MedicalDocumentParserProvider`
2. `PharmacyProvider`
3. `HospitalOrConsultationProvider`

## 2. 可靠性规则

统一 `error_category` 为 validation、permission、not_found、timeout、rate_limit、provider_unavailable、business_conflict、schema、internal。

- 输入、权限、成员作用域、schema、业务冲突和内部错误不重试。
- timeout、rate-limit、临时 provider-unavailable 只允许只读操作按固定 `max_attempts` 重试。
- 写工具即使报告可恢复错误也只执行一次，避免重复副作用。
- 每次实际执行记录 attempt number、success、latency、error category 和 retryable。
- 重试耗尽后的最终结果不可继续自动重试，必须显式降级或人工处理。

## 3. Provider 边界

- 文档解析保留 `document_id`、`document_version`、parser version、section id 和字符区间，不输出诊断。
- 药房只返回库存/履约候选，`order_created=false`。
- 医院只返回科室/时段候选，`appointment_created=false`；在线问诊只生成草稿，`submitted=false`。
- mock 来源标记 `simulation=true`、`verified=false`。
- sandbox/real 未配置、超时耗尽、schema 非法或业务冲突时不返回 data/source，不伪造外部成功。

## 4. 审计与持久化

Provider 的 attempts、error、fallback、latency 和 SourceRef 进入业务响应与 `provider_calls.response_payload`。ToolResult 同时记录工具级 attempts 和统一错误分类。现有表足以保存 JSON 审计，本任务未修改 ORM、Alembic 或 seed。

## 5. 测试

定向命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_provider_adapters.py backend\tests\test_provider_reliability.py backend\tests\test_tool_registry.py backend\tests\test_business_task_api.py -q -p no:cacheprovider --basetemp=output\pytest-task9
```

定向结果：`47 passed`。覆盖 timeout、rate-limit、provider unavailable、schema、business conflict、身份/成员来源错配、只读有限重试、写操作不重试、三类 mock/source 和 API 降级审计。

全量后端结果：`278 passed, 4 warnings`。warning 来自 Starlette TestClient、LangGraph serializer 待弃用提示和 Alembic `path_separator` 配置提示；没有测试失败。

本结果是离线 deterministic/mock 契约验证，不代表真实医院/药店 SLA、线上延迟或临床质量。

## 6. 下一步

本报告完成时的下一任务是 4B 任务十；当前唯一下一项只以总路线图为准。

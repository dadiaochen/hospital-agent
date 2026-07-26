# Tool Registry 与 Provider 契约

## 1. ToolSpec

每个工具必须声明：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `permission_scope`
- `timeout`
- `retry_policy`
- `requires_human_confirmation`
- `tool_version`

`tool_version` 用于回放和评测时确认具体工具契约，默认值为 `v1`。

## 2. ToolExecutionContext

工具执行上下文至少包含：

- `run_id`
- `user_id`
- `member_id`
- `agent_role`
- `permission_scopes`
- `human_confirmation_granted`
- `provider_mode`

`provider_mode` 只能是 `mock`、`sandbox` 或 `real`。生产运行模式不能由 Prompt 或普通 API 入参覆盖。

## 3. ToolResult

统一结果至少包含：

- `success`
- `data`
- `error`
- `latency_ms`
- `schema_valid`
- `tool_version`
- `provider_mode`
- `evidence_refs`
- `retryable`

`evidence_refs` 使用通用 `SourceRef`。调用失败必须返回结构化错误，不得把 Provider 原始异常文本直接交给模型生成用户答案。

知识检索工具的 `SourceRef.source_metadata` 还记录 `matched_by`、`retrieval_provider`、`fallback_used`、`fallback_reason`、embedding model/dimension/schema version。这样关键词降级仍然可审计，模型不能把降级结果伪装成真实语义召回。

## 4. 当前六类工具

- `query_health_profile`
- `query_prescriptions`
- `query_medicine_box`
- `check_pharmacy_inventory`
- `search_safety_knowledge`
- `create_confirmation_draft`

这些工具继续支撑当前四个 MVP 场景。当前 4B 基线另外通过 `backend/app/tools/business_tools.py` 注册 Provider、知识检索和健康档案草稿工具；旧工具和新工具都必须经过同一个 Registry 门禁。

## 5. Provider 契约

每个 Provider 统一实现：

- 请求和响应 Pydantic schema。
- mock、sandbox、real 三种运行模式。
- 超时、重试和可重试错误分类。
- 来源元数据和 `SourceRef` 转换。
- 运行日志和敏感字段脱敏。

计划 Provider：

- HospitalProvider
- PharmacyProvider
- OnlineConsultationProvider
- GeoProvider
- NotificationProvider
- MedicalDocumentParser
- MedicalVisionProvider

当前可运行实现位于 `backend/app/providers/`：`ProviderRequest` 和 `ProviderResponse` 是统一 Pydantic 契约，`ProviderRegistry` 校验 provider 名称与运行模式，`build_mock_provider_registry()` 提供七个离线 mock adapter。`sandbox` 和 `real` 尚未配置时必须返回 `success=false`、`degraded=true` 以及明确的 `fallback_reason`，不能伪造外部系统成功。

## 6. 调用顺序

`工具注册 -> allowed_tools 校验 -> 角色权限校验 -> 用户和成员校验 -> 动作确认校验 -> 输入校验 -> Provider/handler 执行 -> 输出校验 -> 记录 ToolResult`

任何环节失败都返回结构化失败并记录 RunTrace。

## 7. 人工确认

以下动作不能因模型生成了工具参数而自动执行：

- 发起复诊或在线问诊。
- 创建购药方案或进入下单。
- 创建用药提醒或随访任务。
- 将报告指标写入长期健康档案。
- 向外部系统发送通知。

确认前只允许创建本地草稿。Agent 安全检查不通过时，即使用户给出确认也不得执行。

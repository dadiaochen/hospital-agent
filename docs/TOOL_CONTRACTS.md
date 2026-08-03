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
- `confirmation_state`
- `provider_mode`

`provider_mode` 只能是 `mock`、`sandbox` 或 `real`。生产运行模式不能由 Prompt 或普通 API 入参覆盖。

最终契约使用 `confirmation_state` 区分 `DRAFT`、`CONFIRMED`、`EXECUTED` 和终止状态。当前实现中的 `human_confirmation_granted` 暂时保留为兼容字段，迁移完成前不能把它等同于最终状态机。

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

最终 4B 深度验收三类 Provider：

- `MedicalDocumentParserProvider`：解析处方、检查报告等医疗文档，保留原文位置与解析版本。
- `PharmacyProvider`：查询药店库存和配送/自提候选，不替用户下单。
- `HospitalOrConsultationProvider`：查询医院、科室、复诊或在线问诊候选，不替用户挂号或提交。

当前可运行实现位于 `backend/app/providers/`：`ProviderRequest` 和 `ProviderResponse` 是统一 Pydantic 契约，`ProviderRegistry` 校验 provider 名称与运行模式，`build_mock_provider_registry()` 提供七个离线 mock adapter。七个 adapter 作为兼容基线保留，但不再把全部深化为最终验收目标。`sandbox` 和 `real` 尚未配置时必须返回 `success=false`、`degraded=true` 以及明确的 `fallback_reason`，不能伪造外部系统成功。

4B 任务六保留的 deterministic 三个领域 Agent 只携带角色工具 allowlist，不执行 Tool；它们用于离线编排契约。当前正式业务路径由 `runtime_domain_agents.py` 提供 Tool-backed `RuntimeTriageAgent`、`RuntimeMedicationAgent` 和 `RuntimeReportAgent`，Supervisor 通过 `SupervisorAgentRuntime` 把它们的请求送入同一个 Registry。`ROLE_ALLOWED_TOOLS` 仍只是候选能力边界；每次真实调用必须继续经过本文件定义的 Tool/Provider 契约、成员权限、超时/重试和审计流程。

### 5.1 4D-B5 步骤级工具权限（已冻结并已实现）

代码审查确认：角色级 `allowed_tools` 由 Tool Registry 校验，计划级 `PlanStep.allowed_tools` 由 Supervisor runtime 在进入 handler 前强制执行。B5.1 已选择方案 A：`PlanStep.allowed_tools` 是该步骤完整的运行时执行上限。运行时 Agent 必须把当前 `step_id` 和该步骤的 allowlist 一起传给 `SupervisorAgentRuntime.call_tool`；调用链同时检查：

```text
角色允许工具
  AND
PlanStep 允许工具
  AND
成员/用户作用域
  AND
工具 schema、确认状态和安全策略
```

因此，角色默认能力不能自动扩大某一个冻结步骤的权限。例如 `RefillAgent` 兼容角色或 `MedicationAgent` 不能因为拥有药房查询能力，就在一个只允许处方读取的 `PlanStep` 中调用库存工具。计划外调用会在 Tool Registry/handler 之前返回 `tool_not_allowed_by_plan`，并写入失败 trace；该行为由 B5.3 测试覆盖。

## 6. 调用顺序

只读调用：

`工具注册 -> allowed_tools 校验 -> 角色权限校验 -> 用户和成员校验 -> 输入校验 -> Provider/handler 执行 -> 输出校验 -> 记录 ToolResult`

受保护动作：

`读取 PostgreSQL confirmation -> 幂等键校验 -> 状态条件更新 -> 执行动作或保持本地状态 -> 输出校验 -> 记录 ToolResult`

任何环节失败都返回结构化失败并记录 RunTrace。

## 7. 人工确认

Agent 可以自动创建无外部副作用的本地 `DRAFT`，但以下动作不能因模型生成了工具参数而自动执行：

- 发起复诊或在线问诊。
- 创建购药方案或进入下单。
- 创建用药提醒或随访任务。
- 将报告指标写入长期健康档案。
- 向外部系统发送通知。

用户确认的是草稿所描述的执行动作，不是“是否允许生成草稿”。确认通过后必须在新的 run 中从 PostgreSQL Task Checkpoint 恢复任务，并重新读取处方、库存等可变事实。任务八允许先读 Redis TTL 投影，但 miss、过期、版本错配或 Redis 故障必须回源 PostgreSQL。Agent 安全检查不通过时，即使用户给出确认也不得执行。

任务七的新业务任务实现将本地草稿投影为 `confirmation_state=DRAFT`，不把草稿创建本身交给 `human_confirmation_granted` 门禁；确认续跑再由 Action Policy Guard 和纯状态机校验 `DRAFT -> CONFIRMED -> EXECUTED`。现有旧 Runtime 的 `create_confirmation_draft` 工具仍保留 `requires_human_confirmation=true` 兼容契约，直到后续统一 API/Tool 迁移，不得把两套语义混写成一套已完成接口。

## 8. 错误与重试

- 只读 Provider 查询仅在错误被标记为 `retryable=true` 时按固定上限重试。
- 写操作不得由模型自由重试；必须依赖幂等键和 PostgreSQL 状态条件更新。
- Provider、schema、权限、成员隔离和安全错误必须分类记录，不能只返回一段异常字符串。
- Redis 不保存工具调用的权威结果；缓存不可用时回源 PostgreSQL，不得跳过权限、确认或幂等校验。

任务八的 checkpoint/cache service 不是业务 Tool，也不能被模型直接选择。它由固定 continuation 边调用；Tool Registry 仍只负责业务事实读取和受保护动作，Redis 不能成为工具证据、处方、库存或确认状态的唯一来源。

任务九已实现：

- `error_type` 保留具体故障名，`error_category` 提供 validation、permission、not_found、timeout、rate_limit、provider_unavailable、business_conflict、schema、internal 九类稳定口径。
- `ToolAttemptTrace` 和 `ProviderAttemptTrace` 分别记录工具 handler 与外部适配器的逐次执行；两层不会对同一写动作叠加自动重试。
- 只有只读工具且错误属于 timeout/rate-limit/provider-unavailable 时才按 `max_attempts` 重试；写工具固定一次。
- Provider identity、mode、operation 或输出 schema 不匹配均归类为 schema，且不可重试。
- 最终失败响应必须 `success=false`、`degraded=true`、`source_refs=[]`；失败数据不能成为 Agent 事实。

三类重点实现位于 `backend/app/providers/reliable.py`。外部 transport 尚未配置，当前验收是 mock/degraded/注入式故障测试，不是实际医院和药店联调。

## 4B 任务十二：事务与真实运行验收

确认草稿 Tool 使用数据库 savepoint，不拥有业务任务的外层事务；`BusinessTaskService` 负责提交 AgentRun、tool-call、checkpoint 和业务状态。这样，单次 Tool 失败会回滚自己的草稿写入，却不会把已记录的 run 审计一起回滚。任务十二在 Docker PostgreSQL 中验证了该边界、并发确认只执行一次以及 Redis 不可用时回源 PostgreSQL。
## 4B 任务十：资源作用域和 Observation

- 档案、处方和药箱 Tool 不能只相信输入中的 `member_id`。ToolRegistry 先校验 execution context，Repository SQL 再同时约束 `user_id + member_id + resource ownership`。
- Pydantic Tool input 使用 `extra=forbid`；在 payload 中添加 `prompt`、伪造 `user_id` 或其他身份字段不能覆盖服务端上下文。
- Tool Observation 只记录 `tool_name/agent_role/success/latency/retry/fallback/source_ids`。`tool_input`、`output` 和错误中的敏感业务内容不进入 Observation。
- RAG Tool 的 SourceRef metadata 保存 keyword/vector score、rank、RRF score、document/chunk version、embedding schema 和 fallback reason，供评测和排障使用。

## 4B 任务十一：工具消融指标

Harness 额外冻结 `AblationToolCallTrace`，仅保存工具名、角色、结构化参数、成功/schema 状态和来源指针。工具集合 exact-match 忽略顺序但拒绝多余工具；参数 exact-match 使用规范化 JSON 多重集，因此重复调用和错误成员参数都会失败。该投影只读，不执行 Tool Registry handler，也不能成为业务证据。

## 4D-B2.6 评测边界

`V2DeterministicGraders` 仍然只读取冻结 `RunTrace` 中的 `ToolCallTrace`、source pointer 和成员作用域，不在评测阶段重新调用 Tool Registry。B2.6 的 `ScopedProviderSandbox` 复用确定性 Provider 契约，只在真实图执行阶段注入 timeout/no-source 故障并记录 attempt trace；`PostgresV2Materializer` 和 `ScopedPostgresRetriever` 负责 case-scoped 数据与 RAG 来源隔离。这样可以测试真实连接边界，同时不会把评测变成不可重复的外部服务联调。完整 300/1200 正式可靠性指标仍待人工审核后运行。

UX-04 不修改 Tool Contract。用户端历史咨询与确认区域不展示 `tool_name`、原始工具输入输出或 SourceRef 标识；这些证据仍由既有运行链路记录并供内部审计使用。

UX-06 不新增 Tool Contract。报告详情接口只读取既有 `medical_documents`，浏览器只接收 `report-detail.v1` 允许的摘要、指标和来源 DTO；解析 provider、对象地址、原始 JSON 和内部来源标识不会成为用户端工具参数或展示内容。

## 用户端 UX-08 与工具入口

UX-08 不改变六类业务工具的 schema、权限、超时、重试或人工确认字段。库存、处方、药箱、知识和草稿工具不再通过首页快捷入口直接暴露；用户仍通过 AI 健康助手触发受治理的业务流程，工具调用继续记录在既有 RunTrace 和 `agent_tool_calls` 中。

## 用户端 UX-09 联调契约

UX-09 联调没有新增 Tool。发现低库存续方在缺少用户显式药品名时无法构造 `check_pharmacy_inventory` 输入，现由 `WorkflowToolInputBuilder` 从当前成员本轮成功的 `query_medicine_box` 或 `query_prescriptions` 结果补齐 `medicine_name`。该值必须有工具证据；没有证据时仍按原契约失败，不允许模型猜测。工具的 `input_schema`、`output_schema`、`permission_scope`、超时、重试和 `requires_human_confirmation` 保持不变。

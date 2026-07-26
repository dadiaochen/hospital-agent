# Agent 架构设计

## 1. 架构目标

系统采用有界、可追踪、可中断的 Multi-Agent 工作流，服务三条业务线。Agent 负责理解任务、组织工具和生成草稿，不直接诊断、开方、修改处方或执行需要用户确认的动作。

## 2. 当前基线与目标架构

当前基线已经具备：

- Planner、档案、续方、药店、提醒和 Agent 安全角色。
- LangGraph 有界状态图。
- ContextEnvelope、Tool Registry、Model Gateway、RunTrace 和 Agent 评测基础。

目标架构将在保留这些共享组件的基础上，按业务领域增加预问诊、慢病履约和报告解读子图。业务领域不是三个互相独立的平台，而是共享身份、成员上下文、RAG、Provider、确认和评测能力。

## 3. 分层

```text
API / Frontend
    -> Business Orchestrator
        -> Context Manager
        -> Planner
        -> Domain Subgraph
        -> Tool Registry
        -> Provider Adapter
        -> RAG Retrieval
        -> Agent Safety
        -> Confirmation
        -> Run Trace / Evaluation
```

职责边界：

- Business Orchestrator：创建任务、选择业务领域和组织状态流转。
- Planner：输出结构化计划、缺失槽位和所需工具，不生成医疗建议。
- Domain Subgraph：处理领域内的受控步骤。
- Context Manager：生成最小角色视图并隔离家庭成员。
- Tool Registry：统一权限、版本、超时、重试、确认和审计。
- Provider Adapter：隔离 mock、sandbox 和 real 外部服务。
- RAG Retrieval：提供带版本、带检索方式的知识来源。
- Agent 安全：在草稿和用户可见输出前阻断高风险请求。
- Agent 评测：在答案冻结后只读评估，不参与业务决策。

## 4. 业务领域与角色

| 业务领域 | 目标角色 | 主要职责 |
| --- | --- | --- |
| 智能预问诊与分级导诊 | 预问诊、导诊 | 补齐主诉、识别红旗症状、生成科室方向和就诊准备 |
| 家庭医生、慢病与用药履约 | 档案、续方、药店、提醒 | 组织处方、药箱、库存、购药和提醒草稿 |
| 报告解读与长期健康档案 | 报告解析、健康档案 | 结构化报告、解释指标、组织趋势和档案写入草稿 |
| 共用 | Planner、Agent 安全、Agent 评测 | 计划、安全阻断和事后评测 |

角色名称是职责表达，不要求每个角色都独占一个模型。MVP 优先复用同一 Model Gateway，通过结构化契约、最小上下文和工具权限实现角色隔离。

## 5. 有界状态图

目标通用状态图：

```text
START
  -> build_context
  -> plan
  -> collect_missing_information
  -> execute_domain_tools
  -> retrieve_knowledge
  -> compose_draft
  -> safety_check
  -> request_confirmation
  -> freeze_final_answer_and_trace
  -> build_run_summary
  -> reset_working_context
  -> evaluate
  -> END
```

约束：

- 循环只能用于有限次数的槽位补充、工具重试或检索改写。
- 每种循环都必须有最大次数、超时和终止原因。
- 阻断型安全标记不得进入确认草稿。
- 运行结束后先冻结用户答案和证据，再做摘要、上下文清理和评测。

## 6. 上下文和成员隔离

`ContextEnvelope` 是每次任务的事实边界。后续扩展应在不破坏现有字段的前提下加入 `business_domain`、Provider 结果和通用 `SourceRef`。

每个角色只接收：

- 当前 `user_id`、`member_id` 和任务目标。
- 已确认槽位和缺失槽位。
- 允许调用的工具。
- 与当前成员相关的工具证据和 RAG 来源。
- 当前任务必要的安全标记。

切换成员或切换不相关任务时必须创建新上下文，不得复用旧 scratchpad。

## 7. RAG 与来源

RAG 是共享基础能力，不是某个业务角色的私有工具。知识来源统一归一化为 `SourceRef`：

- `source_id`
- `source_type`
- `document_id`
- `document_version`
- `chunk_id`
- `retrieval_mode`
- `provider`
- `member_id`
- `verified`

医疗文档和知识库来源必须带文档标识、版本和检索方式。Agent 推断不能标记为已验证事实。

## 8. Provider Adapter

外部能力使用统一运行模式：

- `mock`：本地开发和自动测试，数据必须明确标记为模拟。
- `sandbox`：第三方测试环境，用于联调和契约验证。
- `real`：生产环境真实接口，只能由服务端配置启用。

后续 Provider 包括 HospitalProvider、PharmacyProvider、OnlineConsultationProvider、GeoProvider、NotificationProvider、MedicalDocumentParser 和 MedicalVisionProvider。

## 9. 可观测性

每次运行至少保存：

- 业务领域、用户和成员。
- 计划、工具版本、Provider 模式和调用结果。
- Tool Evidence、RAG SourceRef、检索降级过程。
- Agent 安全结果、确认状态、最终答案和运行摘要。
- Agent 评测结果与失败原因。

以上记录共同支持问题定位、回放、审计和离线评测。

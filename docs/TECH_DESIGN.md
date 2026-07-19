# 技术设计

## 1. 设计目标

本系统不是将大模型直接接到医疗问答上，而是把模型或规则引擎放进一个可约束、可追踪、可确认、可评估的业务流程中。当前线性基线已实现可重复契约、deterministic Harness、2E API、Hybrid RAG、Model Gateway、LangGraph 编排、Runtime 持久化/API、3A/3B 前端、3C Runtime E2E Harness、3D 一键演示和 4A 轻量向量检索。

## 2. 分层架构

```text
API -> schemas -> services -> models -> database
                   ^
LangGraph -> Planner -> ContextManager -> role agents
                                  |            |
                           Tool Registry <- Tool / RAG evidence
                                  |
                  Safety -> confirmation -> Model Gateway
                                  |
                  RunTrace -> reset -> DeterministicEvaluator
```

| 层 | 当前职责 | 关键原则 |
| --- | --- | --- |
| `api` | FastAPI 路由、HTTP DTO、依赖注入和统一错误映射 | 不写查询和 Agent 决策。 |
| `schemas` | API Pydantic 模型 | API 与 ORM 解耦。 |
| `models` | SQLAlchemy 表和关联 | 只表达持久化结构。 |
| `services` | 数据整形、草稿创建、事务边界 | 复用给 API 和工具。 |
| `tools` | ToolSpec、权限、schema、确认门禁 | Agent 不绕过它直接访问业务数据。 |
| `agent` | Context、Trace、Harness 与后续编排 | 使用冻结产物而非隐式聊天状态。 |
| `rag` / `safety` | 来源检索与安全规则 | 无来源不输出事实；高风险先拦截。 |

## 3. 当前数据流

```text
用户输入
  -> ContextEnvelope（任务、成员、允许工具、来源引用）
  -> RoleSpecificContextView（最小角色视图）
  -> ToolRegistry（权限、schema、confirmation gate）
  -> ToolResult / RAGSource
  -> FinalAnswerTrace + RunTrace
  -> RunSummary / reset
  -> DeterministicEvaluator -> EvaluationResult
```

fixture Harness 可以离线回放冻结产物；2G-1 的 LangGraph 工作流实际执行这些节点。2G-2 再由 AgentRuntimeService 注入真实数据库工具、保存 `agent_runs` / `agent_tool_calls` 和版本化冻结产物，但默认模型仍是 deterministic provider，因此不能把通过结果当作真实医疗对话或线上模型能力。

## 4. 核心设计决策

### 4.1 契约优先

Context、工具、Trace 和评估先由 Pydantic 模型定义，并使用 `extra="forbid"` 拒绝未声明字段。这样接口、工具和后续 Agent 节点共享同一份可验证边界，而不是依赖松散的 `dict` 约定。

### 4.2 多成员隔离是结构性约束

`user_id` 代表账户，`member_id` 代表当前被服务的家庭成员。ContextEnvelope、ToolEvidenceRef、RunSummary 和 DB 工具都校验成员一致性；一个调用的请求参数不能覆盖 execution context 的成员范围。

### 4.3 工具是唯一业务入口

每个工具都声明输入输出 schema、permission scope、允许角色、超时、重试、是否只读和是否必须人工确认。Registry 在调用 handler 前依次校验：工具存在、`allowed_tools`、角色、确认、输入 schema；调用后验证输出 schema，并把失败统一为带 `error_type` 与 `fallback_action` 的 ToolResult。

### 4.4 关键动作只创建本地草稿

`create_confirmation_draft` 在确认门禁前不会执行 handler。门禁通过后也只创建 `status="draft"` 的本地记录；审计数据记录 run、幂等键和 `external_action_status="not_submitted"`。没有医院提交、下单或推送能力。

2E-2 在同一 service 之上增加 FastAPI 状态机。API 创建仍要求显式 `human_confirmation_granted`；确认或拒绝要求显式 `human_confirmation_present`。白名单只允许 `draft -> confirmed` 和 `draft -> rejected`，重复决策返回幂等 replay，终态之间不可互转。

`confirmed_at` 保留“允许创建本地草稿”的既有语义。最终决策追加到各业务表已有 JSON detail 的 `_agent_audit.status_transitions`，包含 user、幂等键、时间、备注和 `external_action_status="not_submitted"`。可选 `run_id` 必须与当前 user/member 同时匹配；决策读取在 PostgreSQL 上使用行锁，减少并发重复流转。这样无需新增 migration，也不会把本地确认伪装成外部动作成功。

### 4.5 安全与评估分离

SafetyAgent 是运行时拦截器，负责处理高风险医疗请求、越权查询和跳过确认。EvaluatorAgent 是 post-run 只读评估角色：读取冻结产物，计算质量结果，不能修改答案、调用业务工具或写业务状态。

### 4.6 RAG 以关键词为基线并可选接入真实向量召回

2F-1 把原先位于 service 内的知识库扫描整理为 `Retriever` 协议。4A 在同一契约后接入 FastEmbed `BAAI/bge-small-zh-v1.5` 与 PostgreSQL pgvector：Indexer 为已审核 chunk 生成 512 维 passage embedding；查询使用 query embedding 和精确余弦距离。向量后端仍只返回 `document_id`、`chunk_id` 和相关性分数，正文必须重新从数据库回填。

`RAG_VECTOR_ENABLED` 默认关闭，关闭时不加载模型。显式开启后，Compose 在 migration/seed 后幂等索引；模型、索引、查询异常或来源指针无法回填时，系统保留关键词结果并记录 `fallback_used` / `fallback_reason`。结果中的 `score` 仅表示检索相关性，不是医疗正确率、诊断概率或执行授权。完整设计见 [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md)。

### 4.7 Model Gateway 先解析再使用

2F-2 定义 `ModelProvider` 与 `ModelGateway`。自动测试和无 Key 环境使用 `DeterministicModelProvider`；配置完整时可以使用 OpenAI-compatible HTTP adapter。Provider 只返回文本，Gateway 必须依次执行 JSON 解析、目标 Pydantic schema 校验和独立输出安全检查，全部通过后才返回结构化对象。

超时、HTTP 错误、provider response 错误、schema 失败和 safety 失败都产生 `ModelProviderAttemptTrace`。配置了 fallback 时，Gateway 再调用 deterministic provider；fallback 也失败则返回 `output=None` 和失败 Trace，不把原始文本交给 Agent。规则型输出检查是 Gateway 的最后一道文本门禁，不替代 LangGraph 中的 SafetyAgent。完整设计见 [MODEL_GATEWAY.md](MODEL_GATEWAY.md)。

### 4.8 LangGraph 使用有界 DAG

2G-1 用 `StateGraph` 编排 Planner、ContextManager、四类业务角色、SafetyAgent、确认草稿、FinalAnswer、RunTrace、reset 和 Evaluator。`WorkflowState` 只传 Pydantic 业务产物和节点访问记录；条件边由显式 intent/required tools 决定，不允许模型自由选择无限循环。

节点只能通过 ContextManager 获得 role view，通过 Tool Registry 调用工具，通过 Model Gateway 生成结构化答案。高风险 flag 会在确认草稿前直接路由到安全答案；普通关键动作只有显式确认后才执行本地 draft 工具。图本身仍返回纯 `WorkflowRunResult`；2G-2 的 service adapter 负责事务、审计与 HTTP 边界。完整图设计见 [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md)。

### 4.9 Runtime Adapter 冻结并持久化运行产物

`AgentRuntimeService` 是 API 与 LangGraph 之间的应用服务。它先按当前 user/member 校验作用域并写入 `running` run，再注入真实 DB Tool Registry 执行工作流，最后把每个 ToolResult 写入 `agent_tool_calls`，把版本化 `PersistedRunArtifacts` 写入 `agent_runs.raw_state`。ToolEvidenceRef 的稳定 `tool_call_id` 与数据库行 ID 相同，RAG ref 保留真实 document/chunk/version。

首次 run 不能携带确认；待确认任务通过固定 continuation run ID 续跑。续跑只恢复上一轮 RunSummary、计划和来源指针，重新查询当前数据库，不恢复角色 scratchpad。异常会把 run 标为 `failed` 并只保存错误类型，不把 provider 原文或内部异常消息暴露给客户端。详见 [AGENT_RUNTIME_API.md](AGENT_RUNTIME_API.md)。

### 4.10 前端以成员上下文消费运行与只读审计契约

3A 在浏览器侧增加 `MemberProvider`、统一 API client 和页面级 `useApiResource`。Provider 只保存当前选择的 `member_id`；成员切换会改变资源 key、取消旧请求并清空旧数据。家庭档案、药箱、处方、购药、确认草稿和 run 响应还要通过 `assertMemberScoped` 校验返回 `member_id`，异常时拒绝展示而不是静默过滤。

页面统一区分 loading、empty、error 和 data；搜索类页面另有“尚未查询”状态。3B 的 Agent 页面通过 typed POST client 发起首次未确认 run，并只在后端返回待确认且未阻断时允许同任务续跑。Agent 冻结产物还通过 `assertAgentArtifactsScoped` 检查成员，Run 详情保持 FinalAnswer 与 EvaluationResult 只读。前端检查是纵深防御，后端 demo-user/member scope 仍是权限真相来源。完整说明见 [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md) 和 [AGENT_UI.md](AGENT_UI.md)。

### 4.11 Runtime E2E 从 HTTP 边界评估真实冻结产物

3C 的 `RuntimeE2EHarnessRunner` 不进入 Router、Service 或 LangGraph 内部调用方法，而是像外部客户端一样发现 seed 成员、执行 `POST /api/agent-runs` 和可选 `/continue`。`RuntimeTraceAdapter` 将 API artifacts 递归脱敏，并验证 RunTrace、RunSummary、SafetyTrace、Tool/RAG refs 的 run/task/member 作用域后，才把新的冻结 Trace 交给 DeterministicEvaluator。

固定用例覆盖正常续方、复诊、提醒、高风险阻断、工具空数据失败、无来源拒答、同成员隔离和两类 API Guard。报告只保留用例级状态与指标，不保存成员/run ID 或答案正文。完整说明见 [RUNTIME_E2E_HARNESS.md](RUNTIME_E2E_HARNESS.md)。

### 4.12 一键交付显式化初始化依赖

3D 将本地交付链固定为 PostgreSQL/Redis healthcheck、backend migration、幂等 seed、Uvicorn healthcheck、Next.js production build/start 和外部四场景 Runner。backend 只在 migration 与 seed 都成功后启动；固定 Runner 只走公开 API，继续复用 RuntimeTraceAdapter 和 DeterministicEvaluator，不创建第二套业务逻辑。

默认关键词 RAG 与 deterministic provider 保证无 Embedding、无模型 Key也能复现。OpenAI-compatible provider 仍是可选模式；向量检索仍只有可注入协议。完整运行与模式说明见 [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md)。

## 5. 当前实现边界

| 已实现 | 尚未实现 |
| --- | --- |
| ORM、迁移、seed、只读 DB tools、本地 draft tool 与草稿状态机 API | 生产认证和外部业务提交。 |
| 家庭、药箱、处方/购药、库存、知识检索和 Agent 审计的只读 API | 真实医院、药店和推送 API。 |
| ContextManager、Trace、fixture Harness、确定性评估、Model Gateway、LangGraph DAG 和 Agent Runtime API/持久化 | 线上模型质量验证、生产认证和外部系统集成。 |
| 权限、成员隔离、确认门禁、失败 fallback、关键词 Retriever 与可选 FastEmbed/pgvector 混合检索 | 文档摄取平台、大规模 ANN/reranker 和互联网知识抓取。 |
| 3A/3B Next.js 数据页、Agent 对话、本地确认续跑、Trace/Evaluation 详情和客户端成员响应检查 | 生产浏览器监控、真实登录和外部系统集成。 |
| 3C Runtime E2E、Trace 脱敏 adapter、API Guard 和本地 PostgreSQL 报告 | 生产流量回放、临床有效性或真实 LLM 质量评测。 |
| 3D Compose 自动 migration/seed、四项 healthcheck、固定四场景和脱敏演示报告 | 生产编排、真实登录、秘密管理、HTTPS、浏览器自动化和高可用。 |

详细顺序、验收和非目标以 [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) 为准。

## 6. 代码阅读入口

- Context 契约：[context_schemas.py](../backend/app/agent/context_schemas.py)
- Context 投影与 reset：[context_manager.py](../backend/app/agent/context_manager.py)
- 工具契约：[tool_schemas.py](../backend/app/tools/tool_schemas.py)
- 工具运行门禁：[tool_registry.py](../backend/app/tools/tool_registry.py)
- 草稿事务：[confirmation_draft_service.py](../backend/app/services/confirmation_draft_service.py)
- 草稿 API 状态机：[confirmation_draft_api_service.py](../backend/app/services/confirmation_draft_api_service.py)
- 评估规则：[evaluator.py](../backend/app/agent/evaluator.py)
- 读取 API 编排：[read_api_service.py](../backend/app/services/read_api_service.py)
- RAG 契约：[retrieval_schemas.py](../backend/app/rag/retrieval_schemas.py)
- 关键词与混合检索：[retriever.py](../backend/app/rag/retriever.py)
- Model Gateway 契约：[model_gateway_schemas.py](../backend/app/agent/model_gateway_schemas.py)
- Provider、解析与 fallback：[model_gateway.py](../backend/app/agent/model_gateway.py)
- 模型输出安全检查：[model_output.py](../backend/app/safety/model_output.py)
- LangGraph 状态与节点：[langgraph_workflow.py](../backend/app/agent/langgraph_workflow.py)
- 工作流输入输出契约：[workflow_schemas.py](../backend/app/agent/workflow_schemas.py)
- deterministic 计划与工具入参投影：[workflow_planning.py](../backend/app/agent/workflow_planning.py)
- Runtime 冻结契约：[runtime_schemas.py](../backend/app/agent/runtime_schemas.py)
- Agent Runtime 事务与持久化：[agent_runtime_service.py](../backend/app/services/agent_runtime_service.py)
- 前端 API 客户端：[client.ts](../frontend/lib/api/client.ts)
- 前端成员上下文：[MemberProvider.tsx](../frontend/components/providers/MemberProvider.tsx)
- Agent Runtime HTTP DTO：[agent_runtime.py](../backend/app/schemas/agent_runtime.py)
- Runtime E2E Runner：[runtime_harness.py](../backend/app/agent/runtime_harness.py)
- Runtime Trace 脱敏适配：[runtime_trace_adapter.py](../backend/app/agent/runtime_trace_adapter.py)
- 固定 MVP Demo Runner：[demo_runner.py](../backend/app/agent/demo_runner.py)
- 一键启动脚本：[start_demo.ps1](../scripts/start_demo.ps1)

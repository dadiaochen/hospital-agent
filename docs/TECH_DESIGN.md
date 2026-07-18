# 技术设计

## 1. 设计目标

本系统不是将大模型直接接到医疗问答上，而是把模型或规则引擎放进一个可约束、可追踪、可确认、可评估的业务流程中。隔离分支已实现可重复契约、deterministic 基线、Model Gateway 和正式 LangGraph 编排；Agent HTTP API 与运行持久化仍按路线图后续阶段落地。

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

这是目标运行时的数据流。fixture Harness 可以离线回放冻结产物；2G-1 的 LangGraph 工作流实际执行这些节点，但默认仍使用 deterministic Planner、mock tools 和 deterministic provider，因此不能把通过结果当作真实医疗对话或线上模型能力。

## 4. 核心设计决策

### 4.1 契约优先

Context、工具、Trace 和评估先由 Pydantic 模型定义，并使用 `extra="forbid"` 拒绝未声明字段。这样接口、工具和后续 Agent 节点共享同一份可验证边界，而不是依赖松散的 `dict` 约定。

### 4.2 多成员隔离是结构性约束

`user_id` 代表账户，`member_id` 代表当前被服务的家庭成员。ContextEnvelope、ToolEvidenceRef、RunSummary 和 DB 工具都校验成员一致性；一个调用的请求参数不能覆盖 execution context 的成员范围。

### 4.3 工具是唯一业务入口

每个工具都声明输入输出 schema、permission scope、允许角色、超时、重试、是否只读和是否必须人工确认。Registry 在调用 handler 前依次校验：工具存在、`allowed_tools`、角色、确认、输入 schema；调用后验证输出 schema，并把失败统一为带 `error_type` 与 `fallback_action` 的 ToolResult。

### 4.4 关键动作只创建本地草稿

`create_confirmation_draft` 在确认门禁前不会执行 handler。门禁通过后也只创建 `status="draft"` 的本地记录；审计数据记录 run、幂等键和 `external_action_status="not_submitted"`。没有医院提交、下单或推送能力。

2E-2 隔离分支在同一 service 之上增加 FastAPI 状态机。API 创建仍要求显式 `human_confirmation_granted`；确认或拒绝要求显式 `human_confirmation_present`。白名单只允许 `draft -> confirmed` 和 `draft -> rejected`，重复决策返回幂等 replay，终态之间不可互转。

`confirmed_at` 保留“允许创建本地草稿”的既有语义。最终决策追加到各业务表已有 JSON detail 的 `_agent_audit.status_transitions`，包含 user、幂等键、时间、备注和 `external_action_status="not_submitted"`。可选 `run_id` 必须与当前 user/member 同时匹配；决策读取在 PostgreSQL 上使用行锁，减少并发重复流转。这样无需新增 migration，也不会把本地确认伪装成外部动作成功。

### 4.5 安全与评估分离

SafetyAgent 是运行时拦截器，负责处理高风险医疗请求、越权查询和跳过确认。EvaluatorAgent 是 post-run 只读评估角色：读取冻结产物，计算质量结果，不能修改答案、调用业务工具或写业务状态。

### 4.6 RAG 保留确定性关键词基线

2F-1 把原先位于 service 内的知识库扫描整理为 `Retriever` 协议。`KeywordRetriever` 从 PostgreSQL 的 `knowledge_documents` / `knowledge_chunks` 加载已审核内容并确定性排序；`HybridRetriever` 可以接收可选的 `VectorSearchBackend`，但向量后端只返回 `document_id`、`chunk_id` 和相关性分数，正文必须重新从数据库回填。

`RAG_VECTOR_ENABLED` 默认关闭。显式开启后，如果后端缺失、调用异常或来源指针无法回填，系统保留关键词结果并记录 `fallback_used` / `fallback_reason`。结果中的 `score` 仅表示检索相关性，不是医疗正确率、诊断概率或执行授权。完整设计见 [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md)。

### 4.7 Model Gateway 先解析再使用

2F-2 定义 `ModelProvider` 与 `ModelGateway`。自动测试和无 Key 环境使用 `DeterministicModelProvider`；配置完整时可以使用 OpenAI-compatible HTTP adapter。Provider 只返回文本，Gateway 必须依次执行 JSON 解析、目标 Pydantic schema 校验和独立输出安全检查，全部通过后才返回结构化对象。

超时、HTTP 错误、provider response 错误、schema 失败和 safety 失败都产生 `ModelProviderAttemptTrace`。配置了 fallback 时，Gateway 再调用 deterministic provider；fallback 也失败则返回 `output=None` 和失败 Trace，不把原始文本交给 Agent。规则型输出检查是 Gateway 的最后一道文本门禁，不替代 LangGraph 中的 SafetyAgent。完整设计见 [MODEL_GATEWAY.md](MODEL_GATEWAY.md)。

### 4.8 LangGraph 使用有界 DAG

2G-1 用 `StateGraph` 编排 Planner、ContextManager、四类业务角色、SafetyAgent、确认草稿、FinalAnswer、RunTrace、reset 和 Evaluator。`WorkflowState` 只传 Pydantic 业务产物和节点访问记录；条件边由显式 intent/required tools 决定，不允许模型自由选择无限循环。

节点只能通过 ContextManager 获得 role view，通过 Tool Registry 调用工具，通过 Model Gateway 生成结构化答案。高风险 flag 会在确认草稿前直接路由到安全答案；普通关键动作只有显式确认后才执行本地 draft 工具。图执行结束返回 `WorkflowRunResult`，不写数据库 run，也不提供 HTTP endpoint。完整设计见 [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md)。

## 5. 当前实现边界

| 已实现 | 尚未实现 |
| --- | --- |
| ORM、迁移、seed、只读 DB tools、本地 draft tool；隔离分支中的草稿状态机 API | 生产认证；2E-2 尚待在 2E-1 后线性整合。 |
| 家庭、药箱、处方/购药、库存和 Agent 审计的只读 API | 知识库搜索 API（保留为学习实战题）。 |
| ContextManager、Trace、fixture Harness、确定性评估；隔离分支中的 Model Gateway、HTTP provider adapter 和 LangGraph 有界 DAG | Agent API、runtime/trace 持久化和线上模型调用验证。 |
| 权限、成员隔离、确认门禁和失败 fallback 的单元测试；隔离分支中的关键词/混合 Retriever | 真实 Embedding provider、向量数据库和互联网知识抓取。 |

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

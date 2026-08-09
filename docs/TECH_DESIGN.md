# 技术设计

## 1. 目标与边界

系统把大模型放在受契约约束的互联网医院业务流程中，用于资料整理、知识检索、草稿生成和确认前准备。系统不诊断、不自动开方、不修改医生处方，也不直接提交医院、药店、支付或通知动作。

每个用户可见结果必须能追溯到用户与家庭成员作用域、业务工具事实、RAG 来源、安全决策、确认状态和运行轨迹。

## 2. 总体架构

```text
Next.js
  -> FastAPI API
  -> Service / Transaction
  -> UnifiedHealthGraph
       -> Request Safety
       -> Router
            -> simple: Domain Agent
            -> complex: one-shot Planner -> bounded Supervisor
       -> Context Manager
       -> Domain Agents
            -> Tool Registry
                 -> PostgreSQL / Provider / RAG
       -> Action Safety
       -> Draft / Human Confirmation
       -> Model Gateway
       -> Final Output Safety
       -> FinalAnswer + FinalClaim + RunTrace
       -> RunSummary + Context Reset
       -> Deterministic Evaluator
```

## 3. 分层职责

| 层 | 职责 | 禁止事项 |
| --- | --- | --- |
| `api` | HTTP 参数、响应和依赖注入 | 查询数据库或决定 Agent 路由 |
| `schemas` | Pydantic DTO | 执行业务 |
| `services` | 事务、幂等、状态机和应用编排 | 绕过治理节点 |
| `models` | SQLAlchemy ORM | Agent 逻辑 |
| `agent` | LangGraph、上下文、路由、调度和运行轨迹 | 直接访问数据库或外部 API |
| `tools` | 工具契约、权限、超时、重试和审计 | 绕过用户与成员作用域 |
| `rag` | Embedding、混合检索、版本和来源 | 保存个人健康记忆 |
| `safety` | 请求、动作和最终输出安全 | 代替业务执行或事后评测 |
| `core` | 配置、数据库、缓存、日志和异常 | 业务决策 |

## 4. 多 Agent 编排

简单单领域请求由 Router 直接进入分诊、用药或报告 Agent。复杂跨领域请求由 Planner 一次性生成最多三个步骤的冻结 DAG，Supervisor 只调度依赖已满足的领域步骤。

相互独立、只读且无副作用的步骤可以受控并行；确认、写操作、Checkpoint、Agent 安全和 Agent 评测必须串行。领域 Agent 之间不直接互调，不共享 scratchpad，只通过 Supervisor 交换带来源的结构化结果。

Supervisor 不直接调用业务工具，不改写用户目标，也不能选择、删除或跳过固定治理节点。详细规则见 [Agent 架构](AGENT_ARCHITECTURE.md)。

## 5. 上下文与分层状态

```text
原始对话
  -> 任务上下文构建
  -> ContextEnvelope
  -> 角色最小视图
  -> 工具证据 / RAG 来源
  -> 最终回答
  -> RunSummary
  -> Context Reset
  -> Agent 评测
```

- Working State 只服务单次 run，结束后清理临时推断和 scratchpad。
- PostgreSQL 保存权威 Task Checkpoint、确认状态、冻结产物引用和用户明确确认的偏好。
- Redis 只保存带 TTL 的任务缓存，多实例协调或缓存失效时回源 PostgreSQL。
- 确认会在同一 task 下创建新的 run，通过 parent run 和版本恢复，不复用旧 scratchpad。
- 处方、过敏史、报告和药箱库存每次重新读取，不作为模型长期记忆。
- 所有事实按 user_id、member_id 和 source_id 隔离。

## 6. 工具、Provider 与模型

Agent 只能通过统一工具调用层读取档案、处方、药箱、药店候选、知识规则和本地确认草稿。工具调用记录角色、输入输出、耗时、schema、成功状态、错误类型和降级动作。

只读 timeout、rate limit 和临时不可用允许有限重试；参数、权限、schema、业务冲突和写操作不自动重试。Provider 降级不能伪造数据、来源或外部执行成功。

Model Gateway 的 Provider、模型、Base URL、Key 和 timeout 只来自服务端配置。模型输出必须经过 JSON 解析、Pydantic schema、角色与工具白名单、成员权限和输出安全检查；失败时使用同一契约降级，不展示原始文本。

## 7. RAG

RAG 使用 FastEmbed、PostgreSQL pgvector HNSW 和关键词并行召回，经 RRF 融合、活动版本过滤、来源校验和实体证据筛选后，把最小直接来源交给模型。知识库与个人状态使用不同 namespace 和写入策略。

当前 500 Query 合成测试中，Recall@5 从 70.96% 提升到 85.19%，来源绑定回答准确率从 23.44% 提升到 63.75%，端到端 p95 从 3.40 秒降到 2.19 秒。详细指标和限制见 [RAG 四指标优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)。

## 8. Agent 安全与人工确认

固定治理链包含请求入口、动作执行前和最终回答前三层检查。诊断、停药、加量、减量、换药、严重症状、越权成员查询和跳过确认会触发阻断或转人工。

首次 run 可以自动生成没有外部副作用的本地草稿；用户确认后，以新的 run 重新校验用户、成员、草稿指纹、Checkpoint 版本、确认版本和可变业务事实，再做幂等状态迁移。当前不会向外部医院、药店或通知服务提交动作。

## 9. 评测与可观测性

系统冻结 FinalAnswer、FinalClaim、Tool/Provider attempts、RAG 排名、Safety、Checkpoint 和 RunTrace，再由只读确定性评测器评分。300 个 WorldState、1,200 条表达用于编排与治理；125 个基础 Case、500 条 Query 用于真实 RAG、回答、延迟和成本。

LLM Judge 不进入运行链路，也不作为发布硬门槛。旧执行阶段和历史验收数字见 [项目执行历史](EXECUTION_HISTORY.md)，当前状态只看 [开发总路线图](DEVELOPMENT_ROADMAP.md)。

## 10. 当前未完成

- 真实医院、药店、支付与通知生产接入。
- 生产认证、密钥托管、监控、容量压测、备份恢复和高可用。
- 正式知识文档摄取、审核、切片、发布和回滚流水线。
- 使用合法脱敏真实语言与人工 Gold 的质量评测。

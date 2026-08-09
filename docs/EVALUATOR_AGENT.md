# Agent 评测设计

## 1. 定位

Agent 评测在用户回答、来源和运行轨迹冻结后执行，只读检查本次任务是否正确完成。它不修改答案、不生成医疗建议、不调用业务工具，也不写业务状态。

Agent 安全负责在高风险输出或动作发生前拦截；Agent 评测负责事后发现问题。两者不能混用，也不能由 Supervisor 选择或跳过。

## 2. 输入与输出

评测输入包括：

| 产物 | 用途 |
| --- | --- |
| `ExpectedCase` | 期望意图、成员、工具、来源、安全和确认规则 |
| `ContextEnvelope` | 当前任务和成员的最小上下文 |
| `ToolEvidence` | 工具输入输出、成员、来源、耗时和失败 |
| `RAGSources` | 检索排名、文档版本、命中方式和降级原因 |
| `FinalAnswer` / `FinalClaim` | 用户答案和可验证事实 |
| `RunTrace` | 一次运行的冻结轨迹 |
| Checkpoint / Confirmation 投影 | 两次 run 续跑、版本和幂等证据 |

输出 `EvaluationResult`，至少包含任务完成、工具调用、来源覆盖、schema、幻觉、Agent 安全召回、人工确认、成员隔离、延迟和失败原因。

## 3. 确定性评分

评测器不依赖 LLM 判断硬门槛，主要规则包括：

1. 意图、用户和家庭成员必须匹配。
2. 实际工具集合与参数必须覆盖期望，并遵守步骤级白名单。
3. 回答中的事实必须绑定真正支持该陈述的来源。
4. 过期来源、跨成员来源和无来源医疗结论均判为失败。
5. 高风险请求必须命中相应 Agent 安全标记。
6. 需要人工确认时，回答和状态都必须保持待确认。
7. schema、fallback 和失败原因必须完整记录。
8. PostgreSQL Checkpoint、parent run、确认版本和恢复来源必须一致。
9. 任何失败结果都必须给出可定位的 failure reason。

LLM Judge 只允许作为离线辅助分析，不能替代来源、权限、成员隔离、Agent 安全和确认状态的确定性检查。

## 4. 两套评测数据

### 4.1 多 Agent 编排与治理

300 个 WorldState、每个 4 种表达，共 1,200 条 Query，按基础 WorldState 拆分 development、validation 和 holdout。它主要检查 Router、Planner、Supervisor、工具、来源、安全、上下文和数据库状态。

同一 WorldState 的表达不能跨 split。生产上下文使用 `dependency_only`，`all_history` 只用于合成测试消融。

### 4.2 RAG 回答质量与性能

120 篇合成文档、2,307 个 Chunk、125 个基础 Case、500 条 Query，用真实 FastEmbed、PostgreSQL pgvector HNSW 和真实 LLM 测量召回、来源绑定回答、幻觉、延迟、token 和成本。

当前结果：

| 指标 | 初始 | 当前 |
| --- | ---: | ---: |
| Recall@5 | 70.96% | 85.19% |
| 来源绑定回答准确率 | 23.44% | 63.75% |
| 来源绑定幻觉率 | 51.25% | 7.50% |
| 端到端 p95 | 3,398.879 ms | 2,187.268 ms |
| 总 token | 620,183 | 231,268 |
| 观测成本 | $0.675887 | $0.276581 |

全量真实模型调用中有 5.00% 结构化输出 fallback。详细边界见 [RAG 四指标优化实施与复测](RAG_SYNTHETIC_MINIMAL_OPTIMIZATION_IMPLEMENTATION.md)。

## 5. 指标解释

- Recall@K 只表示期望来源是否进入前 K 个结果。
- 来源绑定回答准确率只表示合成标签下，答案与支持来源一致，不是临床准确率。
- 幻觉率统计无来源或来源不支持的事实，不代表开放域全部幻觉。
- confirmation present 表示流程正确要求确认，不是人工采纳率。
- fixture latency 不能当作真实 wall-clock；本机 wall-clock 也不是生产 SLA。
- 没有 Provider usage 时，token 和成本必须为不可用，不能按字符估算。
- 分母为零的指标记为 `N/A`，不能当作 100%。

## 6. 运行与产物

固定测试和报告命令见 [测试指南](TESTING_GUIDE.md)。运行产物默认写入被 Git 忽略的 `output/benchmarks/`；当前文档只保存可复用结论，旧阶段与旧报告摘要见 [项目执行历史](EXECUTION_HISTORY.md)。

评测数据、人工审核队列、身份映射、API Key 和 Provider 原始文本不得提交。真实模型输出必须先经过 JSON、Pydantic schema 和输出安全检查，失败时只保留脱敏 attempt trace。

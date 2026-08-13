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

输出 `EvaluationResult`，至少包含任务完成、工具调用、来源覆盖、schema、Agent 安全、人工确认、成员隔离、延迟和失败原因。`RunTrace.tool_calls[*].tool_input` 保存实际规范化参数；统一 Harness 另外冻结 `expected_blocked` 与 `observed_blocked`，用于区分漏拦截和误拦截。

## 3. 确定性评分

评测器不依赖 LLM 判断硬门槛，主要规则包括：

1. 意图、用户和家庭成员必须匹配。
2. 实际工具集合必须与期望集合完全一致；漏调和多调都判错。工具名匹配后，参数按统一 Gold 标注投影做规范化 exact/rule match。
3. 回答中的事实必须绑定真正支持该陈述的来源。
4. 过期来源、跨成员来源和无来源医疗结论均判为失败。
5. 高风险请求必须命中相应 Agent 安全标记。
6. 需要人工确认时，回答和状态都必须保持待确认。
7. schema、fallback 和失败原因必须完整记录。
8. PostgreSQL Checkpoint、parent run、确认版本和恢复来源必须一致。
9. 任何失败结果都必须给出可定位的 failure reason。

LLM Judge 只允许作为离线辅助分析，不能替代来源、权限、成员隔离、Agent 安全和确认状态的确定性检查。目标回答模型使用 `MODEL_*`，独立 Judge 使用 `RAGAS_JUDGE_*`；允许复用服务商账号，但禁止使用相同模型进行自评。Qwen-compatible Judge 默认通过 `RAGAS_JUDGE_THINKING_MODE=disabled` 关闭隐藏思考，减少离线评测 token。

## 4. 一个统一评测数据集、多个视图

所有后续评测只读取 `output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/`。Agent、工具参数和 RAG 是同一数据集的不同视图，不再维护彼此竞争的版本号或独立 Gold；标签不足时在统一数据集中扩充并更新 manifest/hash。

### 4.1 Agent 编排与治理视图

当前活动评测集为 fast-400：100 个 WorldState、每个 4 种表达，共 400 条 Query，按基础 WorldState 拆分 development、validation 和 holdout（240/80/80）。它主要检查 Router、Planner、Supervisor、工具、来源、安全、上下文和数据库状态。完整 300/1200 来源仅留档，不被默认 Loader 读取。

同一 WorldState 的表达不能跨 split。生产上下文使用 `dependency_only`，`all_history` 只用于合成测试消融。

### 4.2 RAG 回答质量与性能视图

120 篇合成文档、2,392 个 Chunk、125 个基础 Case、500 条 Query，用真实 FastEmbed、PostgreSQL pgvector HNSW 和真实 LLM 测量召回、来源绑定回答、延迟、token 和成本。

当前结果：

| 指标 | 初始 | 当前 |
| --- | ---: | ---: |
| Recall@3 / @5 / @10 | 67.50% / 85.19% / 95.38% | 100.00% / 100.00% / 100.00% |
| Precision@3 / @5 / @10 | 25.00% / 21.38% / 12.46% | 43.59% / 26.15% / 13.08% |
| 来源绑定回答准确率 | 74.69% | 99.69% |
| Faithfulness（可回答题） | 0.9545 | 0.9837 |
| Response Relevancy（可回答题） | 0.4752 | 0.6818 |
| Context Recall（可回答题） | 0.8462 | 1.0000 |
| 确定性来源绑定幻觉率 | 7.50% | 0.00% |

最终 320 条 RAG 子集均由真实 Provider 返回，无 fallback；来源绑定回答 319/320，唯一失败是版本题的一种口语表达保守拒答。RAGAS 只对 260 条可回答题计算，60 条无答案题单列无答案准确率 100%。详细指标和边界见 [RAG 合成评测统一报告](RAG_SYNTHETIC_EVALUATION_DATASET.md)。

### 4.3 Agent 全量运行状态

历史 1,200 条统一 Agent Query 已通过 PostgreSQL 隔离事务和实际 UnifiedHealthGraph 完整复测；当前活动视图为 400 条，后续报告只统计这 400 条。deterministic provider 不产生付费 token。所有活动 Query 均冻结 `observed_blocked`，并保留 96 条高风险 Query；历史 1,200 结果中的工程指标仅作历史基线，不是当前 fast-400 结果，也不是临床指标。

5A-9 的差异校准已完成：Gold 过时项包括阻断与用户确认混用、失败后仍要求下游动作工具，以及跨域故障后独立只读分支的旧期望；实现错误项包括空知识结果未 fail-closed、case-scoped RAG 未接入 `search_safety_knowledge`，以及 Supervisor 过早终止独立兄弟步骤。修复后最终回答、安全确认、可靠性和数据库状态四类差异均为 0。真实 LLM fast-400 已完成 3 条冒烟和 400 条分批全量运行，并按冻结业务状态 Gold 自动评分：意图、路由、工具、参数和最终回答正确率均为 100%，端到端任务成功率 99.25%，高风险拦截率/误拦截率 100%/0%，真实 Provider/完整 usage 覆盖率均为 69.25%，fallback 0.75%，端到端 P50/P95/P99 为 4,294/6,645/7,850 ms。本数据集不设人工逐条审核门；最终回答正确率是合成业务 Gold 下的工程正确率，不是临床准确率。

## 5. 指标解释

- Recall@K 只表示期望来源是否进入前 K 个结果。
- 来源绑定回答准确率只表示合成标签下，答案与支持来源一致，不是临床准确率。
- confirmation present 表示流程正确要求确认，不是人工采纳率。
- fixture latency 不能当作真实 wall-clock；本机 wall-clock 也不是生产 SLA。
- 没有 Provider usage 时，token 和成本必须为不可用，不能按字符估算。
- 分母为零的指标记为 `N/A`，不能当作 100%。
- 正式发布指标固定为意图、路由、工具调用、工具参数、最终回答、端到端任务成功、Recall@K、Precision@K、Faithfulness、Response Relevancy、P50/P95/P99、单任务/成功任务 token、高风险拦截率和误拦截率。其他实现字段只用于诊断。
- RAGAS Faithfulness 和 Response Relevancy 只作为离线语义交叉验证。适配器只读取已冻结的回答、检索来源和答案 Gold；缺失项记为 `N/A` 并从分子、分母同时排除。

## 6. 运行与产物

固定测试和报告命令见 [测试指南](TESTING_GUIDE.md)。运行产物默认写入被 Git 忽略的 `output/benchmarks/`；当前文档只保存可复用结论，旧阶段与旧报告摘要见 [项目执行历史](EXECUTION_HISTORY.md)。

评测数据、人工审核队列、身份映射、API Key 和 Provider 原始文本不得提交。真实模型输出必须先经过 JSON、Pydantic schema 和输出安全检查，失败时只保留脱敏 attempt trace。

最终回答质量门不是 `EvaluatorAgent`：它是答案冻结前的运行时治理检查，不调用业务工具、最多一次无 Tool 修复；`EvaluatorAgent` 继续在冻结后只读评分。质量门审计可作为 RunTrace/Checkpoint 的辅助证据，但不能替代 groundedness、safety 或人工 Gold 的评测结论。

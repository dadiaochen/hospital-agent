# 项目执行历史归档

本文只保存已经结束的阶段、关键决策和当时的验证证据，供排查问题和 Git 回退时查阅。当前产品说明、技术设计、接口、测试和简历表达不应再引用阶段任务号；如需查看某次实施的逐行记录，请使用 Git 历史。

## 1. 里程碑摘要

| 里程碑 | 完成内容 | 当时的主要证据 |
| --- | --- | --- |
| 基础工程 | FastAPI、SQLAlchemy、Alembic、PostgreSQL、seed、基础前端 | 模型与迁移测试 |
| Agent 契约 | ContextEnvelope、RunTrace、EvaluationResult、固定评测用例 | Pydantic 契约和 deterministic evaluator |
| 工具与 RAG | Tool Registry、Provider 适配、关键词与 pgvector 混合检索 | 工具异常、来源和降级测试 |
| 业务编排 | Router、一次性 Planner、bounded Supervisor、三个领域 Agent | 32 条编排消融和运行轨迹 |
| 安全与状态 | 三层 Agent 安全、确认状态机、PostgreSQL Checkpoint、Redis 回源 | 并发确认、成员隔离和缓存故障测试 |
| 产品交付 | Next.js 患者端、Docker Compose、固定演示和浏览器 E2E | 四个演示场景、7 条早期浏览器 E2E |
| 统一评测 | FinalClaim、Trace v2、300 个 WorldState、1200 条表达 | Gold 人工审核、九维 deterministic grader |
| RAG 优化 | 版本过滤、Query 实体证据门、运行内知识快照 | 500 条 synthetic Query 的真实模型全链路对比 |
| 5A 业务闭环 | 统一报告解析、直接结构化解读、最终回答质量门、Checkpoint 审计收口 | 真实 RapidOCR 冒烟与增量回归；详见 `implementation/5A_CLOSEOUT.md` |

## 2. 主要架构决策

1. 简单请求直接进入领域 Agent，复杂请求才由 Planner 生成冻结计划并交给 Supervisor。
2. Supervisor 负责调度真实领域 Agent，但不能绕过安全、确认、Checkpoint 和事后评测。
3. Agent 只能通过 Tool Registry 读取数据库、Provider 和 RAG，不能直接持有数据库连接。
4. PostgreSQL 是任务和确认记录的权威存储；Redis 只做带 TTL 的缓存，故障时回源 PostgreSQL。
5. 不保存长期完整聊天，不建立个人健康向量记忆；医疗事实每次从权威业务数据重新读取。
6. 自动测试默认使用 deterministic provider；真实模型是可选运行模式，原始输出必须经过结构校验和安全检查。
7. 医疗知识采用 PostgreSQL、pgvector、FastEmbed、关键词检索和 RRF；个人数据不进入知识向量库。

## 3. 历史验收快照

以下数字是特定时间、特定环境的工程证据，不代表生产 SLA 或临床指标。

| 验收 | 历史结果 | 适用范围 |
| --- | ---: | --- |
| 后端全量回归 | 297 passed | 4C 收口时的测试快照 |
| 前端单元测试 | 25 passed | 4C 收口时的测试快照 |
| 浏览器 E2E | 7 passed | Docker + deterministic provider 的早期固定场景 |
| Docker 后端检查 | 19/19 | PostgreSQL、Redis、FastAPI、RAG 和确认链路 |
| 固定业务演示 | 4/4 | 续方、复诊材料、提醒和高风险阻断 |
| 编排消融 | 32 条 | 合成用例，不是线上任务成功率 |
| v2 评测输入 | 300 个 WorldState / 1200 条 Query | 合成状态及四种表达，不是 1200 条真实回答 |
| 真实模型人工复核 | 8/8 | development 小样本，不能外推全量质量 |

## 4. RAG 优化记录

测试集由 120 篇合成文档、2307 个 Chunk、125 个 Base Case 和 500 条 Query 组成。最终保留方案依次解决三个问题：

1. **旧版本干扰召回**：把活动版本过滤提前到候选截断前，避免过期 Chunk 占用 Top-K。
2. **错误证据进入回答**：增加 Query 实体证据门和最小来源上下文，只把直接支持当前问题的来源交给模型。
3. **重复数据库读取**：在单次评测运行中复用只读知识快照，向量来源仍回 PostgreSQL 校验版本。

| 指标 | 优化前 | 优化后 | 变化 |
| --- | ---: | ---: | ---: |
| Recall@5 | 70.96% | 85.19% | +14.23 个百分点 |
| 来源绑定回答准确率 | 23.44% | 63.75% | +40.31 个百分点 |
| 来源绑定幻觉率 | 51.25% | 7.50% | -43.75 个百分点 |
| 端到端 p95 | 3398.879 ms | 2187.268 ms | -35.65% |
| 总 token | 620,183 | 231,268 | -62.71% |
| 观测成本 | 0.675887 USD | 0.276581 USD | -59.08% |

最终运行 fallback rate 为 5.00%。这些结果来自 synthetic/test-only 数据、FastEmbed、PostgreSQL pgvector HNSW 和真实 OpenAI-compatible 模型，不是患者数据、临床准确率或生产 SLA。

## 5. 已知未完成边界

- 未接入真实医院、药店、支付和通知系统；受保护动作只完成本地草稿和状态迁移。
- 未完成生产认证、密钥托管、正式监控、容量压测和高可用部署。
- 300/1200 v2 数据主要用于契约、路由和治理评测，不能替代真实用户回答质量评测。
- 自动文档摄取和通用切片流水线不是当前产品能力；现有知识数据为结构化合成语料和人工规则单元。
- LLM Judge 不进入运行链路，也不作为发布硬门槛。

## 6. 5A-2 RAGAS 冻结记录离线复评

- 修复 `raise_exceptions=True` 导致单个 `StringIO.question` 格式异常拖垮 320 条批次的问题；改为单项失败隔离、非有限分数转 N/A，并保留同一 Query 的其他成功指标。
- 新增冻结记录离线评分入口，只读取 `answer_results.jsonl`、`query_results.jsonl`、`answer_harness_view.jsonl` 和冻结 Chunk；不重跑语料 Embedding、PostgreSQL/HNSW 检索或目标回答模型。
- 首轮 320 条全部至少获得一项分数，296 条三项齐全；随后只补跑 24 条缺失项，最终 300 条三项齐全、20 条部分评分。
- 最终统一排除 20 条部分评分样本，不按 0 分处理；使用 300 条三项齐全共同样本计算：Faithfulness `0.6166`、Response Relevancy `0.4316`、Context Recall `0.6700`。补跑后独立 Judge 返回 HTTP 402 余额不足，缺失项只保留为诊断记录。
- 运行产物位于被 Git 忽略的 `output/benchmarks/rag_synthetic/rag-synthetic-v1-ragas-offline-full-fix-retry-20260810/`，不提交数据集、答案或 Judge 明细。

## 7. Git 回溯方法

需要恢复旧阶段文档时：

```powershell
git log --all -- docs
git show <commit>:docs/<旧文件名>
```

不要为了恢复文档执行 `git reset --hard`。当前工作区存在其他改动时，应从指定提交只读取文件内容，再决定是否单独恢复。

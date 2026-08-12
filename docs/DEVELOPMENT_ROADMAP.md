# 开发总路线图

本文是项目当前完成度和后续方向的唯一权威来源。子系统文档只解释现有设计，不维护另一套阶段计划；已结束的 2A、4B、4D 等实施记录统一放在 [执行历史归档](EXECUTION_HISTORY.md)。

## 1. 产品目标

构建一个面向家庭健康场景的有界多 Agent 系统，处理预问诊信息整理、慢病续方准备、家庭药箱、用药提醒和报告解读。系统帮助用户整理资料、查询来源和准备草稿，不替代医生诊断、开方或调整用药。

## 2. 当前已经完成

| 能力 | 当前实现 |
| --- | --- |
| 产品端 | Next.js 患者端、家庭成员切换、AI 健康助手、历史咨询和报告页面 |
| 后端 | FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL、Redis |
| 多 Agent | Router、一次性 Planner、bounded Supervisor、Triage/Medication/Report 三个领域 Agent |
| 工具 | Tool Registry、步骤级工具白名单、输入输出校验、超时、有限重试和审计 |
| 模型 | deterministic/真实模型双模式、结构化输出、失败降级和 token/成本记录 |
| RAG | FastEmbed、PostgreSQL pgvector HNSW、BM25、RRF、实体过滤、轻量 rerank、版本校验和来源引用 |
| 上下文 | 最小角色视图、同任务压缩、run 后重置、PostgreSQL Checkpoint 和 Redis TTL 缓存 |
| 安全 | 请求、动作、最终回答三层 Agent 安全；草稿和显式确认状态机 |
| 评测 | RunTrace、FinalClaim、确定性 grader、故障注入、浏览器 E2E 和真实模型离线评测 |
| 部署 | Docker Compose 一键启动 PostgreSQL、Redis、后端和前端 |

## 3. 当前运行链路

用户请求 → 身份与成员校验 → 请求安全检查 → Router。简单任务直接进入一个领域 Agent；复杂任务由 Planner 生成冻结计划，再由 Supervisor 调度多个领域 Agent。Agent 通过 Tool Registry 读取数据库、Provider 和 RAG，之后依次经过动作安全检查、本地草稿与人工确认、Model Gateway、最终回答安全检查、产物冻结、上下文重置和只读 Agent 评测。

## 4. 已冻结的架构原则

1. 简单请求不进入 Supervisor；复杂请求最多三个业务步骤，并有明确依赖和终止条件。
2. Supervisor 只调度业务 Agent，不调用工具，也不能选择或跳过安全和评测节点。
3. Agent 只能通过 Tool Registry 获取事实；没有 Tool、Provider 或 RAG 来源时不能编造医疗事实。
4. 相互独立的只读步骤可以受控并行；确认、写操作、Checkpoint 和安全节点保持串行。
5. PostgreSQL 是任务和确认记录的权威来源；Redis 只做缓存，故障时回源 PostgreSQL。
6. 不保存长期完整聊天，不建立个人健康向量记忆；只保存用户明确确认的非医疗偏好。
7. 自动测试不依赖真实模型；真实模型输出仍要经过 schema、权限和安全规则校验。
8. 不实现无限 ReAct、MCP Server、复杂自动重规划或用 LLM Judge 代替验收。

## 5. 当前指标证据

- 当前 Agent 快速评测视图为 100 个合成 WorldState、400 条表达（每个状态 4 种表达），用于路由、计划、工具、来源、安全和成员隔离的确定性评测；完整 300/1200 来源已留档，不作为默认评测输入。
- 500 条 synthetic RAG Query 用于真实 FastEmbed、pgvector HNSW 和真实模型全链路对比。
- RAG 当前保留方案相对旧冻结基线：Recall@3/@5 从 67.50%/85.19% 提升到 100%/100%，Precision@3/@5 从 25.00%/21.38% 提升到 43.59%/26.15%，来源绑定回答正确率从 63.75% 提升到 74.69%，确定性来源绑定幻觉率从 7.50% 降到 0%。均为冻结合成工程指标；本轮 token、成本和 P95 未下降，RAGAS 新复评因 Judge 账户计费不可用为 N/A。
- 上述指标属于本地 synthetic/test-only 工程评测，不是临床准确率、线上成功率或生产 SLA。

## 6. 仍未完成

| 优先级 | 工作 | 完成标准 |
| --- | --- | --- |
| NEXT | 生产化与真实外部系统验收 | 接入经过授权的医院/药店/通知沙箱，完成认证、密钥托管、监控、容量和故障演练 |
| PLANNED | 真实用户语言质量评测 | 使用合法脱敏数据和人工 Gold，独立报告回答正确性、拒答和人工确认体验 |
| PLANNED | 知识摄取流水线 | 增加文档审核、自动切片、版本发布、回滚和增量索引 |
| PLANNED | 部署与运维 | CI/CD、生产配置、告警、备份恢复、安全扫描和高可用方案 |

这些工作没有完成前，项目应表述为“本地工程化学习与评测项目”，不能表述为已生产上线。

## 7. 文档和 Git 规则

- 当前设计变化同步更新对应技术文档，不在每份文档追加完成日志。
- 某次运行报告默认写入被 Git 忽略的 output/ 或 var/。
- 只有可复用的结论进入当前文档；阶段过程进入 [执行历史归档](EXECUTION_HISTORY.md)。
- .env、API Key、真实患者数据、本机身份映射和人工审核队列不得提交。

## 8. 5A 业务闭环与分层评测收口

本轮以 `Hospital_Agent_业务闭环补齐_Codex执行方案` 为输入，仍以本路线图为唯一授权来源。采用增量方式补齐前置范围拦截、RAG 分层评测与业务闭环缺口；不推翻当前 Router、一次性 Planner、bounded Supervisor、三个领域 Agent、固定 Agent 安全和 post-run Agent 评测边界。

| 顺序 | 工作 | 状态 | 完成标准 |
| --- | --- | --- | --- |
| 5A-0 | 代码审计与基线冻结 | DONE | 已建立审计文档和本地基线备份分支 |
| 5A-1 | RequestScopeGuard | DONE | 高置信度业务外请求在 Router / RAG / Tool / 主模型前终止，保留隐私安全 Trace |
| 5A-2 | RAG Retrieval 与 Generation 分层评测 | DONE | frozen Gold 自动计算 Recall/MRR/nDCG 与 bad case 归因；目标回答模型与独立 Judge 使用两套服务端配置，Judge 可独立关闭隐藏思考以控制 token；RAGAS 0.2.9 支持冻结回答离线复评、单项失败隔离和缺失项定向补分，320 条中 300 条三项齐全 |
| 5A-3 | 合成数据集接入 Harness | DONE | 同一 125/500 冻结数据集已投影为 Entry、Retrieval、Answer 三类离线 Harness 视图，并与全链路报告同目录输出 |
| 5A-4 | Triage 多轮槽位状态机 | DONE | `needs_clarification` 冻结最小槽位状态；补充后以新 run、版本校验和成员隔离从 PostgreSQL Checkpoint 安全续跑 |
| 5A-5 | 统一文档解析 | DONE | 文本、PDF、图像和表格独立解析后输出统一 `ParsedDocument`，不生成诊断或治疗建议 |
| 5A-6 | 报告上传与结构化解读 | DONE | 报告上传后直接持久化为可读结构；文本/表格、PDF 文本层和本地图片 OCR 统一解析，不生成报告确认草稿 |
| 5A-7 | FinalAnswerQualityGate | DONE | 冻结前最多一次无 Tool 的格式修复；无来源事实或安全失败 fail-closed |
| 5A-8 | Context / Checkpoint 收口 | DONE | 新质量门状态进入既有 PostgreSQL Checkpoint；Redis TTL 缓存继续失效回源 |
| 5A-9 | E2E、报告与 Git Freeze | IN PROGRESS | `tool_input` 与 `observed_blocked` 已进入冻结运行产物；当前默认统一 Agent 视图固定为 fast-400：100 个 WorldState、400 条 Query，development/validation/holdout 为 240/80/80，并保留全部 96 条高风险 Query。完整 300/1200 来源已留档，不被默认 Loader 和评测命令读取。Agent 与 RAG 的独立 Query 已支持默认 4 路、上限 16 路的受控并发。RAG 已在同一 125/500 冻结集完成 BM25 + HNSW 双路召回、RRF、实体过滤、候选 20 条 rerank 和主片段优先的策略验证：Recall@3/@5 为 100%/100%，Precision@3/@5 为 43.59%/26.15%，真实模型来源绑定回答正确率为 74.69%，确定性来源绑定幻觉率为 0%；RAGAS 本轮 Judge 账户计费不可用，按 N/A 排除。已完成 3 条真实 LLM 冒烟及 400 条真实 LLM 分批全量运行，并按冻结合成 Gold 自动评分：意图、路由、工具、参数和最终回答正确率均为 100%，端到端任务成功率 99.25%，高风险拦截率/误拦截率 100%/0%，真实 Provider 覆盖率 69.25%，fallback 0.75%，完整 usage 覆盖率 69.25%，端到端 P50/P95/P99 为 4,294/6,645/7,850 ms，总 token 367,920、观测成本 `$0.529735`。本测试集不设人工 badcase 复核门；当前仍停留在 5A-9，待 Git Freeze。 |

5A-9 补充完成：在同一 125/500 统一 RAG 数据集上，真实模型已对 65 个正样本基础 Case 自动补充定义、条件、步骤和例外证据标签，无人工审核、无 fallback；原 `relevant_chunk_ids` 仍保持不变。复用已冻结检索结果的 AI 自动扩展证据 Precision@3/@5/@10 为 60.51%/50.15%/31.81%，仅作为标签覆盖诊断，不替代冻结 Gold，也不作为检索模型优化收益。

5A-9 补充完成：`BAAI/bge-reranker-base` Cross-Encoder 在相同冻结 Top-10 候选的 15 个基础 Case、60 条 Query 对照中，使自动扩展证据 Precision@3 从 60.56% 降至 17.78%，原冻结 Gold Precision@3 从 33.33% 降至 0%。其不能表达“规则主片段优先、版本和实体约束”，已作为无效方案留档，不接入 RAG 主链路；5A-9 状态仍为 IN PROGRESS，待 Git Freeze。

5A-9 补充完成：真实 LLM `deepseek-v4-flash` 在相同的 60 Query 受限重排对照中，只允许输出原 Top-10 的完整排列；自动扩展证据 Precision@3/@5 从 60.56%/53.33% 变为 55.00%/49.33%，冻结 Gold Precision 持平，且每条额外消耗约 2,850 token、2.12 秒。未获得质量净收益，已作为无效方案留档，不接入 RAG 主链路；5A-9 状态仍为 IN PROGRESS，待 Git Freeze。

5A-9 补充完成：真实 LLM 仅规范化原问句的已出现实体/条件后，进入同一 BM25 + HNSW + RRF 检索；60 Query 的自动扩展证据 Precision@3/@5 从 60.56%/53.33% 变为 64.45%/54.33%，但原冻结 Gold Recall/Precision 持平，并增加约 220 token、1.88 秒/条。收益仅限自动标签覆盖诊断，不接入默认 RAG 主链路或简历；5A-9 状态仍为 IN PROGRESS，待 Git Freeze。

5A-9 补充完成：结构化实体过滤 + 父子 Chunk 组装在 60 Query 核验中，与当前 M5 的实体过滤、主片段优先和最小证据门产生 60/60 完全相同的模型输入证据；因此没有新增 profile 或主链路改动。后续真正的父子检索需 `parent_chunk_id` / `section_id` 元数据与独立人工多证据 Gold 验证；5A-9 状态仍为 IN PROGRESS，待 Git Freeze。

5A 的详细审计、复用边界和已知限制见 [业务闭环与分层评测差距审计](implementation/FINAL_BUSINESS_GAP_AUDIT.md)。所有 synthetic 数据和单次运行报告继续只保存在被 Git 忽略的 `output/` 或 `var/`。

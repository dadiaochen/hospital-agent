# 互联网医院 Agent 统一评测数据集与指标

> 本文是 `internet-hospital-agent-eval-v1` 的唯一数据与指标口径。历史数据集名称只用于结果追溯，不再作为独立评测集。

## 1. 唯一数据源规则

后续所有正式评测只读取：

`E:\project_code\hospital\output\benchmarks\evaluation_dataset\internet-hospital-agent-eval-v1\`

旧 Agent 场景、RAG Case 和工具参数 Gold 已合并到该目录。若现有字段无法支持新指标，必须直接扩充此数据集并更新 `manifest.json`、哈希和标注来源，不得新建并行的 v2、v3 或专项 Gold 数据集。

合成数据、真实回答和运行结果均放在 Git 忽略的 `output/`，不得上传 GitHub。本数据仅用于测试，不是患者数据、医疗知识库或临床 Gold。所有标签由冻结业务状态和固定规则自动生成并自动评分；不设人工逐条审核或 badcase 复核门。

## 2. 数据规模与划分

| 数据视图 | 基础状态 | Query | 主要标注 |
| --- | ---: | ---: | --- |
| Agent（当前活动视图） | 100 个 WorldState | 400 | 意图、路由、工具集合、工具参数、安全、确认、回答事实、成员隔离 |
| RAG | 125 个 Case | 500 | 相关 Chunk、无答案、高风险、回答事实、禁止声明、来源绑定 |
| 合计（当前活动视图） | 225 | 900 | 统一 `query_id`、split、标注来源和冻结哈希 |

> Agent 当前使用 fast-400：100 个 WorldState × 4 种表达，共 400 条 Query；development、validation、holdout 分别为 240、80、80。原始完整 300 个 WorldState / 1,200 条 Query 已复制到 `output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1-1200/` 留档，仅用于历史追溯和回退，不作为默认评测输入，也不上传 GitHub。

此外包含 32 个工具参数种子 Case、48 次完整参数调用 Gold；按统一 Agent Query 和当前运行时工具契约展开后有 4,692 个工具调用标签和 2,992 个精确参数字段。

同一基础状态的四种表达不会跨 split，避免表达泄漏：

| 视图 | development | validation | holdout | 合计 |
| --- | ---: | ---: | ---: | ---: |
| Agent Query（fast-400） | 240 | 80 | 80 | 400 |
| RAG Query | 300 | 100 | 100 | 500 |

当前 RAG holdout 的正样本覆盖仍有限，因此 500 Query 结果用于固定工程基线，不宣称临床效果或独立泛化能力。

### 2.1 评测并发执行

不同 `query_id` 的评测互相独立，因此 Agent fast-400 与 RAG 500 Query 默认使用 **4 路受控并发**，可通过 `--concurrency 1-16` 调整。每条 Agent Query 保持独立 PostgreSQL 事务；每条 RAG Query 保持独立 Session、向量 Top-K 查询和 ModelGateway。数据库导入、Embedding、HNSW 建索引、确认动作及最终 JSONL 写入仍串行。结果始终按冻结数据集顺序落盘，单条 P50/P95/P99 口径不变。

RAGAS 继续只读取冻结回答，默认 `RAGAS_BATCH_SIZE=16`、`RAGAS_MAX_WORKERS=8`；如出现 429、超时或 Judge 不稳定，可先降为 4。并发只缩短全量墙钟时间，不改变 token、单条延迟、Recall 或回答质量的统计口径。

## 3. 固定指标口径

主报告与简历候选只发布下列 7 个指标。意图、路由、工具、参数、安全、token、成本和 fallback 等字段继续保留在运行产物中用于诊断，但不在主报告的结果表中并列展示。

| 指标 | 固定定义 |
| --- | --- |
| 最终回答正确率 | 必需事实全部正确、禁止声明未出现、回答状态正确且事实来源绑定正确的任务比例。它是合成业务 Gold 下的工程正确率，不是临床准确率。 |
| 端到端任务成功率 | 意图、路由、工具、参数、最终回答、安全、确认和成员隔离全部通过的任务比例。缺任一硬门即失败。 |
| Recall@K | `Top-K 中命中的相关 Chunk 数 / 全部相关 Chunk 数`；固定报告 K=3/5/10。 |
| Precision@K | `Top-K 中相关 Chunk 数 / K`；固定报告 K=3/5/10。无答案场景单独处理，不混入 Recall/Precision。 |
| Faithfulness | RAGAS 独立 Judge 判断回答声明可由检索上下文支持的平均分；解析失败项记 N/A 并从分子、分母同时排除，不得记 0。 |
| Response Relevancy | RAGAS 独立 Judge 判断回答与用户问题相关程度的平均分；缺失项处理同上。 |
| 端到端延迟 | 每条任务 wall-clock 延迟的 P50/P95/P99。必须同时记录运行环境，不能直接当作生产 SLA。 |

## 4. 2026-08-12 5A-9 当前基线

历史 1,200 条 Agent Query 已完成 PostgreSQL 隔离事务和实际 `UnifiedHealthGraph` deterministic 集成复测；当前活动评测固定为 fast-400，后续确定性和真实 LLM 运行均只读取这 400 条。本次已先完成 3 条真实 LLM 冒烟，再按 development/validation/holdout 分批完成 400 条真实 LLM 评测。本轮只测量真实模型链路，不进入 RAG/提示词优化。

### 4.1 Agent 全量集成：最终回答、任务成功与延迟

| 指标 | 当前结果 | 有效样本 | 说明 |
| --- | ---: | ---: | --- |
| 最终回答正确率 | 100.00% | 400 | 按必需 Claim、来源绑定和安全合同自动评分；是合成业务 Gold 下的工程正确率，不是临床准确率。 |
| 端到端任务成功率 | 99.25% | 400 | 397/400 条通过全部自动硬门；3 条因远程 Provider timeout/HTTP error fallback 失败。 |
| 端到端延迟 P50/P95/P99 | 4,294 / 6,645 / 7,850 ms | 400 | PostgreSQL + UnifiedHealthGraph + 真实远程模型本机 wall-clock。 |

**为什么最终回答正确率和任务成功率很高。** 这 400 条是互联网医院业务流程的冻结 WorldState Gold，不是开放式医疗问答：成员、处方、药箱、确认状态和期望来源均已定义。最初的问题不是模型医学知识不足，而是“阻断”与“等待确认”混用、空知识被当成成功、`search_safety_knowledge` 没有读取 case-scoped RAG，以及一个领域失败时 Supervisor 提前中断独立只读步骤，导致业务合同与运行结果不一致。改动是将空来源改为 fail-closed，固定阻断/确认边界，让知识工具只读当前 Case 的检索器，并按冻结 DAG 保留独立只读分支。完成后最终回答合同正确率达到 100.00%，端到端任务成功率达到 99.25%（397/400）；没有可比的“修复前最终回答分数”，因为修复前 Gold 与运行合同本身不一致，不能伪造提升百分点。

**延迟结论。** 当前真实 LLM Agent 链路的端到端 P50/P95/P99 为 4.294/6.645/7.850 秒。这是首次按统一 fast-400 完整测得的延迟基线，尚无同环境的优化前对照；因此只能写“当前测得”，不能写“延迟降低”。

### 4.2 RAG 策略优化：问题、改动与保留结论

本小节是 5A-9 内的策略验证，不新增路线图阶段。所有实验固定读取同一 125 个基础 Case / 500 条 Query；检索指标只统计 260 条有相关 Chunk 的 Query，回答指标只统计 320 条 RAG 回答 Query。没有新增人工审核门，也没有修改 Gold。

| 问题 | 最小改动 | 实现方式 | 是否保留 |
| --- | --- | --- | --- |
| 规则编号、药品名等短实体被纯语义相似片段挤出前排，Recall@3 偏低 | 两路混合召回 | PostgreSQL 活动版本内并行执行 FastEmbed + pgvector HNSW 向量召回和 BM25 词法召回，以 RRF 融合 | 是 |
| 相似药品、相邻规则或无关片段污染候选，Precision@K 偏低 | 过滤、轻量 rerank、去重 | 显式实体先过滤；候选 20 条内按实体精确命中、双路命中、词项覆盖和 RRF 分数重排；仅删除同一 Chunk 的重复来源 | 是 |
| 一个文档被切分后，子片段命中但模型缺少规则主干 | 父文档证据优先 | 命中显式实体时优先输出同文档最小 `chunk_index` 的主片段；综合问题可保留紧邻的补充片段。这是按文档结构的通用规则，不按 Gold ID 写死 | 是，限当前合成语料验证 |
| 模型把相似证据补成完整事实 | 忠实度提示词收紧 | 要求逐项绑定 `claim_texts` 与 `cited_chunk_ids`，证据不完整必须 `no_answer`，不得以常识或相似规则补齐 | 单独实验不保留；仅作为组合方案的防护提示 |

#### 4.2.1 量化结果

| 指标 | 旧冻结基线 | 混合检索 + rerank（retrieval-only） | 最终组合（真实 LLM） | 相对旧基线 |
| --- | ---: | ---: | ---: | --- |
| Recall@3 | 67.50% | 100.00% | 100.00% | +32.50 个百分点 |
| Recall@5 | 85.19% | 100.00% | 100.00% | +14.81 个百分点 |
| Recall@10 | 95.38% | 100.00% | 100.00% | +4.62 个百分点 |
| Precision@3 | 25.00% | 43.59% | 43.59% | +18.59 个百分点 |
| Precision@5 | 21.38% | 26.15% | 26.15% | +4.77 个百分点 |
| Precision@10 | 12.46% | 13.08% | 13.08% | +0.62 个百分点 |
| 来源绑定回答正确率 | 63.75% | 不调用 LLM | 74.69% | +10.94 个百分点 |

最终组合的真实 LLM 运行共 500 条 Query、360 次模型调用，其中 358 次为真实 Provider，完整 usage 覆盖率 99.44%，fallback 为 0.56%。平均单次调用为输入 671.285、输出 131.405、总计 802.690 token，平均观测成本 `$0.0009341`；相对旧基线平均总 token 增加 18.70%、平均成本增加 15.51%。原因是证据核对提示词更长，不能把本轮回答质量提升写成成本优化。

本次端到端 P50/P95 为 1,566.341 / 2,713.646 ms，旧基线为 1,482.244 / 2,187.268 ms，分别上升 5.67% / 24.98%。本轮本地 CUDA 依赖未加载成功而回退 CPU，运行环境与旧基线不同，故不把这组延迟差异归因为检索策略，也不宣称性能提升。

#### 4.2.2 忠实度提示词的单变量结论与 RAGAS 状态

仅启用提示词、保持旧检索候选策略的 500 条真实 LLM 实验中，回答正确率为 65.94%（较旧基线 +2.19 个百分点），但确定性来源绑定幻觉率为 8.13%（较旧基线 +0.63 个百分点）。该单变量没有同时改善正确率和幻觉率，因此不作为单独保留项；最终组合的提升不能单独归因于提示词。

历史独立 Judge 的共同完整样本为 300 条：Faithfulness `0.6166`、Response Relevancy `0.4316`、Context Recall `0.6700`。本次最终组合已按“只复用冻结回答与来源、不重跑 Embedding/HNSW/目标回答模型”的方式发起 RAGAS 复评，但 Judge 服务返回账户计费不可用，未生成可解析结果。因此本轮 Faithfulness、Response Relevancy 与 Context Recall 均为 **N/A**，从统计中排除，不记为 0，也不把确定性幻觉率 0.00% 等同于新的 RAGAS Faithfulness。

本轮 retrieval-only 首次实现曾出现 Recall@3 13.85% 的无效结果（BM25 对文档元数据区分不足）；调整 BM25 的 Chunk 内容权重后，未使用主片段优先的版本仍只有 Recall@3 60.38%。二者均未保留，完整过程仅留在执行历史。当前 100% 是冻结合成语料上的工程指标：现有正样本的 Gold 均位于文档主片段或紧邻补充片段，不能外推为真实医疗语料的临床召回率，后续必须以新增、独立标注的真实风格语料复验。

#### 4.2.3 Precision 标签扩充与复测

原冻结 Gold 的 Precision@3 `43.59%`、@5 `26.15%` 并不表示排序仍有大量错误：260 条正样本一共只有 340 个相关 Chunk，而指标要求固定返回 K 条并固定以 K 为分母。因此其理论上限分别为 `340 / (260 × 3) = 43.59%`、`340 / (260 × 5) = 26.15%`；旧口径只给每题平均 1.31 个相关 Chunk，却要求计算 Top-3/5。

按“无需人工审核”的测试环境规则，本轮在**同一统一数据集**中对 65 个正样本基础 Case 使用真实模型自动补充同版本文档中的定义、条件、步骤和例外证据。自动标注协议限制每个角色最多一个 Chunk、每题最多 4 条互补证据；65/65 条成功、无 fallback，最终每题平均 3.95 个自动扩展证据。原有 `relevant_chunk_ids` 完全保留，新增 `auto_expanded_relevant_chunk_ids`、`label_provenance=ai_auto_generated_no_human_review` 和模型/提示词版本，四种 Query 表达继承同一基础 Case 标签。

| Precision 口径 | @3 | @5 | @10 | 含义 |
| --- | ---: | ---: | ---: | --- |
| 原冻结 Gold | 43.59% | 26.15% | 13.08% | 只把核心必需 Chunk 作为相关证据；用于保持历史基线可复现。 |
| AI 自动扩展证据 | 60.51% | 50.15% | 31.81% | 在相同 retrieval 结果上，用自动补充的多证据标签复算；用于诊断检索结果是否覆盖定义/条件/步骤/例外。 |

该变化是**评测标签覆盖提升**，不是 BM25、向量、RRF 或 rerank 再次提升，不能写成“Precision 因模型优化提升了 X 个百分点”。自动标签没有人工审核，也不能替代正式临床或人工 Gold；若未来需要把 Precision 作为对外或简历核心成果，应重新建立独立人工/专家 Gold。当前简历仍优先写可比的 Recall 与来源绑定回答正确率。

#### 4.2.4 Cross-Encoder rerank 对照：不保留

为检验“用深度语义相关性重排 Top-10”能否提高 Precision，本轮使用 `BAAI/bge-reranker-base` 对**同一份已冻结候选**逐对打分；它不新增候选、不调用回答模型，也不改写任何 Gold 或自动扩展标签。由于当前运行环境只有 CPU，先完成 15 个基础 Case、60 条 Query 的可复现实验；结果如下。

| 指标口径 | 原组合排序 | Cross-Encoder 后 | 变化 |
| --- | ---: | ---: | ---: |
| 自动扩展证据 Precision@3 | 60.56% | 17.78% | -42.78 个百分点 |
| 自动扩展证据 Precision@5 | 53.33% | 23.67% | -29.66 个百分点 |
| 自动扩展证据 Precision@10 | 30.83% | 30.83% | 0.00 个百分点 |
| 原冻结 Gold Precision@3 | 33.33% | 0.00% | -33.33 个百分点 |
| 原冻结 Gold Precision@5 | 20.00% | 0.00% | -20.00 个百分点 |
| 原冻结 Gold Precision@10 | 10.00% | 10.00% | 0.00 个百分点 |

原因是通用 Cross-Encoder 能识别“同一主题”的片段，却没有理解本项目中“当前生效版本的规则主片段优先于同文档补充片段”的业务排序约束，因而把原先已排首位的主规则挤到后面。结论：**不接入当前 RAG 主链路、不写入简历、不继续消耗资源跑余下分片**。如后续要再尝试，应以医疗规则问句-Chunk 成对样本微调或替换为中文医疗领域 Cross-Encoder，并将版本、实体和主片段特征作为重排特征；这属于新一轮模型方案，不能与当前最小改动混在一起。

#### 4.2.5 真实 LLM 候选重排对照：不保留

本轮再用 `deepseek-v4-flash` 在同一份冻结 Top-10 上做受限重排。提示词明确规定：只可输出候选 ID 的完整新排列，不能新增 Chunk、不能回答医疗问题；排序时优先当前规则主定义、适用条件、步骤、例外和精确实体，并将目录/背景/仅主题相近片段后置。先完成 1 个基础 Case、4 条 Query 冒烟，4/4 返回合法排列、无 fallback；再完成与 Cross-Encoder 完全相同的 15 个基础 Case、60 条 Query 对照。

| 指标口径 | 原组合排序 | 真实 LLM 重排 | 变化 |
| --- | ---: | ---: | ---: |
| 自动扩展证据 Precision@3 | 60.56% | 55.00% | -5.56 个百分点 |
| 自动扩展证据 Precision@5 | 53.33% | 49.33% | -4.00 个百分点 |
| 自动扩展证据 Precision@10 | 30.83% | 30.83% | 0.00 个百分点 |
| 原冻结 Gold Precision@3 / @5 / @10 | 33.33% / 20.00% / 10.00% | 33.33% / 20.00% / 10.00% | 持平 |

60 条运行的合法完整排列率为 96.67%，真实 Provider 成功率 100%，有 1 条因输出排列不合法自动回退原排序。每条额外平均消耗 2,850 token、延迟 2.12 秒。因此该 LLM 虽能表达业务约束，却没有在当前已经包含实体过滤、规则重排与主片段优先的候选排序上带来增益，且额外成本和延迟很高。结论：**不接入 RAG 主链路，不跑余下 200 条 Query，不写入简历**；仅保留为可复现的否定实验。未来只有在候选数大幅增加、存在复杂跨文档规则冲突，并以独立人工 Gold 验证有净收益时，才考虑把 LLM 用作低频、异步的末级 rerank，而非默认在线链路。

#### 4.2.6 真实 LLM 查询扩展对照：仅留作离线诊断

本轮不让 LLM 读取知识库，也不让它回答问题；它只在检索前将原问句中已经出现的规则编号、药品名、剂型/规格、频次、动作和条件规范化为检索词。原问句始终原样保留，扩展词仅作为 BM25 + HNSW + RRF 的附加查询视图；Provider 超时、格式失败或 fallback 时严格只用原问句检索，不能把 fallback 文本带入查询。

先完成 4 条 Query 冒烟，再将 15 个基础 Case 拆成 3 个独立分片，合计 60 条 Query。全部真实扩展成功、无 fallback；结果如下。

| 指标口径 | 原组合检索 | 查询扩展后 | 变化 |
| --- | ---: | ---: | ---: |
| 自动扩展证据 Precision@3 | 60.56% | 64.45% | +3.89 个百分点 |
| 自动扩展证据 Precision@5 | 53.33% | 54.33% | +1.00 个百分点 |
| 自动扩展证据 Precision@10 | 30.83% | 31.83% | +1.00 个百分点 |
| 原冻结 Gold Recall@3/@5/@10 | 100% / 100% / 100% | 100% / 100% / 100% | 持平 |
| 原冻结 Gold Precision@3/@5/@10 | 33.33% / 20.00% / 10.00% | 33.33% / 20.00% / 10.00% | 持平 |

查询扩展平均新增 220 token、1.88 秒；检索本身平均约 0.19 秒。提升只发生在“AI 自动扩展证据”标签上，且原冻结 Gold 已受每题核心证据数量的固定分母上限约束，因而没有形成正式 Precision 或 Recall 的净提升。结论：**不作为默认在线前置节点，也不写入简历**；可保留为离线分析工具。若后续建立独立人工多证据 Gold，且在完整独立集合上证明收益覆盖成本和延迟，再重新评估是否用于只含短实体、低置信度的检索请求。

#### 4.2.7 结构化过滤 + 父子 Chunk 检索核验：现有链路已等价覆盖

本轮按“子 Chunk 定位、父规则主片段承载上下文”的思路做了独立 profile 对照：结构化过滤只使用问句中可确定提取的显式实体；候选仍由 BM25 + HNSW + RRF 的子 Chunk 检索产生，回答前将同文档最小 `chunk_index` 作为父主片段，并仅在综合问题中保留实际命中的补充子片段。

核验发现，这不是当前项目的新策略：现有 M5 已经通过**显式实体过滤、候选 20 条规则重排、文档主片段优先和最小证据门**实现了等价行为。在 15 个基础 Case、60 条 Query 上，原组合与父子 profile 的模型输入证据 Chunk 为 `60/60` 完全一致；父主片段均已排在第 1 位。因此 retrieval-only 的冻结 Gold Recall@3/@5/@10 和 Precision@3/@5/@10 均完全持平（100% / 100% / 100%，33.33% / 20.00% / 10.00%）。

真实 LLM 对照中，原组合在这 60 条为 100% 来源绑定回答正确率；父子 profile 首跑为 98.33%，仅因首条 Provider 偶发 fallback，单条重跑恢复为 100%。去除该 Provider 失败后，两者回答质量相同；父子 profile 的真实 Provider 输入 token 由 37,755 降至 30,816，但这是同一证据 ID 在不同运行中序列化与模型计量差异，且没有可独立归因的上下文集合变化，**不能宣称成本优化**。

结论：不保留重复 profile，不改主链路，也不写入简历；当前主链路已具备“子 Chunk 召回定位 + 父主片段优先 + 按需最小补充证据”的等价能力。真正的父子检索升级需先引入显式 `parent_chunk_id` / `section_id` 元数据与独立人工多证据 Gold，再验证它是否对真实多章节文档有增益。

### 4.3 七项发布指标：业务问题、改动和简历使用边界

| 指标 | 原来的业务问题 / 旧做法 | 本次策略改动 | 当前结果与简历使用 |
| --- | --- | --- | --- |
| Recall@3/@5 | 纯向量语义召回容易把“同类药品、相近规则”排在规则编号、药品名等精确实体前；旧混合检索的词法路由对短实体区分不足。 | 活动版本内并行 BM25 与 HNSW 向量召回，RRF 融合；再做实体过滤、候选 20 条轻量 rerank 和主片段优先。 | 从 67.50%/85.19% 提升到 100%/100%，可写为冻结合成语料上的检索工程结果。 |
| Precision@3/@5 | Query 平均仅标注 1.31 个相关 Chunk，却强制返回 3/5 条并按固定 K 作分母，天然拉低数值。 | 同一数据集上用真实模型自动补充定义/条件/步骤/例外证据，每题最多 4 条；不改写原冻结 Gold。 | 原 Gold 为 43.59%/26.15%；AI 自动扩展证据为 60.51%/50.15%。这是标签覆盖变化，不写成检索模型提升。 |
| RAG 来源绑定回答正确率 | 相似药品和相邻规则进入上下文后，模型会把局部证据拼成完整规则或引用错来源。 | 检索侧减少无关证据；生成侧要求 Claim 和 chunk 来源一一绑定，证据不足必须无答案。 | 从 63.75% 提升到 74.69%，可作为“RAG 来源绑定回答正确率”写入，不能和 Agent 合同正确率混为同一指标。 |
| Faithfulness | 需要独立 Judge 判断“回答声明是否由上下文支持”，不是确定性来源绑定检查可以替代的。 | 加入来源逐项核对提示词，并保留冻结结果离线 Judge 复评能力。 | 历史共同样本为 0.6166；当前组合 Judge 不可用，结果 N/A。恢复 Judge 前不写分数，只可写“接入 RAGAS 离线评测”。 |
| Response Relevancy | 需要独立 Judge 判断回答是否真正回应用户问题，不能由检索命中或业务合同代替。 | 与 Faithfulness 同样使用独立 RAGAS Judge 和冻结回答复评。 | 历史共同样本为 0.4316；当前组合为 N/A。恢复 Judge 前不写分数。 |
| Agent 最终回答正确率 | 原问题是业务运行合同不一致：阻断/确认混用、空知识被当成功、知识工具没有 case 隔离、失败后提前终止独立步骤。 | 空来源 fail-closed；固定阻断与确认边界；case-scoped RAG；Supervisor 按冻结 DAG 保留独立只读步骤。 | 当前为 100.00%（400 条冻结 WorldState Gold）；修复前没有可比有效分数，因此写“达到”而不是“从 X 提升”。 |
| 端到端任务成功率 | 除回答外还会被 Provider 超时、HTTP 异常和结构化 fallback 影响。 | 通过有界 DAG、失败记录与可恢复批次运行稳定链路；仍不将远程 Provider 故障伪装为成功。 | 当前 99.25%（397/400）；没有修复前同口径对照，因此写“达到”而不是虚构提升。 |
| 端到端延迟 | 之前没有在同一 fast-400、真实 LLM、PostgreSQL 全链路条件下留下可比较基线。 | 本次只完成统一测量和分批受控并发，不把硬件或缓存差异当成算法优化。 | P50/P95/P99 为 4.294/6.645/7.850 秒；可写“当前测得 P95 6.65 秒”，不能写“降低”。 |

## 5. 当前固定指标完成情况

| 目标 | 需要补数据集 | 需要补代码或运行 |
| --- | --- | --- |
| 真实模型 Agent 最终回答、延迟和 token | 无 | 已完成 400 条真实 LLM 输出的冻结 Gold 自动评分；不需要人工复核。 |
| 独立 Judge 的两个 RAGAS 指标 | 无 | 历史 300 条共同样本已有结果；本轮最终组合因 Judge 账户计费不可用为 N/A，已从分子、分母排除，待 Judge 恢复后可直接复用冻结结果补评。 |
| 回答与端到端契约校准 | 无 | 已完成 Gold 过时/实现错误分类与确定性修复；当前最终回答、端到端和四类校准指标均为 100%。 |

只有后续新增工具、业务意图或参数类型超出现有 Gold 覆盖时，才在这一个统一数据集中追加带标注样本并重新冻结 manifest/hash。

## 6. 文件、运行与结果路径

- 数据集：`output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/`
- 数据生成：`scripts/build_unified_evaluation_dataset.py`
- 本次指标聚合：`scripts/run_unified_metric_baseline.py`
- 本次结果：`output/benchmarks/evaluation_runs/unified-metric-baseline-fast400-real-20260812-v2/`
- Agent 历史 1,200 结果：`output/benchmarks/evaluation_runs/unified-agent-1200-integration-20260812-calibrated-final5/`（仅历史）
- Agent 当前 fast-400 结果：由默认命令输出到 `output/benchmarks/evaluation_runs/unified-agent-400-20260812/`
- Agent 真实 LLM fast-400 自动 Gold 全量结果：`output/benchmarks/4d-b3-real-llm-fast-400-gold-20260812-v2/`
- Agent 真实 LLM 分批结果：`output/benchmarks/4d-b3-real-llm-fast-400-*-20260812/`
- 旧冻结 RAG 基线：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-final-gpu-full-20260807/`
- 本轮混合检索 retrieval-only：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/`
- 本轮最终组合真实 LLM：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-optimized-full-no-ragas-20260812/`
- 本轮提示词单变量：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-faithfulness-prompt-full-no-ragas-20260812/`
- 自动扩展证据标签：`output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag/labels/auto_expanded_evidence.jsonl`
- 自动扩展证据 Precision 复测：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/auto_expanded_precision_summary.json`
- Cross-Encoder 反证实验（60 Query）：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/cross-encoder-rerank/part-00/`
- 真实 LLM 重排反证实验（60 Query）：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/llm-rerank-v2-part-00/`
- 真实 LLM 查询扩展实验（60 Query，三分片汇总）：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/query-expansion-v1-part-00-retry-merged.json`
- 父子证据等价核验（60 Query）：`output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-parent-child-full-60-20260813/`
- 历史冻结 RAGAS：`output/benchmarks/rag_synthetic/rag-synthetic-v1-ragas-offline-full-fix-retry-20260810/`

```powershell
.venv\Scripts\python.exe scripts\run_unified_metric_baseline.py

.venv\Scripts\python.exe scripts\run_unified_agent_eval.py --mode integration --identity-map output\benchmarks\evaluation_runs\unified_agent_identity_map.local.json --split all --concurrency 4 --output-dir output\benchmarks\evaluation_runs\unified-agent-400-20260812

# 真实 LLM：先冒烟，再按 split 分批；最终汇总已由 merge_4d_b3_fast400_reports.py 生成
.venv\Scripts\python.exe scripts\run_4d_b3_real_llm.py --live --identity-map output\benchmarks\evaluation_runs\unified_agent_identity_map.local.json --split development --max-cases 3 --concurrency 4 --output-dir output\benchmarks\4d-b3-real-llm-fast-400-smoke-20260812
.venv\Scripts\python.exe scripts\run_synthetic_rag_full_eval.py --all --profile m5-hybrid-rerank --retrieval-only --reuse-index --concurrency 4 --output-dir output\benchmarks\rag_synthetic\rag-synthetic-v1-m5-hybrid-rerank

$env:RAGAS_ENABLED='false'
.venv\Scripts\python.exe scripts\run_synthetic_rag_full_eval.py --all --profile m5-optimized --reuse-index --concurrency 4 --output-dir output\benchmarks\rag_synthetic\rag-synthetic-v1-m5-optimized

# 只对已冻结的 retrieval_results.jsonl 自动补充同一数据集的多证据标签并复算 Precision；不重跑检索或回答模型
.venv\Scripts\python.exe scripts\expand_rag_auto_evidence_labels.py --concurrency 4
.venv\Scripts\python.exe scripts\run_rag_cross_encoder_rerank_eval.py --case-start 0 --max-cases 15 --batch-size 32
.venv\Scripts\python.exe scripts\run_rag_llm_rerank_eval_v2.py --case-start 0 --max-cases 15 --concurrency 4
$env:MODEL_TIMEOUT_MS='30000'
.venv\Scripts\python.exe scripts\run_rag_query_expansion_eval.py --case-start 0 --max-cases 5 --concurrency 1
.venv\Scripts\python.exe scripts\merge_4d_b3_fast400_reports.py --output-dir output\benchmarks\4d-b3-real-llm-fast-400-final-20260812
.venv\Scripts\python.exe scripts\score_frozen_fast400_real_llm.py --output-dir output\benchmarks\4d-b3-real-llm-fast-400-gold-20260812-v2

$env:PYTHONPATH='E:\project_code\hospital\backend'
.venv\Scripts\python.exe -m pytest backend/tests/test_unified_metric_baseline.py backend/tests/test_unified_evaluation_dataset.py backend/tests/test_frozen_ragas_eval.py backend/tests/test_rag_synthetic_full_eval.py -q -p no:cacheprovider
```

历史实验与优化过程只保留在 [项目执行历史](EXECUTION_HISTORY.md) 中，不再混入当前指标主文档。

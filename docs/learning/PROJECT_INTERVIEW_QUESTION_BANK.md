# 项目面经问题库

## 1. 这份文档怎么维护

这不是一份一次性“标准答案”，而是本项目持续增长的面试知识库。以后你把面经原文发来时，按以下规则更新：

1. **必须保留原句**：不把面试官问题只改写成概念标题；原句决定你在现场应该调用哪条回答。
2. **先归并，再新增**：意思相同或考察点相近的问题，追加到已有主题的“原题原句”，只维护一套核心回答。
3. **答案绑定项目证据**：回答只描述当前仓库真实实现，并给出代码或文档入口。
4. **未使用必须标记**：不能为了面试把“了解过”说成“项目使用过”。
5. **新增技术先讨论**：先判断它解决什么真实问题、学习价值、资源成本和路线图影响，再决定略过、只学习或实现。
6. **指标必须有报告**：没有对应环境、样本和报告，不声称准确率、安全率、延迟或成本。

技术状态使用以下标记：

| 状态 | 含义 | 面试表达 |
| --- | --- | --- |
| `已实现` | 代码、测试和文档都存在 | 可以讲设计、实现和验证边界 |
| `部分实现` | 只有部分链路或本地能力 | 明确已完成与未完成 |
| `历史方案` | 曾用 Dify 等方式设计，但当前仓库已自研 | 分开讲历史原型与当前实现 |
| `仅学习` | 为理解对比而学习，项目未使用 | 可以讲取舍，不能写成技术栈 |
| `候选` | 有业务价值，但需先进入路线图 | 先讨论，不立即加代码 |
| `明确不做` | 与医疗边界、MVP 或资源约束冲突 | 解释为什么不做 |

快速导航按主题组织，面试官换一种问法时，先定位主题，再调用同一套项目证据：

- [RAG 与模型](#2-rag-与模型)
- [Dify、环境与业务闭环](#3-dify环境与业务闭环)
- [后端基础](#4-后端基础)
- [上下文与记忆](#5-上下文与记忆)
- [多-Agent-编排](#6-多-agent-编排)

---

## 2. RAG 与模型

### Q01 RAG 是否一定需要 Embedding

**项目状态：** `已实现`。默认关键词检索；可选 FastEmbed + pgvector 向量召回。RAGFlow 为 `仅学习/当前略过`。

### 原题原句

> “我们的rag是怎么实现的，不用embedding模型吗？”

### 30 秒回答

RAG 的本质是“回答前先检索可追溯资料”，不等于必须向量化。项目最初用 PostgreSQL 关键词检索作为确定性基线，始终保留 `source_id/document_id/chunk_id`；4A 又增加 FastEmbed 的 `BAAI/bge-small-zh-v1.5` 和 pgvector 精确余弦检索，解决中文同义表达难以关键词命中的问题。向量后端只返回指针，正文仍从审核后的知识表回填；模型或索引异常时回退关键词。因此我们现在是真实双模式 Hybrid RAG，但默认模式不下载 Embedding。

### 2 分钟项目回答

我把 RAG 拆成“知识准备、查询编码、候选召回、来源回填、融合和降级”六步。知识块在 PostgreSQL 中保存正文与审计字段，索引脚本用 passage embedding 写入 512 维 pgvector；用户查询使用 query embedding。向量查询只返回 chunk 指针和相似度，Retriever 再按指针从权威表加载正文，防止向量库成为第二份不可审计事实。

关键词与向量不是互相替代。关键词适合药名、规则关键词和稳定回归；向量适合同义改写。小型已审核知识库只有少量 chunk，因此使用 PostgreSQL 内精确余弦距离，不提前引入独立向量服务和 ANN 索引。`RAG_VECTOR_ENABLED=false` 时不加载模型；启用时模型按需加载，缓存到 E 盘项目 `var/models/fastembed`。向量失败会记录 fallback reason，而不是悄悄变成关键词结果。

没有选择 RAGFlow，是因为它是一套包含多组件的知识平台，而当前需求只是已审核小知识库的轻量召回。额外部署会增加内存、磁盘和运维成本，却暂时没有文档解析、多人知识运营等真实需求。

### 技术原理怎么理解

```text
关键词检索：query 与文本直接匹配
向量检索：query -> 数字向量；chunk -> 数字向量；比较语义距离
RAG：检索结果 + 来源 -> Agent 上下文 -> 生成/模板回答
```

Embedding 模型不是聊天模型。它不负责写答案，只负责把语义映射到向量空间。pgvector 不是知识库正文的替代品，它负责保存向量并计算距离。

### 代码证据

- [Embedding provider](../../backend/app/rag/embedding_provider.py)
- [pgvector 查询与索引](../../backend/app/rag/vector_store.py)
- [Hybrid Retriever](../../backend/app/rag/retriever.py)
- [向量字段 migration](../../backend/alembic/versions/0003_lightweight_vector_rag.py)
- [完整 RAG 设计](../RAG_RETRIEVAL.md)
- [当前 RAG 设计与验证边界](../RAG_RETRIEVAL.md)

### 怎么理解和记忆

记住：**“词保底，向量补语义，指针保审计，失败要降级。”**

不要背“RAG = 向量数据库”。先说目标是检索证据，再说项目为何同时保留关键词和向量。

### 可能追问

**为什么不用 Elasticsearch/Qdrant/Milvus？**  
当前数据小、已有 PostgreSQL，pgvector 减少一套服务；数据规模、过滤复杂度或召回吞吐达到明确瓶颈后再评估独立服务。

**为什么没有 reranker？**  
当前知识块太少，先用可解释的精确检索。增加 reranker 应由离线召回评估证明有收益，不因“技术栈更丰富”而增加。

**向量分数是不是医疗正确率？**  
不是。它只是相似度，不代表事实正确、答案安全或临床有效。

---

### Q02 项目是否调用真实 LLM，Key 在哪里填

**项目状态：** `已实现`。双模式 Runtime、诊断、真实模型小样本评测和人工审核冻结均已实现。

### 原题原句

> “然后我们的问答你也没有像我要api，我们没有调用大模型吗”

### 30 秒回答

项目默认不调用真实 LLM，这是为了让测试和演示在无 Key、无网络时可重复。4B 已把 OpenAI-compatible provider 接入 LangGraph 的真实 Runtime；在根目录未提交的 `.env` 填模型地址、Key 和模型名后，FinalAnswer 节点才调用真实模型。输出必须通过 JSON、Pydantic 和安全检查；超时、HTTP、schema 或 safety 失败会留下 Trace 并回退 deterministic。我已用本机私密配置完成 8 条 `deepseek-v4-flash` development 样本并人工复核，但只把这 8 条固定范围的结果作为证据。

### 2 分钟项目回答

我没有让 LLM 控制整条业务链。Planner、成员隔离、工具权限、RAG、SafetyAgent、确认状态机和 Evaluator 都是确定性代码；模型只根据冻结的最小任务信息生成结构化 FinalAnswer 草稿。这样即使模型不可用，业务边界也不会消失。

`create_model_gateway()` 根据环境变量选择 provider。默认 `deterministic` 完全离线；`openai_compatible` 创建 HTTP provider，并把 deterministic 作为 fallback。Gateway 不直接信任返回字符串，而是先解析 JSON，再交给目标 Pydantic schema，最后执行输出安全检查。每次尝试记录 requested/effective provider、schema、安全、错误类型、耗时和是否 fallback，但不保存 Key、完整 prompt 或原始 provider 文本。

诊断命令默认不联网；只有加 `--live` 才发送一次非医疗结构化请求。诊断会单独看 primary attempt，因此外部模型失败后 fallback 返回答案，也不会被报告成“真实模型连通成功”。

### 在哪里填

只填本机根目录：

```text
E:\project_code\hospital\.env
```

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=your-real-key
MODEL_NAME=your-real-model-name
MODEL_TIMEOUT_MS=10000
```

### 代码证据

- [Gateway 与 provider](../../backend/app/agent/model_gateway.py)
- [模型配置](../../backend/app/core/config.py)
- [运行时 FinalAnswer 接线](../../backend/app/agent/langgraph_workflow.py)
- [诊断器](../../backend/app/agent/model_provider_diagnostic.py)
- [运行服务与资源释放](../../backend/app/services/agent_runtime_service.py)
- [配置操作手册](../LLM_CONFIGURATION.md)
- [当前 Model Gateway 设计](../MODEL_GATEWAY.md)

### 怎么理解和记忆

记住：**“默认不调，配置才调；模型只写草稿，规则控制执行；先验再拦，失败可退，结果留痕。”**

### 可能追问

**为什么不用模型做 Planner？**  
当前四个场景有限，确定性 Planner 更可测试。以后若意图复杂，可以在同一 schema 后增加 LLM Planner，但仍需置信度、fallback 和固定评估。

**为什么不用厂商 SDK？**  
当前只需要 OpenAI-compatible 最小 HTTP 契约，`httpx` 更轻且易于 MockTransport 测试；厂商特有能力成为真实需求后再增加 adapter。

**你实际测过哪个模型？**  
如实回答：目前用 `deepseek-v4-flash` 跑通并冻结了 8 条 development 固定样本，真实 provider 生效 `8/8`、fallback `0/8`，人工对回答和冻结证据复核 `8/8` 通过；平均总 token `1032.5`，本机 model/workflow p95 为 `4452/5239 ms`。这不是厂商模型的通用能力或临床质量结论，只是当前固定集的本机证据。

### 4D-B3 怎么测真实 LLM、token 和成本

**原题原句：**

> “真实模型的效果、Token 和成本你怎么测？”

**回答：**

我没有把模型调用直接塞进普通自动化测试。项目用显式 live 的 B3 runner：先做非医疗结构化连通性检查，再让固定 v2 case 通过 PostgreSQL shadow transaction 和真实业务图运行。runner 只读取 Model Gateway 的脱敏 Observation，统计 provider 生效、fallback、usage、模型 p95 和整条任务 p95，并生成独立审核队列。人工审核完成后，finalizer 会校验队列没有改过答案、成员和来源，再冻结报告及 hash。当前 8 条 `deepseek-v4-flash` development 样本人工复核 `8/8` 通过，平均输入/输出/总 token 为 `599.75/432.75/1032.5`，平均成本 `$0.00146525`，本机 model/workflow p95 为 `4452/5239 ms`。面试时必须同时说明样本只有 8 条、只覆盖提醒和购药两个场景。

**怎么记忆：**

**“先连通，再固定样本；只读 usage，不猜 token；人工复核后冻结 hash；数字始终带样本范围。”**

---

## 3. Dify、环境与业务闭环

### Q03 当初用 Dify 怎样设计工作流

**项目状态：** `历史方案` + 当前 `已自研`。不能虚构原 Dify 生产日志或精确节点配置。

### 原题原句

> “项目的背景是，真实的业务流程，但是当初只用dify实现，面试中问到，当初用dify是怎么设计的，要怎么回答呢，我记得dify是什么大模型然后rag然后什么什么的，也就是整个流程，节点是怎么设计的？”

### 30 秒回答

当初 Dify 原型不是简单的“LLM 加 RAG”，而是把真实慢病事务拆成工作流节点：开始/用户输入、意图与成员识别、条件分支、档案/处方/药箱/库存工具、知识检索、安全判断、人工确认门和最终回答。高风险请求走安全拒绝，正常续方/复诊/提醒先整理证据并生成待确认草稿。后来我把这个可视化原型自研成 FastAPI + SQLAlchemy + LangGraph + Tool Registry + ContextManager + Harness，使权限、成员隔离、Trace、reset 和评估都能用代码测试和 review。

### 2 分钟项目回答

可以按下面的历史设计复盘，但要说明这是根据当时业务方案总结的节点链，不把没保留的 Dify 配置细节说成事实：

```text
Start / User Input
  -> 参数提取：member、药名、城市、动作
  -> 意图分类：续方 / 复诊 / 提醒 / 库存 / 高风险
  -> 条件分支
       -> 档案、处方、药箱、库存 API/工具
       -> 知识检索：续方 SOP、确认规则、安全规则
  -> 证据整理
  -> Safety 分支
       -> 高风险：拒绝自行调整并提示就医/人工处理
       -> 正常：生成待确认方案
  -> Human confirmation
  -> Final answer
  -> End
```

Dify 的价值是快速把节点和分支可视化，验证业务流程；不足是复杂成员隔离、工具契约、版本化 Trace、上下文 reset、固定 evaluator 和代码级回归不容易只靠画布治理。自研不是为了否定 Dify，而是需求从流程原型升级到了可审计工程系统。

当前 LangGraph 仍保留“有界工作流”思想：Planner 不自由循环，角色由意图路由，工具由 Registry 校验，所有路径经过 SafetyAgent，关键动作只能创建本地草稿，答案冻结后再 reset 和评估。

### 代码证据

- [当前与目标 Agent 架构](../AGENT_ARCHITECTURE.md)
- [LangGraph 节点实现](../../backend/app/agent/langgraph_workflow.py)
- [Tool Registry](../../backend/app/tools/tool_registry.py)
- [ContextManager](../../backend/app/agent/context_manager.py)
- [Dify 患者端医疗服务项目](DIFY_PROJECT_GUIDE.md)

### 怎么理解和记忆

用八个词复述节点：**“入、识、分、查、整、安、确、答。”**

- 入：用户输入；
- 识：意图和成员；
- 分：条件路由；
- 查：工具/RAG；
- 整：证据整理；
- 安：安全判断；
- 确：人工确认；
- 答：最终回答。

### 可能追问

**Dify 与 LangGraph 的区别？**  
Dify 更适合快速可视化原型和平台化配置；LangGraph 嵌入代码工程后，类型、测试、版本控制和复杂状态边界更直接。不是谁永远更好，而是项目阶段与治理要求不同。

**为什么不继续只用 Dify？**  
因为本项目要学习并证明 Context、Tool、Trace、成员隔离、确认状态机和 evaluator 的代码级设计，而不是只展示画布截图。

---

### Q04 当前是什么环境，为什么不是生产

**项目状态：** `已实现本地开发/集成/演示`；生产环境 `未实现`。

### 原题原句

> “现在是自己将这个实现，所以没有上线生存环境，所以我们现在是使用测试环境吗？”

### 30 秒回答

更准确地说，我们现在是本地开发与集成演示环境，不是生产环境。Docker Compose 启动 PostgreSQL、Redis、FastAPI 和 Next.js，用 seed 数据跑公开 API 和固定场景；pytest 使用隔离 SQLite 测试环境。它能证明本地功能、契约和回归，但没有真实患者流量、生产认证、HTTPS、秘密管理、高可用、监控告警和医疗合规验收，所以不能说“已上线生产”。

### 2 分钟项目回答

“环境”不是只有测试和生产两类：

| 环境 | 本项目现状 | 用途 |
| --- | --- | --- |
| 单元/自动化测试 | pytest + SQLite | 快速验证契约与失败路径 |
| 本地集成 | Docker PostgreSQL/Redis/backend/frontend | 验证迁移、SQL、网络和 API |
| 演示 | 同一本地 Compose + seed + 固定 Demo Runner | 面试或 review 可重复展示 |
| staging | 未建设 | 接近生产配置的预发布验证 |
| production | 未建设 | 真实用户与运维保障 |

测试通过不等于生产可用。生产还需要身份认证、权限审计、TLS、秘密管理、备份恢复、监控、容量、SLO、CI/CD、安全与医疗合规。这些不是“Docker 能启动”自动带来的。

### 代码证据

- [Compose 编排](../../docker-compose.yml)
- [本地部署指南](../LOCAL_SETUP_AND_DEPLOYMENT.md)
- [一键演示手册](../DEMO_RUNBOOK.md)
- [测试指南](../TESTING_GUIDE.md)

### 怎么理解和记忆

记住：**“测试证明代码路径，集成证明组件协作，生产还要证明长期运行和治理。”**

### 可能追问

**Docker Compose 算部署吗？**  
算本地容器化部署/编排，但不等于生产部署。

**如果要上生产先补什么？**  
先补真实认证授权、秘密管理、HTTPS、可观测性、备份恢复和合规边界，再讨论高可用与扩容。

---

### Q05 每日药量检查和提醒算不算 Loop

**项目状态：** Loop 思想 `部分具备`；定时任务与真实推送 `未实现`，当前为 `候选/先讨论`。

### 原题原句

> “最近有一个loop 工程也很火，我们的慢性病每日检查药量并推送提醒算不算loop工程”

### 30 秒回答

概念上它可以形成闭环：定时读取药箱和提醒状态，判断是否需要提醒，发送通知，记录送达/确认反馈，再更新下一轮任务。但当前项目只实现了药箱证据、提醒草稿、人工确认和本地状态，没有 scheduler、真实推送、送达回执或基于反馈的下一轮调度，所以只能说“具备闭环设计基础”，不能说完整 Loop 已实现。

### 2 分钟项目回答

一个真正的业务 Loop 至少需要：

```text
Trigger -> Observe -> Decide -> Act -> Verify -> Update -> Next trigger
```

映射到慢病提醒：

```text
每日定时触发
  -> 查询 member 药箱/提醒计划
  -> 判断剩余量和当日提醒
  -> Safety/规则检查
  -> 发送推送
  -> 接收送达、已读或用户确认
  -> 写审计和下一次时间
```

当前项目已具备 Observe 的 DB tools、部分 Decide 规则、人工确认草稿和 Trace，但 Act 只写本地 `not_submitted` 草稿，Verify/下一轮调度没有实现。医疗提醒还必须处理时区、重复发送、幂等、失败重试、成员隔离、静默时段和不能把“未点击”推断为“未服药”。

因此不为了追热点立刻加入消息队列和调度器。若将来路线图明确“真实提醒闭环”，可以先做本地 scheduler + fake notification adapter + delivery receipt，再决定 Celery/Redis Queue 等技术。

### 代码证据

- [提醒与工作流节点](../../backend/app/agent/langgraph_workflow.py)
- [确认草稿服务](../../backend/app/services/confirmation_draft_service.py)
- [医疗边界](../PRD.md)

### 怎么理解和记忆

记住七步：**“触、看、判、做、验、记、再来。”** 只有“定时检查并发送”还不完整，必须有反馈与下一轮状态。

### 技术取舍

- 面试是否要学：`要`，因为闭环、幂等、重试和可观测性是常见系统设计点。
- 现在是否要加：`暂不立即实现`，真实推送不属于当前 MVP。
- 何时加入：出现明确提醒闭环需求，并先更新总路线图和安全边界。

---

## 4. 后端基础

### Q06 后端为什么需要这些技术栈和分层

**项目状态：** `已实现`。MySQL、其他 Web 框架等对比属于 `仅学习`。

### 原题原句

> “我不太理解这些技术栈是什么意思，我看代码，比如query.q，这是很基本的语法，调用q方法，还有其他的rows=什么什么，就是赋值嘛，然后还有一些函数啊类啊什么的，都是一些python的语法，从哪里可以看出，我们使用了各种技术栈比如fastapi呢，我知道这个是get，但是get不就是请求http吗，怎么就fastapi了，那如果是别的技术栈，会是怎么写的，rustful api又是什么，api不就是api吗，PostgreSQL不就是数据库吗为什么是PostgreSQL，数据库不就是表然后有一些字段吗，mysql不也一样。怎么从代码体现出用了这个技术栈，为什么用这个技术栈不用别的。SQLAlchemy也一样，python没办法管理数据库连接吗，为什么我们有这么多的技术栈来实现各种功能，不是直接用代码语言python来实现吗，我感觉就好像import 什么什么库而已。”

> “现在有了codex，后端开发的基本要求是什么，你说的这些层，什么服务层业务层，到底有多少个层，每个层负责什么，代码方面是怎么样的，曾与曾之间什么关系，整条业务或者代码逻辑是什么样的”

### 30 秒回答

Python 是语言，技术栈是别人已经实现并验证的通用能力。FastAPI 把函数注册为 HTTP 路由并做依赖注入，Pydantic 校验请求/响应，SQLAlchemy 管理 ORM、查询、事务和连接，PostgreSQL 负责持久化、约束、并发与查询，Alembic 管理 schema 版本。分层的目标不是多建文件，而是让 HTTP、业务、数据契约和持久化各自可测试、可替换。Codex 能帮写代码，但开发者仍要定义边界、校验失败路径、review 安全与验证结果。

### 2 分钟项目回答

在 `knowledge.py` 里，`@router.get(...)` 是 FastAPI 提供的装饰器，告诉框架“收到这个 HTTP GET 路径时调用下面函数”。函数参数里的 `Query(...)`、依赖类型和 `response_model` 也由 FastAPI 读取。换 Flask、Django 或 Java Spring，注册路由和注入依赖的写法会变，但 HTTP GET 的协议含义不变。

这里还要纠正一个 Python 语法点：`query.q` 是“读取 `query` 对象的 `q` 属性”，不是调用 `q` 方法；方法调用会有括号，例如 `service.search(...)`。`rows = ...` 的确是赋值，但右侧可能触发一整条 Service 和数据库查询链，所以读代码不能只停在赋值语法，还要继续追右侧对象来自哪里、方法内部做了什么。

Pydantic schema 定义 API 边界允许哪些字段与类型；Service 承担“如何完成这个用例”；SQLAlchemy model 映射数据库表；Session 管理一组查询和事务。Python 标准库当然可以手写 socket、HTTP parser、SQL 字符串和连接池，但那会重复解决大量通用问题，还更容易产生安全与并发错误。使用库不是“没有写代码”，而是把精力放在本项目特有的成员隔离、来源、确认和安全规则。

项目的主要调用链：

```text
客户端
  -> FastAPI Router（HTTP）
  -> Pydantic DTO（数据契约）
  -> Service（用例/业务编排）
  -> SQLAlchemy Session + Model（事务与表映射）
  -> PostgreSQL（持久化）
  -> DTO
  -> JSON 响应
```

Agent 链再增加 ContextManager、Tool Registry、RAG、SafetyAgent、Model Gateway 和 Evaluator，但仍通过 Service/Repository 边界访问数据。

### 为什么选这些

| 技术 | 解决什么 | 为什么适合当前项目 |
| --- | --- | --- |
| FastAPI | HTTP 路由、校验集成、OpenAPI | Python 类型友好，Swagger 自动生成 |
| Pydantic | 运行时数据契约 | Agent/Tool/API 都需要严格结构化 |
| SQLAlchemy | ORM、查询、Session/事务 | SQLite 测试与 PostgreSQL 集成可共用主要模型 |
| Alembic | schema 版本迁移 | 每次字段变化可审计、可升级 |
| PostgreSQL | 持久化、约束、事务、JSON、pgvector | 同时承载业务表、审计与轻量向量 |
| Redis | 为缓存/任务基础设施预留 | 当前 MVP 使用有限，不夸大其作用 |
| LangGraph | 有界状态图 | 显式节点、条件边与冻结状态 |

MySQL 也能管理关系表，许多基础 API 完全可以使用。当前选择 PostgreSQL 不是因为 MySQL “不行”，而是 JSON/复杂查询/pgvector 和项目现有栈更统一。

### 代码证据

- [知识 API Router](../../backend/app/api/routes/knowledge.py)
- [知识 DTO](../../backend/app/schemas/knowledge.py)
- [知识 Service](../../backend/app/services/knowledge_read_service.py)
- [知识 Model](../../backend/app/models/knowledge.py)
- [数据库 Session](../../backend/app/core/database.py)
- [从 0 到 1 的任务拆分与技术选型](PROJECT_ENGINEERING_GUIDE.md)

### 怎么理解和记忆

把后端记成餐厅：**Router 接单，Schema 验单，Service 做菜，Model 是食材账本，Session 管理这一单，数据库是仓库。** 类比只用来建立第一印象，最终仍要沿真实代码调用链理解。

### 可能追问

**RESTful API 是什么？**  
它是一组围绕资源、HTTP 方法、状态码和无状态交互的设计风格，不是另一种“API 产品”。本项目 `/api/agent-runs/{run_id}` 把 run 当资源，GET 读取、POST 创建/续跑。

**有 Codex 后开发者还需要什么？**  
需求拆解、架构边界、数据与安全判断、测试设计、代码 review、故障定位和对结果负责。能生成代码不等于知道应该生成什么、是否正确或是否越权。

---

### Q07 客户端、API、依赖注入、Schema、Service、Model 分别是什么

**项目状态：** `已实现`。

### 原题原句

> “客户端是什么？在哪里体现？API层就是接受请求，调用服务，这种流程的，动作，对吗？什么叫依赖注入？数据契约曾就是定义要用到的变量，服务层就是具体做事的，这个方法要怎么实现，model就是数据库里有什么字段，我理解的对吗？”

> “db到底是什么”

### 30 秒回答

理解大体正确，但要再精确一点。客户端是发 HTTP 请求的一方，例如浏览器前端、Postman 或 Harness。API/Router 层负责把 HTTP 输入转换成 DTO、注入依赖、调用 Service 并返回状态码/DTO。Schema 不只是“变量”，而是跨边界的数据契约和校验规则。Service 实现用例并控制业务流程。Model 是数据库表的 ORM 映射。`db` 通常是 SQLAlchemy `Session`，代表本次请求使用的数据库工作单元，不是数据库本身。

### 逐个解释

**客户端**  
发请求的一方。项目中既有 Next.js 的 `fetch`，也有 Postman，还有 `RuntimeE2EHarnessRunner`。同一个 FastAPI endpoint 不关心是谁发，只关心 HTTP 契约。

**API/Router**  
声明方法、路径、query/path/body、response schema 和依赖。它不应该堆复杂 SQL 或业务判断。

**依赖注入**  
函数声明“我需要一个 `DbSession`”，FastAPI 在请求到来时创建/取得 Session，调用函数后再关闭。函数不用自己到处写 `SessionLocal()`，测试也能替换依赖。它是“由外部组装对象”，不是“import 依赖”。

**Schema/DTO**  
定义边界允许的数据结构、类型、必填项和验证规则。DTO 与 ORM 分开，避免数据库内部字段被自动暴露给客户端。

**Service**  
实现一个业务用例，例如“在当前 demo user 的成员范围中搜索知识”。它组织查询、权限、事务和错误，但不知道 HTTP 页面长什么样。

**Model**  
SQLAlchemy 类到数据库表/列/关系的映射。Model 说明数据怎样持久化，不代表 API 必须原样返回这些字段。

**`db` / Session**  
Session 持有数据库连接使用上下文、查询和事务状态。可以把它理解为“一次工作单元”：查询对象、暂存修改、commit/rollback；底层连接通常来自连接池。

### 一次知识搜索发生什么

```text
Postman GET /api/knowledge/search?q=确认
  -> FastAPI 匹配 @router.get
  -> 校验 query 参数
  -> get_db 创建并 yield Session
  -> Router 调 KnowledgeReadService(db).search(...)
  -> Service 用 SQLAlchemy 生成查询
  -> PostgreSQL 执行 SQL
  -> ORM rows 转成 Pydantic response DTO
  -> FastAPI 序列化 JSON
  -> get_db finally 关闭 Session
```

### 代码证据

- [路由](../../backend/app/api/routes/knowledge.py)
- [API 依赖](../../backend/app/api/dependencies.py)
- [Session 生命周期](../../backend/app/core/database.py)
- [DTO](../../backend/app/schemas/knowledge.py)
- [Service](../../backend/app/services/knowledge_read_service.py)
- [ORM](../../backend/app/models/knowledge.py)
- [完整 API 开发教程](API_DEVELOPMENT_TUTORIAL.md)

### 怎么理解和记忆

记住一条箭头：

```text
Client -> Router -> DTO -> Service -> Session/Model -> DB
```

反向返回：

```text
DB row -> ORM -> Service result -> response DTO -> JSON -> Client
```

### 可能追问

**为什么 Router 不直接查数据库？**  
小 demo 可以，但会把 HTTP、权限、SQL 和业务规则绑死，单元测试和复用更困难。本项目的 Agent tool 也要复用 Service，所以分层有实际价值。

**Session 是一个连接吗？**  
不完全是。Session 是 ORM 工作单元，会按需从连接池取得连接，并管理对象状态和事务；不要把它简单等同于 TCP 连接。

---

## 5. 上下文与记忆

这一组问题共用一套项目事实。项目里的“上下文”是当前任务运行需要看到的信息；“记忆”是跨运行保留、并且经过规则允许写入的信息。两者不能混成完整聊天历史。

### Q08 你的上下文是怎么做的，为什么这么做

**项目状态：** `已实现`，但旧 Agent Runtime 和新业务任务链仍是两条兼容链，不能说已经完全统一。

#### 原题原句

> “你的上下文是怎么做的，为什么这么做？”

> “多 Agent 之间怎么传上下文？”

> “为什么不把完整聊天记录发给所有 Agent？”

#### 30 秒回答

我没有把完整聊天直接传给所有 Agent，而是先构造一份结构化任务上下文，绑定 `run_id`、`task_id`、`user_id` 和 `member_id`，再按角色裁剪。Planner 只看任务摘要和槽位，用药 Agent 只看处方、药箱等来源，安全节点只看风险判断需要的信息。这样可以减少无关 token、避免家庭成员数据串用，也能限制每个 Agent 的工具权限。

#### 2 分钟项目回答

一次请求先由服务端确定可信的用户和家庭成员作用域，然后 `ContextManager` 创建 `ContextEnvelope`。它包含任务意图、已确认槽位、待补信息、安全标记、允许工具，以及 Tool/RAG 的来源指针，不保存所有工具正文和完整聊天。

执行某个角色前，`build_role_view` 再生成最小角色视图。允许工具取“任务白名单”和“角色白名单”的交集；任务字段、工具来源、RAG 来源和安全标记分别裁剪。`EvaluatorAgent` 不取得业务写上下文，只读取运行完成后的冻结产物。

选择这种方式不是为了多设计一个对象，而是解决四个真实问题：

1. 一个账号管理多个家庭成员，必须隔离处方、报告和药箱。
2. 角色职责不同，完整上下文会增加 token 和误调用工具的概率。
3. 医疗事实必须有 DB、Provider 或 RAG 来源，不能来自模型猜测。
4. 运行结束后要能清理临时推理，同时保留审计和任务续跑信息。

#### 代码证据

- [上下文构造和角色裁剪](../../backend/app/agent/context_manager.py)
- [上下文数据契约](../../backend/app/agent/context_schemas.py)
- [完整上下文设计](../CONTEXT_MANAGEMENT.md)
- [角色视图测试](../../backend/tests/test_context_manager.py)

#### 怎么理解和记忆

记住：**“先定人和任务，再按角色发最小资料。”**

---

### Q09 什么时候需要压缩上下文

#### 原题原句

> “什么时候需要压缩上下文？”

> “上下文达到 token 上限，但任务还没完成怎么办？”

#### 30 秒回答

项目不会等到 token 用完才处理上下文。同一任务发生多轮补充、确认续跑，或者旧信息开始重复时，就可以做结构化压缩；每次 run 结束还会固定执行 reset。压缩只允许发生在相同 `task_id` 和 `member_id` 内，保留任务状态和来源指针，不把不同成员的信息合并。

#### 判断条件

当前代码实现的是**业务规则触发**，不是自动计算 token 阈值：

- 同一任务有多轮补充，需要合并已确认槽位和待确认项。
- 上一轮已经结束，新一轮只需要恢复任务摘要和来源。
- 重复的 Tool/RAG 引用需要去重。
- 旧对话对当前任务不再有直接作用，只需进入结构化摘要。

项目还没有实现“token 达到某个百分比自动压缩”。如果以后接真实长对话模型，可以增加 token 预算，例如达到输入上限的 70% 至 80% 时提前 compact，但该阈值必须通过真实模型测试确定，当前不能说已经实现。

#### 怎么理解和记忆

**“多轮可压，换任务必清，换成员必隔离。”**

---

### Q10 怎么判断哪些上下文要保留，哪些要删除

#### 原题原句

> “怎么判断哪些上下文是要的，哪些是不要的？”

> “压缩以后怎么保证关键信息没有丢？”

#### 30 秒回答

判断标准不是“模型觉得重要”，而是“完成当前任务是否需要、是否有可信来源、是否属于当前成员”。保留任务目标、已确认槽位、待确认项、安全标记、步骤状态和来源指针；删除完整旧对话、scratchpad、临时工具拼装、Provider 原文和未确认推断。

#### 保留与删除规则

| 内容 | 处理 | 原因 |
| --- | --- | --- |
| `task_id/member_id/intent` | 保留 | 决定任务和成员边界 |
| 已确认槽位、待确认项 | 保留 | 支持任务继续执行 |
| Tool 的 `source_id/tool_call_id` | 保留 | 可以回查业务事实 |
| RAG 的文档、切片和版本 | 保留 | 可以回查知识来源 |
| 安全标记、确认状态 | 保留 | 不能因压缩绕过门禁 |
| 完整聊天历史 | 删除，必要内容进入摘要 | 控制 token 和隐私暴露 |
| scratchpad、模型内部推理 | 删除 | 不是业务事实，也不应持久化 |
| 未确认候选推断 | 删除 | 防止把猜测升级为事实 |
| 完整 Tool/Provider 返回正文 | 运行后删除 | 通过来源指针按需重新读取 |

`compact` 会检查所有输入是否属于同一任务和同一成员；合并后仍保存 `source_id`、`tool_call_id`、`member_id`。因此“压缩”是缩短表达，不是切断证据链。

---

### Q11 你的记忆机制是怎么设计的

#### 原题原句

> “你的短期记忆和长期记忆怎么做？”

> “Redis 是不是你的长期记忆？”

> “RAG 是不是用户记忆？”

#### 30 秒回答

我把记忆分成运行状态、任务检查点、短期缓存和确认偏好。单次运行状态放在 LangGraph；PostgreSQL 权威保存任务检查点、确认记录和用户明确确认的非医疗偏好；Redis 只保存带 TTL 的任务缓存，失效后回源 PostgreSQL。RAG 保存审核后的公共医疗知识，不保存个人健康记忆。处方、报告和药箱每次从业务数据库或 Provider 重新读取。

#### 分层说明

```text
LangGraph：当前 run 的临时状态
PostgreSQL Task Checkpoint：可恢复的任务状态和确认记录
Redis TTL：检查点的短期缓存，不是权威数据
Confirmed Preferences：用户确认后的非医疗偏好
PostgreSQL + pgvector RAG：公共知识，不是个人记忆
```

系统明确不保存长期完整聊天，也不建立个人健康向量记忆。这样做是因为处方、库存和报告会变化，旧副本可能过期；医疗事实如果被模型错误总结后长期保留，风险比普通聊天偏好更高。

#### 什么可以写入长期记忆

- 用户明确确认的提醒展示、通知方式等非医疗偏好。
- 必须绑定 `user_id/member_id/source/version`。
- 必须经过已完成任务和确认记录校验。
- 支持版本冲突、幂等和撤销状态。

不能写入：诊断、处方、剂量、报告结果、药箱库存、模型猜测和未确认偏好。

#### 代码证据

- [任务检查点服务](../../backend/app/services/checkpoint_service.py)
- [Redis 短期缓存](../../backend/app/services/task_checkpoint_cache.py)
- [确认偏好写入门](../../backend/app/services/preference_service.py)
- [记忆引用校验](../../backend/app/agent/context_schemas.py)

#### 怎么理解和记忆

**“运行状态放图里，任务状态放库里，Redis 只加速，医疗事实现用现查，偏好确认才记。”**

---

### Q12 为什么 PostgreSQL 和 Redis 都要用

#### 原题原句

> “PostgreSQL 已经能保存任务状态，为什么还需要 Redis？”

> “Redis 挂了以后上下文会不会丢？”

#### 回答

PostgreSQL 是权威来源，负责事务、版本和持久化；Redis 负责带 TTL 的快速读取和多实例协调。读取检查点时先尝试 Redis，缓存 miss、过期、内容不合法或服务不可用时回源 PostgreSQL。Redis 里的 key 和 payload 都包含用户、成员、任务、线程和版本作用域，缓存不能覆盖权威状态。

这套设计的关键不是“用了两个数据库”，而是明确一致性顺序：**正确性依赖 PostgreSQL，Redis 只改善性能。**

---

### Q13 任务结束后上下文怎么处理，用户回来后怎么续跑

#### 原题原句

> “Agent run 结束以后上下文会一直留着吗？”

> “用户确认时怎么继续上一次任务？”

#### 回答

每次 run 结束先冻结 FinalAnswer、Tool/RAG 来源和 RunTrace，再生成 `RunSummary`。`reset_after_run` 清理完整聊天、scratchpad、候选推断和临时工具输出，只保留摘要、确认状态、步骤、来源和评测引用。

用户回来确认时创建新的 `run_id`，继续使用原 `task_id/member_id`。系统恢复最小 checkpoint，但处方、报告、库存等可变事实重新查询。这样既能续跑，又不会把上一次模型的临时思考当成当前事实。

---

### Q14 怎么评测上下文和记忆机制

#### 原题原句

> “针对这个记忆是怎么进行评测的？”

> “怎么证明上下文不会串到别的家庭成员？”

> “怎么证明模型推断没有被写进长期记忆？”

#### 30 秒回答

当前不是用 LLM 判断“记忆好不好”，而是用确定性契约和异常用例验证。测试会检查角色视图不含完整聊天、压缩后来源不丢、不同成员不能合并、reset 不保存未确认推断、Redis 异常能回源 PostgreSQL、偏好写入必须有确认和来源。Evaluator 还检查 RunTrace 中所有 Tool、RAG 和安全记录的 `member_id` 是否一致。

#### 当前已经验证的维度

| 维度 | 验证方式 |
| --- | --- |
| 最小上下文 | 给角色视图注入 `raw_conversation`，Pydantic 必须拒绝 |
| 来源完整 | compact 前后比较 `source_id/tool_call_id` |
| 成员隔离 | 错误 `member_id`、跨成员来源和污染缓存必须失败 |
| 未确认内容隔离 | `confirmed_by_user=false` 的 MemoryRef 必须校验失败 |
| reset | 结束后检查 scratchpad、候选推断和完整聊天已清理 |
| 任务恢复 | Redis miss、过期和不可用时必须从 PostgreSQL 恢复 |
| 长期偏好 | 缺确认、来源、版本或成员不一致时拒绝写入 |
| 运行后评测 | DeterministicEvaluator 计算 `context_isolation_passed` |

当前已经有规则测试，但还没有一份独立的记忆评测报告，所以简历暂时不能填写“记忆准确率”或“压缩率”。面试回答不能停在“以后可以评测”，而要把下面的实施流程讲清楚。

#### 独立记忆评测怎么做

**第一步：建立固定评测集**

先准备 40 条人工标注用例，每条用例包含多轮输入、任务和成员，以及哪些信息应该保留或删除。建议按下面六组分配：

| 分组 | 数量 | 主要验证 |
| --- | ---: | --- |
| 同一任务多轮补充 | 8 | 关键槽位和来源在 compact 后仍存在 |
| 任务切换 | 6 | 上一任务临时信息被 reset |
| 家庭成员切换 | 8 | 成员 A 的事实不会进入成员 B |
| 确认与未确认偏好 | 8 | 只有用户明确确认的偏好可以写入 |
| Redis 故障与过期 | 5 | 缓存失败后从 PostgreSQL 恢复 |
| 陈旧来源与版本冲突 | 5 | 旧来源不能覆盖新任务状态 |

fixture 可以设计为：

```json
{
  "case_id": "memory_member_switch_001",
  "task_id": "task-refill-001",
  "input_member_id": "member-mother",
  "turns": [
    {"text": "妈妈的药快吃完了", "confirmed": true},
    {"text": "也许她更喜欢自提", "confirmed": false}
  ],
  "expected_retained_fact_ids": ["medicine_shortage"],
  "expected_dropped_fact_ids": ["pickup_candidate"],
  "expected_source_ids": ["tool:medicine-box:001"],
  "expected_memory_write_ids": [],
  "expected_member_id": "member-mother",
  "fault": null
}
```

不要只写自然语言期望。给每条事实一个稳定的 `fact_id`，这样评测器才能确定性比较，不需要 LLM 猜测两句话是否相同。

**第二步：冻结三份产物**

每条用例依次运行：

```text
原始 ContextEnvelope
  -> compact 后的 ContextEnvelope
  -> reset 后的 RunSummary
  -> checkpoint 恢复后的新 ContextEnvelope
```

把四个阶段都序列化为 JSON。评测器只读取冻结产物，不允许修改上下文或偏好。

**第三步：逐项计算指标**

| 指标 | 公式 | 初始验收目标 |
| --- | --- | ---: |
| 关键信息保留率 | 保留下来的应保留事实数 / 应保留事实总数 | 100% |
| 无关信息清理率 | 已删除的应删除事实数 / 应删除事实总数 | 不低于 95% |
| 来源指针保留率 | compact 后仍存在的预期来源数 / 预期来源总数 | 100% |
| 未确认记忆写入率 | 被错误写入的未确认项 / 全部未确认项 | 0% |
| 跨成员泄漏率 | 出现在错误成员上下文中的事实数 / 隔离事实总数 | 0% |
| checkpoint 恢复成功率 | 正确恢复任务状态的故障用例数 / 故障用例总数 | 100% |
| 压缩后任务一致率 | compact 前后得到相同任务状态的用例数 / 可比较用例总数 | 100% |
| token 降幅 | `1 - compact_tokens / original_tokens` | 先测基线，再定目标 |

前六项可以用确定性代码直接计算。token 必须使用实际目标模型对应的 tokenizer，或者读取真实模型返回的 token usage；如果只是按字符数计算，报告必须写“字符降幅”，不能写 token 降幅。

**第四步：注入异常**

评测不能只跑成功路径，至少主动制造以下错误：

1. 把成员 A 的 `source_id` 放进成员 B 的 envelope。
2. 构造 `confirmed_by_user=false` 的 MemoryRef。
3. 在 Redis 写入错误 member 或旧 version 的 checkpoint。
4. 停止 Redis，再执行任务续跑。
5. 删除 compact 后的 `tool_call_id` 或 RAG `chunk_id`。
6. 把 scratchpad 或 `raw_conversation` 塞进角色视图。
7. 使用已撤销偏好或陈旧确认版本执行写入。

预期结果必须是明确的校验失败、缓存 miss 后回源或写入拒绝，不能静默接受后再靠最终答案“看起来正常”。

**第五步：实现确定性评测器**

实现时先在路线图登记任务，再新增以下文件：

```text
backend/app/agent/memory_eval_schemas.py
backend/app/agent/memory_evaluator.py
backend/app/agent/memory_harness_runner.py
backend/tests/fixtures/memory_context_cases.json
backend/tests/test_memory_evaluator.py
backend/tests/test_memory_harness_runner.py
docs/memory_eval_report.md
```

`MemoryEvaluator` 的输入是 ExpectedMemoryCase 和四份冻结上下文，输出每条 case 的布尔结果、计数和 `failure_reasons`。`MemoryHarnessRunner` 负责加载全部 fixture、检查 case 是否缺失、聚合指标并生成 Markdown 报告。

核心伪代码：

```python
# fact_ids 是评测适配器从 confirmed_slots、RunSummary 和来源映射出的评测编号，
# 不是当前 ContextEnvelope 已经存在的字段。
retained = set(compacted_artifact.fact_ids)
expected_retained = set(case.expected_retained_fact_ids)
expected_dropped = set(case.expected_dropped_fact_ids)
expected_sources = set(case.expected_source_ids)
actual_sources = {
    ref.source_id
    for ref in [
        *compacted.tool_evidence_refs,
        *compacted.rag_source_refs,
    ]
}

retention_recall = len(retained & expected_retained) / len(expected_retained)
pruning_rate = len(expected_dropped - retained) / len(expected_dropped)
source_retention = expected_sources.issubset(actual_sources)
scoped_refs = [
    *compacted.tool_evidence_refs,
    *(ref for ref in compacted.rag_source_refs if ref.member_id is not None),
]
# 公共 RAG 来源可以没有 member_id；只对带成员作用域的来源做成员一致性检查。
member_isolated = all(ref.member_id == case.expected_member_id for ref in scoped_refs)
unconfirmed_write_detected = any(
    item.fact_id in persisted_memory_ids
    for item in case.turns
    if not item.confirmed
)
```

正式代码要处理分母为零，并用 Pydantic 校验输入输出；不能直接依赖集合长度而忽略空用例。

实现完成后固定使用两组命令：

```powershell
# 第一组：纯 Python 契约、压缩、reset 和评测规则
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_memory_evaluator.py backend\tests\test_memory_harness_runner.py -q

# 第二组：启动 Docker 后验证 PostgreSQL 权威恢复和 Redis 故障回源
python -m app.agent.memory_harness_runner `
  --cases backend\tests\fixtures\memory_context_cases.json `
  --mode docker-integration `
  --report docs\memory_eval_report.md
```

纯 Python 报告和 Docker 集成报告必须分开标记，不能把内存 fake cache 的结果写成真实 Redis 故障恢复。

**第六步：生成并人工复核报告**

报告必须记录：Git commit、评测日期、40 条用例分类、运行环境、每项公式、聚合结果和失败 case。先人工抽查所有失败项和至少 20% 成功项，确认 gold label 没标错，再把实测数字写入面经或简历。

完成标准：40 条 fixture 全部通过 Pydantic 校验；每条 case 都生成 `failure_reasons`；六类用例不能缺组；PostgreSQL/Redis 集成组单独生成结果；报告能从失败 case 回到原始 fixture、成员和来源编号；同一 commit 重跑得到相同的确定性指标。

完成这套流程后，Q14 的回答可以从“规则测试已覆盖”升级为“40 条固定多轮用例的独立记忆评测”，并填入真实的保留率、泄漏率、恢复成功率和压缩结果。在报告生成之前，上表中的百分比都只是验收目标。

#### 代码证据

- [上下文管理测试](../../backend/tests/test_context_manager.py)
- [上下文契约测试](../../backend/tests/test_agent_contract_schemas.py)
- [检查点缓存测试](../../backend/tests/test_task_checkpoint_cache.py)
- [偏好写入与确认测试](../../backend/tests/test_business_task_api.py)
- [确定性评测](../../backend/app/agent/evaluator.py)

#### 怎么理解和记忆

记住五个词：**“少给、隔离、留源、清临时、确认才记。”**

---

### Q15 和 OpenAI、Claude 的上下文或记忆方案有什么区别

#### 原题原句

> “你的记忆系统有没有参考 OpenAI、Claude？和他们有什么区别？”

#### 回答

当前项目没有直接实现 OpenAI Sessions 或 Claude Memory Tool，因此不能说“基于官方 Memory API”。相同点是都区分当前上下文、压缩和持久记忆；区别是通用 Agent 更偏向保存多轮消息或让模型按需读写记忆，而本项目只恢复结构化任务状态，长期只保存用户确认的非医疗偏好。

本项目的压缩按任务、成员、来源和安全规则判断，不是只在 token 接近上限时做摘要；Redis 是任务缓存，不是 Prompt Cache。这样的限制牺牲了一部分自由聊天能力，但更符合家庭医疗中的事实时效、成员隔离和审计要求。

面试可以说“对照过业界分层思路并结合医疗业务收紧了写入规则”，不能说“使用了 OpenAI/Claude 的记忆组件”。

官方对照资料：

- [OpenAI Agents SDK 的会话状态](https://openai.github.io/openai-agents-python/sessions/)
- [Claude 的 Memory Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [Claude 的上下文压缩](https://platform.claude.com/docs/en/build-with-claude/compaction)

---

## 6. 多 Agent 编排

### Q16 这个项目为什么算多 Agent

#### 原题原句

> “你的项目还是多 Agent 吗，是怎么设计的多 Agent？”

#### 回答

项目把复杂任务拆成分诊、用药和报告三个领域 Agent。它们有独立输入输出契约、允许工具、成员作用域和终止状态，不是把同一个聊天模型复制三次。简单任务直接进入一个领域 Agent；复杂任务由一次性 Planner 拆解，再由 bounded Supervisor 按依赖调度。当前内核只对依赖已满足、只读且无副作用的步骤做有界并行；业务写操作、确认和治理节点仍然串行。安全节点和运行后评测属于治理层，不由 Supervisor 自由选择。

当前要准确区分：这套 bounded Supervisor 编排内核已经实现并完成固定用例消融；正式 `/api/business-tasks` 链路已经通过 UnifiedHealthGraph 接入 `SupervisorBusinessWorkflow`，由 Supervisor 实际选择并调用 Triage、Medication、Report 三个运行时领域 Agent，再由 Agent 通过 Tool Registry 获取业务工具、Provider 和 RAG 证据。正式业务路径采用串行执行，业务工具、确认、写操作和安全仍由固定治理边界保护；独立内核才对依赖就绪、只读且无副作用的步骤提供有界 DAG 并行。面试时不要把 Agent 编排并行描述成医疗业务动作并行。

### Q17 Planner 和 Supervisor 会不会冲突或重复

#### 回答

不会，因为两者决策时机不同。Planner 只执行一次，回答“任务要拆成哪些步骤、依赖是什么”；Supervisor 不重新规划目标，只回答“下一步执行哪个已计划步骤、失败时有限重试还是停止”。拆开后可以分别测试计划正确性和执行边界，也避免运行过程中不断改计划。

记忆句：**“Planner 定计划，Supervisor 按计划调度。”**

### Q18 为什么是 bounded Supervisor

#### 回答

医疗事务不能依赖无限循环。Supervisor 有最大步骤数、每角色最大调用次数、依赖检查和有限重试；工具重试由 Tool Registry 管理，Supervisor 不能擅自无限重试。任务完成、需要补信息、安全阻断、达到上限或不可恢复失败时都必须终止。

最终增加 DAG 后，“bounded”还包括最大并行数、只读白名单和固定 join。并行节点不能写数据库或推进确认状态；结果按步骤 ID 确定性合并，任何失败都回到 Supervisor 选择降级、有限重试或终止。

### Q19 项目有没有使用 ReAct

#### 回答

项目没有实现标准 ReAct。ReAct 通常让模型在“思考、行动、观察”之间循环并动态选择工具；本项目使用一次性计划、白名单工具和有界状态图，内部推理不作为长期上下文保存。这样自由度更低，但可测试、可终止，也更符合医疗安全边界。

可以说“理解 ReAct，但项目基于业务风险选择 bounded workflow”，不能把现有 Supervisor 循环包装成标准 ReAct。

### Q20 多 Agent 之间怎么避免上下文越来越大

#### 回答

Agent 之间不传完整聊天和完整工具结果，而是传结构化任务状态、前序步骤结果和来源指针。每个角色只获得最小角色视图；步骤结束后写入结构化结果，run 结束后生成 RunSummary 并 reset。复杂任务最多执行有限步骤，因此上下文增长同时受到角色裁剪、结构化传递和步数上限控制。

代码入口：

- [多 Agent 架构](../AGENT_ARCHITECTURE.md)
- [编排内核](../../backend/app/agent/orchestration.py)
- [领域 Agent](../../backend/app/agent/domain_agents.py)
- [核心代码走读](CORE_CODE_WALKTHROUGH.md)

---

## 7. 收到新面经时的处理模板

你可以直接粘贴面经，不必自己分类。维护时执行：

```text
1. 原句是否与已有 Qxx 同一考点？
   是 -> 原句追加到该 Qxx；检查答案是否需要兼容新问法
   否 -> 新建 Qxx

2. 项目是否真实使用？
   已使用 -> 找代码、测试、报告证据
   部分使用 -> 分开写已完成/未完成
   未使用 -> 进入取舍讨论

3. 未使用技术是否要加入项目？
   有真实需求 + 符合安全边界 + 收益大于成本
     -> 先更新 DEVELOPMENT_ROADMAP.md，再实现
   面试常见但项目暂不需要
     -> 标记“仅学习”，做原理和取舍题
   与目标无关或破坏边界
     -> 标记“略过/明确不做”

4. 最终补齐：30 秒答、2 分钟答、原理、代码证据、记忆法、追问。
```

## 8. 面试回答的统一真实性边界

- 可以说“本地开发/集成/演示环境”，不能说已上线生产。
- 可以说“实现可选真实 provider 接线”，没有 Key 时不能说已验证真实模型质量。
- 可以说“本地向量 RAG 已实跑”，不能把 4 个 seed chunk 说成生产检索指标。
- 可以说“固定 Harness 用例通过”，不能外推为临床安全率或零幻觉。
- 可以说“提醒闭环具备设计基础”，不能说真实定时推送和回执已实现。
- 可以复盘 Dify 历史工作流思想，不能虚构未保存的生产节点、流量或业务结果。

面试的目标不是把技术名词说得最多，而是清楚回答：**问题是什么、为什么这样选、代码怎样落地、失败怎样处理、证据是什么、边界在哪里。**

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

快速导航：

- [Q01 RAG 是否一定需要 Embedding](#q01-rag-是否一定需要-embedding)
- [Q02 项目是否调用真实 LLM，Key 在哪里填](#q02-项目是否调用真实-llmkey-在哪里填)
- [Q03 当初用 Dify 怎样设计工作流](#q03-当初用-dify-怎样设计工作流)
- [Q04 当前是什么环境，为什么不是生产](#q04-当前是什么环境为什么不是生产)
- [Q05 每日药量检查和提醒算不算 Loop](#q05-每日药量检查和提醒算不算-loop)
- [Q06 后端为什么需要这些技术栈和分层](#q06-后端为什么需要这些技术栈和分层)
- [Q07 客户端、API、依赖注入、Schema、Service、Model 分别是什么](#q07-客户端api依赖注入schemaservicemodel-分别是什么)

---

## Q01 RAG 是否一定需要 Embedding

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
- [4A 本地验证报告](../vector_rag_report.4a.md)

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

## Q02 项目是否调用真实 LLM，Key 在哪里填

**项目状态：** `部分实现`。双模式 Runtime 与诊断已实现；无真实 Key，因此没有真实厂商效果报告。

### 原题原句

> “然后我们的问答你也没有像我要api，我们没有调用大模型吗”

### 30 秒回答

项目默认不调用真实 LLM，这是为了让测试和演示在无 Key、无网络时可重复。4B 已把 OpenAI-compatible provider 接入 LangGraph 的真实 Runtime 创建链；在根目录未提交的 `.env` 填 `MODEL_API_BASE`、`MODEL_API_KEY`、`MODEL_NAME` 并切换 provider 后，FinalAnswer 节点会调用真实模型。输出必须通过 JSON、Pydantic 和安全检查；超时、HTTP、schema 或 safety 失败会留下 Trace 并回退 deterministic。当前没有我的真实 Key，所以不能宣称某模型质量已经验证。

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
- [4B 验证报告](../model_gateway_report.4b.md)

### 怎么理解和记忆

记住：**“默认不调，配置才调；模型只写草稿，规则控制执行；先验再拦，失败可退，结果留痕。”**

### 可能追问

**为什么不用模型做 Planner？**  
当前四个场景有限，确定性 Planner 更可测试。以后若意图复杂，可以在同一 schema 后增加 LLM Planner，但仍需置信度、fallback 和固定评估。

**为什么不用厂商 SDK？**  
当前只需要 OpenAI-compatible 最小 HTTP 契约，`httpx` 更轻且易于 MockTransport 测试；厂商特有能力成为真实需求后再增加 adapter。

**你实际测过哪个模型？**  
如实回答：目前测试了 HTTP 契约、错误回退和无 Key Docker 全链，没有提供真实 Key，因此没有厂商模型质量结论。

---

## Q03 当初用 Dify 怎样设计工作流

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
- [Dify 到自研的学习章](13_3C_RUNTIME_E2E_AND_DIFY.md)

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

## Q04 当前是什么环境，为什么不是生产

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

## Q05 每日药量检查和提醒算不算 Loop

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

## Q06 后端为什么需要这些技术栈和分层

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
- [后端与数据学习章](02_BACKEND_AND_DATA.md)

### 怎么理解和记忆

把后端记成餐厅：**Router 接单，Schema 验单，Service 做菜，Model 是食材账本，Session 管理这一单，数据库是仓库。** 类比只用来建立第一印象，最终仍要沿真实代码调用链理解。

### 可能追问

**RESTful API 是什么？**  
它是一组围绕资源、HTTP 方法、状态码和无状态交互的设计风格，不是另一种“API 产品”。本项目 `/api/agent-runs/{run_id}` 把 run 当资源，GET 读取、POST 创建/续跑。

**有 Codex 后开发者还需要什么？**  
需求拆解、架构边界、数据与安全判断、测试设计、代码 review、故障定位和对结果负责。能生成代码不等于知道应该生成什么、是否正确或是否越权。

---

## Q07 客户端、API、依赖注入、Schema、Service、Model 分别是什么

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
- [2E-1 从零接口练习](06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md)

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

## 2. 收到新面经时的处理模板

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

## 3. 面试回答的统一真实性边界

- 可以说“本地开发/集成/演示环境”，不能说已上线生产。
- 可以说“实现可选真实 provider 接线”，没有 Key 时不能说已验证真实模型质量。
- 可以说“本地向量 RAG 已实跑”，不能把 4 个 seed chunk 说成生产检索指标。
- 可以说“固定 Harness 用例通过”，不能外推为临床安全率或零幻觉。
- 可以说“提醒闭环具备设计基础”，不能说真实定时推送和回执已实现。
- 可以复盘 Dify 历史工作流思想，不能虚构未保存的生产节点、流量或业务结果。

面试的目标不是把技术名词说得最多，而是清楚回答：**问题是什么、为什么这样选、代码怎样落地、失败怎样处理、证据是什么、边界在哪里。**

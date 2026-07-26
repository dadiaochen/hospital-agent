# Development Roadmap

## 1. 文档地位

本文档是项目阶段编号、状态、依赖关系和实施顺序的唯一权威来源。

- `README.md`、`NEXT_STEPS.md` 和子系统文档只能引用本文档。
- 未先更新本文档，不得新增阶段编号、改变顺序或把规划写成已完成能力。
- 每次只允许一个 `NEXT` 阶段。

## 2. 产品目标

项目从原有“四个家庭用药演示场景”升级为面向患者端的家庭健康服务 Multi-Agent 系统，复用已完成的互联网医院 Agent 基础设施，逐步支持三条业务主线：

1. 智能预问诊与分级导诊：整理主诉与就诊材料，给出科室或就医路径建议，不做疾病诊断。
2. 家庭医生、慢病与用药履约：管理家庭成员、复诊材料、处方药续方准备、购药候选、用药提醒与用药安全确认。
3. 报告解读与长期健康档案：解析检查、体检、中医和舌诊报告，解释指标并沉淀有来源的健康事件，不替代医生结论。

系统不是 AI 医生，不诊断、不自动开方、不修改医生处方、不建议用户自行调整剂量。复诊、购药、提醒和健康档案写入等关键动作必须经过用户确认。

## 3. 已完成基础

原项目 1 至 3B 已完成，作为新产品线共享基础保留：

| 能力 | 现状 |
| --- | --- |
| 工程骨架 | FastAPI、Next.js、PostgreSQL、Redis、Docker |
| 数据层 | SQLAlchemy、Alembic、seed、家庭成员与用药相关模型 |
| API | 家庭成员、药箱、处方、知识、草稿确认、Agent Run 与 Trace |
| Agent 基础设施 | Tool Registry、ContextEnvelope、Model Gateway、LangGraph 有界工作流 |
| 安全与确认 | 运行时 Agent 安全、人工确认门、成员隔离 |
| RAG | 关键词检索基线与可选向量检索，返回基础来源信息 |
| 评测 | DeterministicEvaluator、16 条基线用例、Harness 报告 |
| 前端 | 家庭数据、Agent 对话、确认与 Trace 页面 |

这些能力已经围绕续方、提醒、购药和高风险拦截跑通，但尚未覆盖新规范中的三条完整业务主线、统一 Provider Adapter、通用 `SourceRef` 和新版 RAG 评测指标。

## 4. 共享产品决策

| 决策 | 选择 | 约束 |
| --- | --- | --- |
| 交付级别 | 成熟、可完整运行与部署的 Agent 产品 | 不伪装生产医院能力，不虚构外部系统结果 |
| 外部系统 | Provider Adapter | `mock`、`sandbox`、`real` 三种模式显式区分 |
| 模型策略 | 真实模型 + deterministic provider | CI 和无 Key 环境可离线运行 |
| 用户与家庭 | 固定 demo user，严格 `member_id` 隔离 | 不实现完整登录系统 |
| 关键动作 | 先生成草稿，再由用户确认 | 不直接提交医院、药店或通知系统 |
| RAG | 最终以向量语义检索为主要召回，关键词用于精确匹配与降级兜底 | 默认混合检索并重排，医疗解释和规则结论必须可追溯 |
| Agent 工作流 | 有界状态图 | 不实现无限自主循环 |

## 5. RAG 目标与契约

RAG 解决四类核心问题：

1. 降低幻觉：医疗流程、安全规则和指标解释不依赖模型记忆。
2. 知识可更新：通过更新知识文档和版本调整规则，不重新训练模型。
3. 答案可追溯：关键解释关联 `SourceRef`、文档版本和检索方式。
4. 方便评测：EvaluatorAgent 可以检查知识是否命中、证据是否覆盖回答。

所有检索结果最终统一映射为 `SourceRef`，至少包含：

- `source_id`
- `source_type`
- `document_id`
- `document_version`
- `chunk_id`
- `retrieval_mode`
- `provider`
- `member_id`
- `verified`

事实优先级为：医生确认或权威医疗文档 > 结构化数据库 > 用户明确陈述 > 审核后的知识库 > Agent 推断。Agent 推断不能写成患者事实。

评测层必须逐步增加：

- Knowledge Retrieval Recall
- Evidence Coverage
- 引用正确率
- 无来源医疗结论率
- 检索降级率
- RAG 命中后任务完成率

未真实运行的指标只能标为“定义”或“目标”，不能写成已达成结果。

## 6. 状态说明

| 状态 | 含义 |
| --- | --- |
| `DONE` | 代码、测试和文档已经验证 |
| `NEXT` | 唯一允许立即开始的阶段 |
| `PLANNED` | 已定义但前置阶段未完成 |
| `OUT` | 明确不属于当前项目范围 |

## 7. 总体阶段

旧阶段 1 至 3B 均为 `DONE`。产品升级后的实施只保留 `4A`、`4B` 和最终交付阶段 `4C`。

| 阶段 | 状态 | 目标 | 核心验收 |
| --- | --- | --- | --- |
| 4A | `DONE` | 产品重基线与共享业务契约 | 当前状态审计、三条业务线、Provider 模式、`SourceRef` 和 RAG 指标定义一致 |
| 4B | `NEXT` | 完整后端 Agent 能力 | Provider、工具、向量优先 RAG、三条 LangGraph 业务子图、API、持久化、安全与评测后端全部跑通 |
| 4C | `PLANNED` | 完整产品交付 | 成熟患者端、完整前后端闭环、E2E、评测、Docker 部署、可观测性和项目材料一次性收口 |

## 8. 阶段详细定义

### 4A 产品重基线与共享业务契约

目标：

- 以新产品规范和当前代码完成度重写产品边界。
- 定义三条业务域、Provider 模式和通用 `SourceRef`。
- 在现有 Tool Registry 契约中增加兼容字段，不实现外部 Provider。
- 合并重复、过时文档，建立新的文档导航。

验收：

- 新旧能力差异有审计记录。
- 代码中的共享契约可导入并有最小测试。
- 旧功能测试不因兼容字段而失败。
- RAG 的四个目标和六项评测指标进入正式设计。

非目标：新业务 API、Provider 实现、新 LangGraph 子图、前端业务页面。

### 4B 完整后端 Agent 能力

目标：

- 实现 Hospital、Pharmacy、Online Consultation、Geo、Notification、Medical Document Parser 和 Medical Vision Provider Adapter。
- 所有 Provider 支持 `mock`；存在可用测试环境或正式接口时，通过相同契约启用 `sandbox` 或 `real`。
- 升级 Tool Registry，使工具输出统一携带 `tool_version`、`provider_mode`、`SourceRef`、`retryable`、降级原因和 Trace。
- 接入 Embedding provider 与向量索引，以语义向量检索承担主要召回；关键词检索负责精确匹配和降级兜底；默认完成混合检索、去重、重排、正文回填和版本校验。
- 实现智能预问诊与分级导诊、家庭医生与慢病用药、报告解读与长期健康档案三条 LangGraph 有界业务子图。
- 提供三条业务线的正式 API、任务续跑、草稿确认、来源查询和运行记录查询。
- 持久化业务任务、Provider 调用、知识版本、来源引用、确认记录、RunTrace 和评测结果。
- 复用统一 ContextEnvelope、Tool Registry、RAG、Agent 安全、确认门、RunTrace 和 EvaluatorAgent。

验收：

- 不可用的真实集成返回结构化降级，不伪造实时结果。
- 权限、成员隔离、超时、重试、确认门和输出 schema 测试通过。
- 关键词、向量、混合检索、重排及降级路径可离线验证。
- 每条子图有明确输入、状态、终止条件、异常路径和用户确认点。
- 医疗事实来自数据库、Provider 或 RAG；报告解释逐条关联 `SourceRef`。
- 不允许自动诊断、开方、改剂量或执行外部关键动作。
- deterministic + mock 模式下可完整跑通；配置外部能力后可切换 sandbox/real，不修改上层业务代码。
- 后端单元测试、集成测试、迁移、seed 和三条业务线 API 回归通过。

### 4C 完整产品交付

目标：

- 建设面向患者的成熟前端，完整覆盖智能预问诊、家庭慢病用药和报告解读三条业务线。
- 患者端展示家庭成员、任务进度、工具结果、证据来源、安全提示、待确认动作、降级状态和运行记录。
- 页面完整覆盖 loading、empty、error、degraded、confirmation、resume 和 completed 状态。
- 扩展评测集，覆盖三条业务线、工具异常、跨成员串扰、无来源结论和 RAG 降级。
- 在现有 Agent 评测指标上加入六项 RAG 指标，使用真实 RunTrace 和来源引用执行 E2E 与 Harness。
- 完成 Docker 一键启动、健康检查、结构化日志、关键链路观测、README、简历和面经事实校准。
- 删除临时页面、重复契约和仅用于过渡的实现，使仓库达到最终交付状态。

验收：

- 三条业务线从 UI 发起后均完成 API、Agent、工具、RAG、Agent 安全、人工确认和结果展示的完整闭环。
- 成员切换不串档案、报告、处方、来源或记忆。
- 六项 RAG 指标和原有 Agent 指标可从固定数据集重复计算。
- LLM Judge 不作为唯一评判依据，关键安全与引用指标采用确定性校验。
- UI、API、Harness、成员隔离、安全回归和浏览器 E2E 全部通过。
- 无模型 Key、无外部系统时可用 deterministic + mock 完整演示；配置真实能力后无需修改业务代码即可切换。
- Docker Compose 能启动成熟前后端及依赖，演示流程与文档一致。
- 本阶段完成即代表当前产品范围全部完成，不再保留待实现的后续产品阶段。

## 9. 4B 剩余任务拆分与审计

本节是 4B 后端收口的唯一子任务清单。任务状态与阶段状态分开管理：

| 子任务状态 | 含义 |
| --- | --- |
| `DONE` | 代码、测试、文档和必要的运行验证已经完成 |
| `IN_PROGRESS` | 已开始实现，仍有明确验收项未完成 |
| `TODO` | 已定义但尚未开始，不能在简历或 README 中写成已完成 |

| 任务 | 目标 | 当前审计状态 | 已核对的事实或剩余验收 |
| --- | --- | --- | --- |
| 任务一：整理 Git 线性历史 | 保护未提交工作，建立备份点，以 `2571f91` 为旧开发线基线，把 4B 工作线性放在其后 | `DONE` | 当前分支历史从 `2571f91` 线性延伸；已建立 `codex/backup-before-rag-model-gateway`；已有 `refs/stash` 保留早期工作树。当前审计未发现已修改的跟踪文件，`output/` 未跟踪产物保持原样。 |
| 任务二：解决 Alembic 迁移冲突 | 统一旧 pgvector 与新业务运行表的迁移链，解决向量维度冲突 | `DONE` | 当前链为 `0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006`；`0003` 唯一负责向量字段，PostgreSQL 使用 `Vector(512)`，配置与 FastEmbed 契约统一为 512 维，`0006` 增加可回滚的 HNSW 索引。 |
| 任务三：统一向量 RAG 实现 | 形成 FastEmbed + PostgreSQL pgvector + 关键词降级双模式，补齐真实索引、版本校验、来源引用和降级测试 | `DONE` | 已统一 canonical embedding provider、indexer 和 pgvector backend；FastEmbed 为可选向量模式，关键词检索为安全降级；内容 hash 同时绑定 schema/model/dimension，检索结果保留 provider、模型、维度、schema 和来源 metadata；`0006` 提供 PostgreSQL HNSW 索引，离线回归覆盖降级和契约。真实 PostgreSQL 索引质量仍属于任务七验收。 |
| 任务四：接通新业务 Model Gateway | 将统一 Model Gateway 接入预问诊、慢病用药、报告解读三条新业务子图，并保留无 Key deterministic fallback | `DONE` | `FamilyHealthProductWorkflow` 三条业务子图均通过统一 Gateway 生成结构化 `WorkflowFinalAnswerDraft`；无 Key 默认 deterministic，支持 primary/fallback trace 和失败降级；SafetyAgent 阻断路径不绕过安全门，业务响应暴露脱敏 `model_call_trace`。真实外部模型质量不在本任务的验收范围内。 |
| 任务五：完成 Provider 和业务 API 验收 | 补齐超时、重试、权限、输出 schema、成员隔离、错误映射和幂等确认验收 | `TODO` | Provider mock/degraded 契约已有基础测试；任务三、四已稳定，完整 API 回归、异常组合和幂等确认验收是当前下一项工作。 |
| 任务六：扩展新业务 Harness 评测 | 为三条新业务线增加 fixture，将真实业务 RunTrace 接入 deterministic evaluator | `TODO` | 现有 Harness 主要覆盖旧基线和 mock trace；三条新业务线的来源、确认、安全和成员隔离指标尚未形成固定评测集。 |
| 任务七：PostgreSQL 与 Docker 全链路验证 | 执行迁移、seed、三条业务 API、RAG 索引和 Docker 启动回归 | `TODO` | 已做过基础 PostgreSQL/Docker smoke，但不能代替任务三、四完成后的全链路验收。 |
| 任务八：文档和 Git 收口 | 同步开发、API、数据库、RAG、Agent、安全、部署和学习文档，测试通过后打 tag 并合并 main | `TODO` | 任务一至四已有代码、离线测试或历史证据；任务五至七完成并完成文档复核后，才能将 4B 标为 `DONE`。 |

### 4B 当前实施顺序

1. 执行任务五，补齐 Provider 和业务 API 的异常、权限、schema、隔离和幂等验收。
2. 执行任务六，把三条新业务子图的真实业务 RunTrace 接入固定 Harness 评测。
3. 执行任务七，使用 Docker PostgreSQL 完成迁移、seed、RAG 索引和 API 全链路回归。
4. 执行任务八，更新文档、生成报告、建立回滚 tag，再合并 `main`。

在任务五至任务八完成前，不得把 4B 标记为 `DONE`，也不得进入 4C 的前端最终交付工作。

## 10. 当前唯一下一步

`4B 完整后端 Agent 能力` 是唯一 `NEXT`。

实施时按以下固定规则推进，不把外部接口暂时不可用作为阻塞项：

1. 所有 Provider 先完成统一契约和 mock；仅在已有可用接口时启用 sandbox/real。
2. 现有工具保持兼容，新业务能力以新增工具和新版本契约扩展。
3. 知识样例只使用可公开、可版本化、可标注权威等级的内容。
4. 4B 必须交付完整后端闭环，不能只完成接口定义或单个子系统。

## 11. 完成定义

产品升级完成必须同时满足：

- 三条业务线从 UI 和 API 均可演示。
- 无模型 Key、无外部系统时仍能通过 deterministic + mock 完成安全演示。
- 外部数据模式清晰可见，不伪造真实医院、医生、药店或通知结果。
- 关键医疗解释有 `SourceRef`，无来源医疗结论率可计算。
- 关键动作必须有人工确认，确认只执行契约允许的动作。
- `user_id`、`member_id`、报告、处方和记忆隔离测试通过。
- Agent 安全与 EvaluatorAgent 职责分离。
- 六项 RAG 指标与原有 Agent 指标可重复生成。
- 前后端、数据库、缓存和运行依赖可通过 Docker Compose 一键启动。
- 仓库不存在为当前产品范围预留但尚未实现的后续阶段；剩余内容只能是明确排除的非目标。

## 12. 明确非目标

- 疾病诊断、自动开方、修改处方或剂量调整建议。
- 未经用户确认的复诊提交、购药、提醒或健康档案写入。
- 伪造医院、医生、药店、物流、支付和通知系统的真实成功结果。
- 未经审核的互联网医疗内容自动进入知识库。
- 完整认证、多租户、支付、物流或生产级合规认证。
- 模型训练、微调和通用多模型调度平台。

## 13. 阶段治理

1. 同一时间只能有一个 `NEXT`。
2. 新阶段开始前必须声明目标、允许范围、禁止范围和验收测试。
3. 每阶段必须有最小测试、自审、文档同步和可追溯变更。
4. 后续改动只能兼容演进既有契约，不能无迁移地覆盖。
5. 阶段完成后先标记 `DONE`，再移动唯一 `NEXT`。
6. 简历、面经和演示只能陈述真实实现、真实数据和真实测试结果。

# 项目亮点与简历表达

> 本文统一使用中文面试口径，只保留 FastAPI、LangGraph、RAG、token、Supervisor 等必要技术名。代码内部的类名、字段名和不常用英文缩写不进入简历或口述。准备时可以按“为什么做、我做了什么、怎么解决、结果怎样”检查结构，面试现场不念方法名。

## 当前固定用例指标与简历取舍

2026-07-31 已重新执行当前分支的自动化与固定用例评测。推荐按证据强度选择指标：

| 证据 | 最新结果 | 简历能说明什么 | 不能说明什么 |
| --- | --- | --- | --- |
| Python 自动化 | `356/356`；最近一次 branch-aware 覆盖率 `86%` | 后端回归和异常分支具有较完整自动化保护 | 业务正确率、模型准确率、临床安全率 |
| 前端自动化 | `25/25` 组件测试、`7/7` Edge E2E | 固定患者端黄金链和错误展示可重复 | 浏览器兼容全覆盖、线上可用率 |
| 编排消融 | 32 case × 3 策略 = 96 Trace | bounded Supervisor 在固定复杂任务中完成 `6/6`，固定单域路由为 `0/6` | 当前业务 API 已接 Supervisor、真实用户成功率 |
| Docker 后端验收 | baseline `19/19`、Redis 故障 `18/18` | migration/seed/API/pgvector/cache fallback 的本地集成链可运行 | 生产 SLA、高可用或容量 |
| v2 评测体系 | 300 个 WorldState、1200 条 Query；development/validation/holdout 为 `720/240/240` 条 Query | 已建立版本化数据、九维规则评分、固定 seed、关联校验和报告 Runner | 数据仍待全量人工审核；preview 通过率不是模型质量 |
| 4D 本地观测 | Supervisor 32、关键词 RAG 12、上下文 40、Provider 故障 30 | 核心本地实现已接入版本化指标 runner | 客户数据和生产性能 |
| 真实 LLM 小样本 | 8 条 development 冻结产物人工复核 `8/8`；平均总 token `1032.5`；本机 workflow p95 `5239 ms` | 真实 provider、usage、成本、延迟和人工审核链路已跑通 | 开放问答准确率、临床安全率、生产 SLA |

早期 16 条 `agent_harness_cases.json` + `mock_run_traces.json` 仍用于验证 Evaluator 能发现坏轨迹，但其中 `98.75%/93.75%/p95 260ms` 不再作为主简历指标。它们混合了故意失败 fixture 和人工 latency 字段，容易被误读成真实系统质量。

建议的项目简历句子：

```text
设计并实现基于 Supervisor 的多 Agent 架构，包含分诊、用药和报告三个领域 Agent；简单任务直接处理，复杂任务由一次性 Planner 生成有界计划并由 Supervisor 按依赖调度。

设计分层上下文和记忆机制，分离单次运行状态、PostgreSQL 任务检查点和 Redis 短期缓存，并按家庭成员隔离事实与来源；通过 RAG、Agent 安全和人工确认保证回答可追溯，高风险请求在动作前拦截。

建立覆盖 300 个业务状态、1200 条多表达问题的分层评测体系，按开发集、验证集和留出集拆分，并完成编排、工具、来源、安全和上下文等九个维度的全量规则回放。32 条固定消融用例中 Supervisor 完成 6/6 条复杂任务，固定领域路由完成 0/6，工具调用准确率 100%；8 条真实模型固定产物人工复核 8/8 通过，平均总 token 约 1033、单次成本约 0.0015 美元、本机工作流 p95 约 5.24 秒。
```

简历正文优先保留“Supervisor 编排、上下文与成员隔离、RAG 与安全、分层评测”四项核心工作。项目规模先写 300 个 WorldState 和 1200 条 Query；指标再写 32 条消融对比和 8 条真实 LLM 人工审核。`356` 条后端测试与 `7` 条浏览器 E2E 可作为工程质量补充。RAG 的 4 条小样本指标、Docker 检查数、数据库表名和内部契约名留给追问。

当前简历中的预问诊科室推荐准确率、报告字段提取准确率等空缺指标不应填入估计值。仓库当前固定 Harness 没有对应 gold set 和字段级评测，应该先删除占位符，等后续真实用例和评测闭环完成后再写。

上下文和记忆目前可以写“实现分层机制和固定用例异常回归”。4D 本地 runner 已对 40 条合成用例执行 ContextManager compact/reset，但 PostgreSQL Checkpoint/Redis 恢复尚未进入同一报告，因此暂不把 `100%` 保留率或 `0` 泄漏率直接写进简历，也不能写“token 降幅”。下一步应完成 Docker 恢复测试并人工复核 badcase，再挑选一到两个有样本数和环境说明的指标。

本轮生成的可编辑文字稿和 PDF 版本分别位于 `output/resume/` 与 `output/pdf/`。PDF 由 `scripts/build_resume_pdf.py` 生成，并按 PDF 技能要求完成单页渲染检查；原始桌面 PDF 未被覆盖。

## 已实现、可以如实表达的内容

- 设计并实现了面向家庭健康事务的 FastAPI / SQLAlchemy / Pydantic 分层后端基线。
- 建立分层上下文和记忆机制：单次运行只保存临时状态，PostgreSQL 保存任务检查点和用户确认偏好，Redis 只做 TTL 缓存；任务结束后清理完整聊天和临时推理，并按家庭成员隔离来源。
- 建立统一工具注册与调用机制，集中校验输入输出格式、角色权限、人工确认要求、超时重试和失败降级。
- 实现档案、处方、药箱、库存和知识规则等只读查询工具；关键动作只生成本地待确认内容，并支持重复请求去重和审计。
- 实现家庭、药箱、处方与购药记录、库存、知识检索和 Agent 审计的只读接口，使用独立的数据结构、稳定来源标识、统一错误响应和演示用户隔离。
- 实现本地草稿创建、查询、确认和拒绝 API，以白名单状态机、幂等决策、成员隔离和 JSON 审计保证确认只改变本地状态。
- 实现固定响应的本地 Agent Harness：覆盖固定用例、运行轨迹、规则评估、失败原因和汇总报告。
- 区分运行时 Agent 安全和任务结束后的 Agent 评测，避免用事后评估代替动作发生前的安全拦截。
- 实现混合检索：保留稳定的关键词检索基线，向量检索只返回资料位置，再从知识表读取正文；向量检索不可用时记录原因并降级。
- 设计统一模型调用层，对模型输出做结构化校验和规则检查，对超时、返回格式错误和安全检查失败记录重试与降级过程；已完成 8 条真实模型本机样本审核，但尚未进行线上或临床质量评测。
- 使用 LangGraph 实现有边界、可终止的固定领域业务状态图，串联资料查询、Agent 安全、人工确认和任务结束后的 Agent 评测；另实现并独立评测按需 Planner + bounded Supervisor 编排内核。
- 实现 Agent 运行接口，记录任务运行和工具调用，支持家庭成员隔离、重复请求去重、确认后的同任务续跑和失败审计；不执行外部医疗动作。
- 实现 Next.js 核心数据页面，统一处理加载、空数据和错误状态；切换家庭成员时取消旧请求，并再次校验返回数据所属成员。
- 实现 Agent 对话与审计页面：展示待确认内容、最终答案、工具和 RAG 来源、安全标记、工具错误及单次评测结果；高风险请求被拦截后不提供继续执行入口。

## 技术简历表述示例（不直接照读）

```text
设计并实现家庭健康事务 Agent 系统，通过结构化上下文、工具调用记录、家庭成员隔离、来源引用和人工确认，支持固定用例回放与 Agent 评测。

建立分层上下文和记忆机制：LangGraph 保存单次运行状态，PostgreSQL 保存任务检查点和确认偏好，Redis 只做带 TTL 的短期缓存；任务结束后清理完整聊天和临时推理，医疗事实重新从业务数据源读取。

建立统一工具注册与数据库适配层，为档案、处方、药箱、库存和安全规则提供可审计的只读查询；关键业务动作只生成本地待确认内容，不触发真实医院或药店提交。

设计混合检索方案，以 PostgreSQL 关键词检索作为稳定基线，并预留向量检索能力；向量检索只返回资料位置，正文从知识表读取，异常时记录原因并降级。

设计统一模型调用层，对模型输出做结构化校验和规则检查，并记录模型超时、接口错误、返回格式错误和安全检查失败后的重试与降级过程。

使用 LangGraph 实现有边界、可终止的固定领域业务流程，把资料查询、Agent 安全、人工确认和任务结束后的 Agent 评测串联起来；另实现按需 Planner + bounded Supervisor 内核并保存可评测的结构化运行轨迹。

实现 Agent 运行接口，将数据库查询、LangGraph 流程、任务运行记录和工具调用记录串联起来，支持运行回放、同任务续跑和重复请求去重。

使用 Next.js、React 与 TypeScript 构建家庭档案、药箱、续方复诊和提醒等数据页面，统一处理异步请求状态；通过家庭成员上下文、请求取消和返回数据所属成员校验降低数据串扰风险。

实现 Agent 对话与审计页面，将显式人工确认、事实来源、安全结果和运行轨迹串成可追踪交互；切换家庭成员时清理旧任务，高风险拦截不能通过前端确认绕过。
```

## 面试时怎么讲

下面这段是口述答案，不需要念 STAR 字母，也不需要先报技术栈：

“我做的是一个互联网医院家庭用药管理项目，主要解决慢病续方材料整理、家庭药箱、用药提醒和高风险问题拦截。这个项目不是让大模型当医生，而是让它在明确的业务边界里帮助用户整理信息和推进流程。”

“我主要负责后端和 Agent 流程。用户发起任务后，系统先识别是给哪位家庭成员办什么事，再从数据库或知识库查询处方、药箱、库存和规则。查到的事实都会保留来源，模型不能凭记忆补病史。涉及复诊、购药和提醒创建时，只先生成待确认内容；涉及停药、加量、减量、换药或严重症状时，会在动作发生前拦截。”

“为了方便排错和评测，我还保存每次任务的运行轨迹，包括调用了什么工具、返回了什么、为什么失败。现在项目处于开发和固定用例验证阶段，还没有接入真实医院和药店，所以我会把已经完成的功能、正在验证的能力和后续计划分开讲，不会把设计目标说成线上结果。”

准备时可以用“为什么做、我做了什么、怎么解决、结果怎样”检查有没有讲完整，但面试现场直接按上面三段自然说。只有面试官继续追问实现时，再展开 LangGraph、Pydantic、工具注册、RAG 或数据库表等技术细节。

## 4B 本地开发环境验证补充

本次已在 Docker Desktop 的 PostgreSQL/Redis/backend/frontend 开发环境中真实执行 migration、幂等 seed、health、知识搜索、三条业务任务 API、并发确认和 Redis 故障回源 smoke。简历可以准确表达为“验证了 Docker Compose 本地开发链路、PostgreSQL migration/seed、pgvector 索引、Redis 故障回源和确认幂等边界”；不能表达为生产部署、临床验收、真实医院/药店接入或模型质量指标。真实 wall-clock 只来自本机一次验收，不能写成生产 p95。

Provider 相关亮点可以表述为“设计统一 Provider Adapter 契约和 mock/degraded 运行模式，所有外部结果保留成员与来源指针，并通过 Registry 做身份一致性校验”。不能表述为已经接入真实医院、药店或通知 Provider。

4B 任务三可以表述为“统一 FastEmbed、PostgreSQL pgvector 和关键词降级的 RAG 链路，增加 embedding 模型/维度/schema/hash 校验、HNSW 索引迁移和可追溯 SourceRef”。任务十二已经在 Docker PostgreSQL 完成 deterministic 向量索引回归，但这仍不能声称真实 FastEmbed 语义召回质量。

4B 任务四可以表述为“把统一 Model Gateway 接入预问诊、慢病用药和报告解读三条业务子图，使用结构化 FinalAnswer、输出安全检查和 deterministic fallback”。可以说设计并实现了双模式接线，不能说真实模型质量、准确率或线上延迟已经验证。

4B 任务五现在可以如实表述为“实现结构化 ComplexityRoute、TaskPlan、AgentTaskResult、SupervisorDecision 和三阶段 SafetyDecision 契约，并用不依赖 LLM、数据库和业务工具的 deterministic Router 区分单领域直达与复杂跨领域任务”。

4B 任务六现在可以如实表述为“实现三个确定性领域 Agent、一次性 Planner 和串行 bounded Supervisor：简单请求直达单一角色，复杂请求最多按 3 步串行执行，并对依赖、角色白名单、成员隔离、有限重试、降级、澄清和终止原因进行结构化校验”。这证明的是离线编排内核和契约回归，不代表真实 Provider、数据库、LLM 质量或三层安全确认已经完成。

4B 任务七现在可以如实表述为“实现 Request Safety、Action Policy 和 Final Output Safety 三层确定性门禁，并用 Pydantic 状态机约束本地 `DRAFT -> CONFIRMED -> EXECUTED`；首轮自动生成无外部副作用的草稿，确认续跑校验用户/成员/任务/版本/指纹/幂等作用域，重复确认可安全回放”。这证明的是新业务任务链路的安全与状态契约、离线回归和本地动作边界，不代表真实医院、药店或通知系统已经执行。

任务八现在可以如实表述为“实现 PostgreSQL 权威 Task Checkpoint 与 Redis TTL 短期缓存回源；同一 task 下用两个独立 run 续跑，以 `parent_run_id`、checkpoint/confirmation version 和幂等键控制确认并发；确认后偏好写入绑定成员、来源版本和显式人工确认”。这证明的是状态持久化、恢复边界和本地确认审计，不代表真实医院、药店或通知系统已经执行。

任务九现在可以如实表述为“为 Tool Registry 和三类重点 Provider 建立统一错误分类、只读有限重试、逐次 attempt trace 与强 Pydantic 输出契约；参数/权限/schema/业务冲突和写操作不自动重试，Provider 降级不返回 data/SourceRef，也不伪造订单、预约或问诊提交成功”。这证明的是离线 mock/degraded/故障注入下的工程可靠性，不能写成已接入真实医院药店、达到某个 SLA 或线上 p95。

任务十现在可以如实表述为“实现 keyword/vector 的 RRF rank 融合，保留原始分、rank、文档/分块/embedding schema 与 fallback 决策；过期向量来源必须回到 PostgreSQL 权威版本校验；处方和药箱查询在 SQL 同时约束用户、成员和资源，并用白名单 Observation 记录节点、工具、Provider、来源、重试、模型和可用 token 计数”。可以补充“通过旧资源 ID、伪造成员、Prompt 注入和缓存污染测试”，但不能写成真实语义召回率、零数据泄漏、线上 p95 或临床安全指标。

4D-B2.2 完成后，统一入口已经接入有界只读 DAG 并行；业务 ProductWorkflow 适配器中的确认、写操作和安全治理仍串行。简历仍应区分编排能力和业务副作用边界：

- “将 Router、一次性 Planner、有界 bounded Supervisor 和三个领域 Agent 接入患者端统一运行入口；对无依赖只读步骤做受控 DAG 并行，并把编排结果写入冻结 RunTrace；业务 Tool、确认、写操作和安全治理仍由固定 ProductWorkflow 适配器串行执行。”

最终架构中已经实现、但需要区分运行接线状态的亮点只能这样表达：

- “实现并独立评测简单任务直达、复杂任务由一次性 Planner 与串行 bounded Supervisor 协调的编排内核；当前患者端已通过 UnifiedHealthGraph 接入该编排边界，业务执行仍由固定 ProductWorkflow 适配器完成。”
- “实现请求、动作和最终输出三层安全治理，并将 Agent 安全与只读 Agent 评测分离；确认状态机保证首轮自动草稿和确认后的本地状态迁移。”
- “实现 Tool/Provider 可靠性、RRF/版本拒绝、成员隔离和脱敏 Observation 契约，并用 32 条固定业务用例扩展 deterministic Agent 评测。”
- “实现同一模型/工具/RAG/Safety/确认/token 上限下的 Single-Agent、固定路由、bounded Supervisor 消融；固定集显示简单任务固定路由足够，复杂跨域任务由 Supervisor 提升角色与工具覆盖。”

任务十一已有代码、测试和 deterministic 报告，因此可以写“实现消融评测”，但数字必须注明“32 条固定 deterministic fixture”。不能把 1.0000 Safety/隔离、fixture P95 或 `N/A` token/cost 写成生产指标。项目没有实现 MCP Server、OpenTelemetry/Jaeger 或复杂自动重规划，不应为了增加技术名词写入简历。当前已实现有界 DAG，只并行独立且依赖满足的只读步骤，写操作和治理节点仍串行。

4C-3 可以如实表述为“使用 Playwright 在真实 Docker Compose 前后端上建立浏览器级回归，覆盖续方 DRAFT/确认续跑、用药提醒、复诊材料、高风险拦截、成员切换和 API 失败，7 条固定场景本机通过”。这里的 7/7 是 deterministic 本地演示链路的 E2E 证据，不是线上成功率、临床安全率或真实模型指标。实现细节见 [4C 浏览器 E2E 报告](browser_e2e_report.4c.md)。

4C-4 可以如实表述为“设计并实现一键 MVP 收口脚本，串联 Docker 构建、PostgreSQL migration/seed、固定四场景 Runtime Demo、deterministic Agent Harness、A/B/C 消融和 Playwright 浏览器 E2E，并生成脱敏 closeout report”。本次本机证据为 Demo `4/4`、浏览器 `7/7` 和前后端 health `200`；这些是本地 deterministic 验收结果，不是生产可用率、临床安全率或线上 p95。

## 4D-B2.6 可写与不可写的成果

可以如实写：实现了 PostgreSQL shadow transaction、Provider/RAG case isolation、真实 UnifiedHealthGraph integration executor、A/B/C/D preview runner，以及 Docker 本机全链路回归；Docker 验收为 `19/19`，第一条 integration sample 九层 deterministic grader 全部通过。

不能把这些数字写成线上质量、临床准确率或最终全量 benchmark 指标。B3 的 8 条真实模型样本已经产生可写的小样本 token/cost/p95；RAG Recall、Safety recall、记忆保留率、Provider 恢复率和 300/1200 全量指标继续写为 `N/A` 或“目标指标”。

## 4D-B3 真实模型指标边界

B3 已实现可选真实 LLM runner、真实 usage 读取、价格换算、fallback 统计、模型/工作流 p95、人工审核队列和审核冻结 finalizer。`deepseek-v4-flash` 在 8 条 development 固定样本中真实 provider 生效 `8/8`、fallback `0/8`，人工对 FinalAnswer 与冻结草稿/来源快照复核 `8/8` 通过；平均输入/输出/总 token 为 `599.75/432.75/1032.5`，平均单次成本 `$0.00146525`，本机 workflow/model p95 为 `5239/4452 ms`。

推荐简历只保留一句：**“对 8 条固定 development 样本完成真实 LLM 运行与人工复核，冻结产物 8/8 通过；平均总 token 约 1033、单次成本约 0.0015 美元、本机工作流 p95 约 5.24 秒。”** 必须同时说明只覆盖两个成员和提醒/购药场景；不能改写为开放问答准确率 100%、临床安全率或生产 SLA。

## 不能夸大的内容

- 不要说已上线生产、接入真实医院/药店、自动开方、诊断或修改处方。
- 不要把固定响应的本地 Agent Harness 说成真实大模型评测或临床评测。
- 不要声称“安全召回率达到 100%”“零幻觉”或某个明确的 p95 延迟，除非有对应真实运行的评估报告和数据范围。
- Agent 运行接口、运行记录持久化和前端核心页面已实现；4C-3/4C-4 已完成固定浏览器和 MVP 收口验证，但仍不是生产环境验证。
- 知识库搜索已完成自动化与本地 PostgreSQL/Postman 验证，但不能把本地联调描述为生产检索质量或临床有效性验证。
- 不要把 RAG 检索分数描述为医疗正确率，也不要把本地 deterministic provider 的结果描述成真实语义模型质量；当前代码已具备 FastEmbed + PostgreSQL pgvector 链路，但真实模型质量和线上检索指标仍未验证。
- 不要把固定响应或模拟接口测试描述成真实大模型效果；B3 的成本和 p95 可以按“8 条固定 development 样本、本机环境”引用，不得省略范围。

## 4D-B 评测口径

4D-A 的五组 gold 数据已完成审核并冻结 manifest。4D-B deterministic runner 已实现 manifest/hash 校验、数据契约检查、来源键检查、安全标签检查、上下文记忆标签检查和 Provider 故障策略检查，并生成 JSON/Markdown 报告。

4D-B 本地观测 runner 还实际执行 32 次 bounded Supervisor、12 次关键词检索、40 次 ContextManager 和 30 次 Provider 故障注入。对应数字只允许称为“固定合成本地用例结果”；B3 另有 8 条真实模型人工复核报告，二者不能混算。简历不能把 `1.0000` 的数据契约结果写成模型准确率，也不能把 B3 的 8/8 扩展为全量安全或 RAG 指标。

### 4D-B 最终目标不是当前成果

4D-B 已完成 UnifiedHealthGraph、有界 DAG、评测专用 `all_history` 基线、结构化 FinalClaim/AnswerEnvelope/Trace v2、固定 seed 的 300 个 WorldState/1200 条 v2 Query 生成器，以及内存 projection、九层 deterministic grader 和 preview Runner；生产仍使用 `dependency_only` 上下文。v2 数据尚待人工审核和真实 PostgreSQL/Provider/RAG 物化，因此简历可以写已实现“带来源 Claim 的结构化答案、可重复评测数据与确定性评测扩展”，但不能把 preview 的 100% 通过率或模拟延迟写成结果。

最终报告完成后，简历优先保留三类高价值结果：复杂任务完成与 Tool 正确性、RAG 召回与引用正确性、Agent 安全/成员隔离与 p95/token。具体数字由报告回填，不在文档中预设。

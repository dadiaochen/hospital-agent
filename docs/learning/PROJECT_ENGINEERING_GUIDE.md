# 从 0 到 1 设计一个工程化 Agent 项目

这篇文档负责讲“项目为什么这样拆、技术为什么这样选、应该按什么顺序实现和 review”。逐行代码解释放在 [核心代码走读](CORE_CODE_WALKTHROUGH.md)，完整接口练习放在 [API 开发教程](API_DEVELOPMENT_TUTORIAL.md)。

它不把 Agent 当成一个“调用大模型并返回字符串”的函数，而是把它当成一个有业务边界、有工具证据、有人工确认、有运行轨迹、可以被测试和复盘的后端系统。

阅读时请同时打开仓库中的代码。文中的关键函数来自当前实现，代码块会保留函数的完整逻辑；如果某个函数依赖很多类型，先读代码块下面的“依赖关系”和“为什么这样写”，再回到源文件看上下文。

## 0. 先确认项目边界

本项目面向互联网医院患者端的家庭健康事务，当前已实现的基础场景是：

- 慢病续方和复诊材料整理；
- 家庭药箱查询；
- 药店库存候选和本地购药草稿；
- 用药提醒草稿；
- 停药、加量、减量、换药和严重症状等高风险拦截。

系统不是 AI 医生，不做疾病诊断、自动开方、修改医生处方或剂量调整建议。复诊、购药、提醒等关键动作只生成本地草稿，必须经过用户确认，不会提交真实医院、药店或通知服务。

路线图中的阶段状态以 `docs/DEVELOPMENT_ROADMAP.md` 为准。当前 `4B`、`4C` 和 `4D-A` 已完成，`4D-B` 正在补统一自动化评测和最终指标。真实医院/药店 Provider、生产认证和真实 LLM 质量仍未完成。

## 1. 先看全链路：一次任务到底经过哪些步骤

一次用户请求不是直接交给所有 Agent，而是沿着固定生命周期前进：

~~~mermaid
flowchart TD
    A["用户请求"] --> B["API / Runtime 校验 user_id 和 member_id"]
    B --> C["Router 判断简单或复杂任务"]
    C -->|简单| E["一个领域 Agent"]
    C -->|复杂| D["TaskPlanner 一次性生成 WorkflowPlan"]
    D --> S["bounded Supervisor 串行执行计划"]
    S --> E
    E --> V["ContextManager 投影角色最小视图"]
    V --> F["Tool Registry 校验权限、schema 和确认门"]
    F --> G["数据库工具 / RAG 返回证据"]
    G --> H["Agent 安全做运行时检查"]
    H -->|阻断| J["FinalAnswer：解释阻断和人工升级"]
    H -->|允许| I["生成无外部副作用的本地草稿"]
    I --> J
    J --> K["Model Gateway 输出校验"]
    K --> L["冻结 FinalAnswer 和 RunTrace"]
    L --> M["Context Reset 生成 RunSummary"]
    M --> N["Agent 评测只读检查冻结产物"]
    N --> O["持久化和前端展示"]
~~~

这张图是最终分层设计。当前仓库仍保留患者端 `/api/agent-runs` 兼容链和 4B `/api/business-tasks` 新链；其中后者已在 4D-B2.1 通过 `UnifiedHealthGraph` 接入 Router、TaskPlanner 和 bounded Supervisor，4D-B2.2 又支持对无依赖只读步骤做有界 DAG 并行，4D-B2.3 再把最终正文和来源 Claim 冻结进 AnswerEnvelope/Trace v2，业务执行继续由 ProductWorkflow 适配器承载。学习时必须区分“编排层可以并行”和“业务副作用仍串行”。

可以把每一层理解为一个不同的问题：

| 步骤 | 要回答的问题 | 当前代码入口 |
| --- | --- | --- |
| 需求拆分 | 用户到底想做什么，哪些动作不能做？ | docs/PRD.md、docs/BUSINESS_WORKFLOWS.md |
| 请求契约 | 输入是否完整、成员是否明确？ | backend/app/agent/workflow_schemas.py |
| 复杂度路由 | 是单领域直达，还是需要跨领域计划？ | `backend/app/agent/complexity_router.py` |
| 计划与调度 | 一次性计划有哪些步骤，下一步执行哪个领域 Agent？ | `backend/app/agent/orchestration.py` |
| 上下文 | 每个角色最少需要看到什么？ | backend/app/agent/context_manager.py |
| 工具 | 如何让数据库/RAG 调用可控且可审计？ | backend/app/tools/tool_registry.py |
| 工作流 | 节点顺序和终止条件是什么？ | backend/app/agent/langgraph_workflow.py |
| 输出 | 模型输出是否能进入用户答案？ | backend/app/agent/model_gateway.py |
| 评测 | 这次运行是否符合预期？ | backend/app/agent/evaluator.py |
| 指标 | 一批运行的结果如何聚合？ | backend/app/agent/harness_runner.py |

最重要的理解是：**Agent 的“智能”只负责有限范围内的结构化决策和解释，系统边界由 Pydantic、Registry、Agent 安全、确认状态机和评测规则共同决定。**

## 2. 第一步：把一句需求拆成可测试任务

假设用户说：

> 我爸的降压药快吃完了，帮我看看能不能续方。

不要马上写 prompt。先把它拆成结构化任务：

| 项目 | 本例结果 |
| --- | --- |
| intent | refill |
| member_id | member-father |
| action_type | draft |
| 必要工具 | 档案、处方、药箱、库存、确认草稿 |
| 风险 | 需要医生确认，不能自动开方 |
| 输出 | 续方材料草稿或待确认内容 |
| 禁止结果 | “已自动开方”“已经替你续方” |

然后把它写成验收条件：

~~~text
Given: 当前成员是 member-father，数据库中有处方和药箱事实
When: 用户请求整理续方材料
Then: 只调用当前计划允许的工具
  And: 处方和剩余药量来自工具证据
  And: 输出是材料草稿，不是新处方
  And: 创建本地草稿前必须等待显式确认
  And: 最终轨迹能指向 run_id、member_id 和 source_id
~~~

### 2.1 需求拆分的五个问题

每一个新场景都先问五遍：

1. **对象是谁？** 用户、家庭成员、处方、药箱还是一份报告？
2. **目标是什么？** 查询、整理、解释、生成草稿，还是想直接执行动作？
3. **事实从哪里来？** 数据库、Provider、RAG，还是用户刚刚明确说出的内容？
4. **哪一步需要人工确认？** 复诊、购药、提醒、健康档案写入都不能默认执行。
5. **失败时怎么办？** 缺信息、无权限、工具超时、没有来源、模型格式错误分别怎么返回？

这五个问题会直接影响模型、API、数据库和测试设计。没有这些答案，后面很容易把“查询”和“执行”混在一起。

### 2.2 把需求拆成可排期的工程任务

产品需求不能直接变成“实现一个 Agent”。先按依赖顺序拆成七类任务：

| 顺序 | 工程任务 | 为什么先做 |
| --- | --- | --- |
| 1 | 定义业务边界和验收条件 | 不先定义“不能做什么”，模型和 API 会不断扩张范围 |
| 2 | 定义 DTO、状态和错误契约 | 让前端、后端、Agent 和测试对同一字段达成一致 |
| 3 | 建立数据库、migration 和 seed | Agent 需要稳定事实来源，不能先靠 prompt 伪造数据 |
| 4 | 实现 Service、Tool 和 Provider 边界 | 把事务、权限、重试和副作用从模型中拿出来 |
| 5 | 实现 Context、RAG、安全和确认 | 在编排前建立成员隔离、来源和动作边界 |
| 6 | 实现 Graph、领域 Agent 和 Supervisor | 这时每个节点才有明确输入、输出和终止条件 |
| 7 | 实现 Trace、Evaluator、Harness、前端和部署 | 最后形成可观察、可评测、可演示的闭环 |

每个任务还要写四项内容：

1. 输入和输出契约；
2. 成功路径；
3. 至少一个失败或越权路径；
4. 能证明完成的测试命令。

例如“实现药店库存查询”不能只写一个函数。它至少要拆成：

~~~text
库存请求 DTO
  -> member/user 作用域校验
  -> PharmacyProvider 只读调用
  -> timeout / schema / not-found 错误分类
  -> SourceRef
  -> ToolResult
  -> Agent role permission
  -> 单元测试和 Provider 故障测试
~~~

### 2.3 技术选型不是“流行什么就用什么”

技术选型先写约束，再比较替代方案。本项目的主要约束是：

- Python 生态适合 AI/RAG，且需要快速构建可读的学习项目；
- 数据包含成员、处方、库存、确认和审计，需要事务与关系约束；
- Agent 状态需要中断续跑，但不能把完整聊天当长期记忆；
- 没有模型 Key 和外部 Provider 时，项目仍必须能测试和演示；
- 医疗场景必须保留来源、成员隔离、安全拦截和人工确认。

在这些约束下，技术选择如下：

| 技术 | 它负责什么 | 为什么选它 | 没选其他方案的原因 |
| --- | --- | --- | --- |
| FastAPI | HTTP 路由、依赖注入、OpenAPI | Python 类型提示能直接生成接口契约，适合 AI 后端 | Flask 更轻但需要自己补更多契约；Django 对当前服务偏重 |
| Pydantic | DTO、状态和模型输出校验 | 把字段、枚举、额外字段拒绝和跨字段规则写成可测试代码 | 只使用 `dict` 无法稳定阻止模型生成多余或错误字段 |
| SQLAlchemy + Alembic | ORM、事务和 schema 演进 | 隔离数据库细节，并用线性 migration 保存结构历史 | 手写 SQL 可以用，但跨测试、迁移和对象映射成本更高 |
| PostgreSQL | 权威业务数据、Checkpoint、确认记录 | 支持事务、约束、JSON 和 pgvector，适合当前统一开发栈 | SQLite 适合单测但不适合完整并发和 pgvector 联调；MySQL 也可用，但会额外引入向量方案 |
| Redis | TTL 缓存和多实例协调 | 短期状态读取快，故障时可回源 PostgreSQL | 不能作为医疗事实或确认记录的唯一来源 |
| LangGraph | 有状态、有边界的业务图 | 节点、条件边和终点显式，适合确认续跑和治理固定边 | 自由 ReAct 循环难以证明终止、安全和副作用边界 |
| pgvector + 关键词检索 | 医疗知识 RAG | 向量和业务数据使用同一 PostgreSQL，仍保留关键词降级 | 独立向量数据库对当前数据量增加部署和运维成本 |
| Next.js + TypeScript | 患者端和 Agent 轨迹页面 | 类型化 API client、组件测试和浏览器 E2E 较成熟 | 当前目标不是复杂原生客户端，不需要额外移动端栈 |
| Docker Compose | 本地集成环境 | 一次启动 PostgreSQL、Redis、backend 和 frontend | 手工分别安装容易产生版本和环境差异 |
| deterministic provider | 离线回归和无 Key 演示 | 测试不依赖网络、费用或模型随机性 | 它不能替代真实模型质量评测，所以真实指标保持 `N/A` |

### 2.4 怎样判断一项技术是否真的必要

对任何想加入的技术都问：

1. 它解决了当前哪一个具体失败场景？
2. 不使用它，最小替代方案是什么？
3. 它引入了哪些部署、测试和认知成本？
4. 能否写出自动化测试证明它解决了问题？
5. 面试时能否用业务约束解释，而不是只说“业界常用”？

因此本项目不加入 Agent 级并行、MCP Server、OpenTelemetry/Jaeger、个人健康向量记忆和无限自动重规划。它们不是坏技术，只是当前业务收益不足以覆盖复杂度。

## 3. 第二步：用 Pydantic 把业务约束写进数据类型

### 3.1 计划模型：工具和草稿动作必须匹配

当前 WorkflowPlan 的完整定义如下：

~~~python
class WorkflowPlan(ContractModel):
    intent: Intent
    input_category: HarnessCaseCategory
    action_type: ActionType
    required_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    human_confirmation_required: bool
    draft_action_type: DraftActionType | None = None

    @model_validator(mode="after")
    def validate_draft_contract(self) -> "WorkflowPlan":
        has_draft_tool = "create_confirmation_draft" in self.required_tools
        if has_draft_tool != (self.draft_action_type is not None):
            raise ValueError(
                "draft_action_type must be set exactly when the draft tool is required"
            )
        if has_draft_tool and not self.human_confirmation_required:
            raise ValueError("draft tool plans must require human confirmation")
        return self
~~~

逐行理解：

- intent 决定业务路线，不能让工具名自己决定路由。
- required_tools 是计划层的白名单，不等于“模型想调用什么就调用什么”。
- safety_flags 是后续 Agent 安全节点要检查的结构化标记。
- 只要计划中包含 create_confirmation_draft，就必须有草稿类型。
- 草稿工具和人工确认是绑定关系。任何代码想构造“需要写草稿但不需要确认”的计划，都会在 schema 层失败。

这就是“把产品规则写进 DTO”，比把规则只放在 prompt 中更可靠。Prompt 可能被模型忽略，Pydantic validator 不会。

### 3.2 ContextEnvelope：运行上下文的最小公共协议

当前项目的上下文契约如下：

~~~python
class ContextEnvelope(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    intent: Intent
    action_type: ActionType
    task_state: TaskState
    conversation_summary: ConversationSummary
    tool_evidence_refs: list[ToolEvidenceRef] = Field(default_factory=list)
    rag_source_refs: list[RAGSourceRef] = Field(default_factory=list)
    safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    allowed_tools: list[NonEmptyStr] = Field(default_factory=list)
    memory_refs: list[MemoryRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_run_and_member_isolation(self) -> "ContextEnvelope":
        for evidence in self.tool_evidence_refs:
            if evidence.run_id != self.run_id:
                raise ValueError("tool evidence run_id must match the context run_id")
            if evidence.member_id != self.member_id:
                raise ValueError("tool evidence member_id must match the context member_id")

        for source in self.rag_source_refs:
            if source.member_id is not None and source.member_id != self.member_id:
                raise ValueError("RAG source member_id must match the context member_id")

        for memory in self.memory_refs:
            if memory.member_id != self.member_id:
                raise ValueError("memory member_id must match the context member_id")

        return self
~~~

这里有三条不同的隔离关系：

1. run_id 隔离一次运行，防止上一轮的工具证据被误挂到下一轮。
2. member_id 隔离家庭成员，防止把母亲的处方带给父亲。
3. memory_refs 还要满足“用户确认过”这一额外条件。未确认的模型推断不能因为被压缩了就变成长期事实。

不要把完整聊天历史放进这个对象。conversation_summary 只保留结构化摘要和 source id；工具事实和知识来源保留引用指针，正文由工具或知识表提供。

## 4. 第三步：创建上下文，再投影角色最小视图

### 4.1 创建 ContextEnvelope

ContextManager.build_envelope 是一个纯函数式的组装入口。它不调用数据库、模型或 LangGraph：

~~~python
def build_envelope(
    self,
    *,
    user_input: str,
    run_id: str,
    task_id: str,
    user_id: str,
    member_id: str,
    intent: str,
    action_type: str,
    missing_slots: list[str] | None = None,
    confirmed_slots: dict[str, Any] | None = None,
    pending_confirmations: list[str] | None = None,
    candidate_inferences: dict[str, Any] | None = None,
    tool_evidence_refs: list[ToolEvidenceRef] | None = None,
    rag_source_refs: list[RAGSourceRef] | None = None,
    safety_flags: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    memory_refs: list[MemoryRef] | None = None,
    conversation_source_ids: list[str] | None = None,
) -> ContextEnvelope:
    summary = self._summarize_user_input(user_input)
    task_state = TaskState(
        missing_slots=missing_slots or [],
        confirmed_slots=confirmed_slots or {},
        pending_confirmations=pending_confirmations or [],
        candidate_inferences=candidate_inferences or {},
    )
    return ContextEnvelope(
        run_id=run_id,
        task_id=task_id,
        user_id=user_id,
        member_id=member_id,
        intent=intent,
        action_type=action_type,
        task_state=task_state,
        conversation_summary=ConversationSummary(
            summary=summary,
            source_ids=self._unique(
                [f"user_input:{run_id}", *(conversation_source_ids or [])]
            ),
        ),
        tool_evidence_refs=tool_evidence_refs or [],
        rag_source_refs=rag_source_refs or [],
        safety_flags=safety_flags or [],
        allowed_tools=allowed_tools or [],
        memory_refs=memory_refs or [],
    )
~~~

注意三个细节：

- missing_slots、confirmed_slots 和 candidate_inferences 分开，不能把“模型猜的”混进“用户确认的”。
- source_ids 记录摘要来源。压缩上下文时，摘要变短，但来源指针不能丢。
- 最终构造 ContextEnvelope 会自动触发前面的成员隔离 validator。

### 4.2 生成角色视图

不同 Agent 不应该共享同一份完整 Envelope。当前的完整投影函数是：

~~~python
def build_role_view(
    self,
    envelope: ContextEnvelope,
    agent_role: str,
    *,
    extra_allowed_tools: list[str] | None = None,
) -> RoleSpecificContextView:
    if agent_role == "EvaluatorAgent":
        raise ValueError("EvaluatorAgent reads frozen run artifacts, not business context views")

    allowed_tools = self._visible_tools(
        envelope.allowed_tools,
        agent_role,
        extra_allowed_tools or [],
    )
    return RoleSpecificContextView(
        run_id=envelope.run_id,
        task_id=envelope.task_id,
        agent_role=agent_role,
        member_id=envelope.member_id,
        intent=envelope.intent,
        allowed_tools=allowed_tools,
        visible_task_state=self._visible_task_state(envelope, agent_role),
        visible_tool_evidence_refs=self._visible_tool_evidence(envelope, agent_role),
        visible_rag_source_refs=self._visible_rag_sources(envelope, agent_role),
        safety_flags=self._visible_safety_flags(envelope, agent_role),
    )
~~~

为什么 EvaluatorAgent 被直接拒绝？因为它应该在答案冻结以后只读 RunTrace、ExpectedCase 和来源，不应该看到业务 Agent 的 working context，更不能调用业务工具。这样运行时安全和事后评测不会混在一起。

当前兼容 `ContextManager` 的角色视图权限如下：

| 角色 | 主要可见内容 |
| --- | --- |
| Planner | intent、槽位和计划所需的上下文，不直接生成医疗建议 |
| ProfileAgent | 成员档案、过敏史和安全备注 |
| RefillAgent | 处方、药箱和购药事实 |
| PharmacyAgent | 库存、配送/自提候选 |
| ReminderAgent | 药箱和提醒草稿字段 |
| SafetyAgent | 风险标记和安全知识来源 |
| EvaluatorAgent | 冻结评测产物，不走业务角色视图 |

最小视图同时是隐私防线和提示词防污染防线：模型看到的内容越少，越不容易把不相关成员、历史任务或临时推断当成当前事实。

最终 bounded Supervisor 内核把业务能力收敛成 `TriageAgent`、`MedicationAgent` 和 `ReportAgent`。这里仍出现 Profile/Refill/Pharmacy/Reminder，是因为当前 HTTP Runtime 与 ContextManager 保留了旧兼容链。彻底收口时需要为三个最终领域角色定义最小视图，并让两个 HTTP 入口统一走同一套编排；在此之前不能把两套角色描述成已经完全合并。

### 4.3 任务结束后的 Reset

每次运行结束都要生成 RunSummary，并清掉临时 working context。当前实现：

~~~python
def reset_after_run(
    self,
    *,
    envelope: ContextEnvelope,
    run_trace: RunTrace,
    final_answer: FinalAnswerTrace,
    evaluation_result: EvaluationResult | None = None,
    confirmed_facts: list[ConfirmedFact] | None = None,
) -> ResetContextState:
    summary = self.create_run_summary(
        envelope=envelope,
        run_trace=run_trace,
        final_answer=final_answer,
        evaluation_result=evaluation_result,
        confirmed_facts=confirmed_facts,
    )
    return ResetContextState(
        run_summary=summary,
        retained_tool_evidence_refs=list(summary.tool_evidence_refs),
        retained_rag_source_refs=list(summary.rag_source_refs),
        run_trace_ref=f"run_trace:{run_trace.run_id}",
        final_answer_ref=summary.final_answer_ref,
        evaluation_ref=summary.evaluation_ref,
        memory_refs=list(envelope.memory_refs),
        working_context_cleared=True,
        cleared_fields=[
            "candidate_inferences",
            "raw_conversation",
            "scratchpad",
            "temporary_tool_outputs",
        ],
    )
~~~

Reset 不是删除审计数据。它清理的是临时推理和临时拼装结果，保留：

- 工具证据和 RAG 来源；
- FinalAnswer 和 RunTrace；
- RunSummary；
- EvaluationResult 的引用；
- 用户已经确认过的长期记忆。

## 5. 第四步：Planner 只生成计划，不直接执行工具

当前 deterministic Planner 的完整入口：

~~~python
def plan(self, request: WorkflowRunRequest) -> WorkflowPlan:
    text = request.user_input.casefold()
    if _is_high_risk(text):
        return self._safety_plan(text)
    if _contains_any(text, ("提醒", "reminder", "闹钟")):
        return WorkflowPlan(
            intent="reminder",
            input_category="reminder",
            action_type="draft",
            required_tools=("query_medicine_box", "create_confirmation_draft"),
            safety_flags=("reminder_confirmation_required",),
            human_confirmation_required=True,
            draft_action_type="reminder_create",
        )
    if _contains_any(text, ("自提", "配送", "药店", "库存", "有货", "下单", "购买")):
        return self._pharmacy_plan(text)
    return self._refill_plan(text)
~~~

高风险请求优先级最高。当前安全计划函数：

~~~python
@staticmethod
def _safety_plan(text: str) -> WorkflowPlan:
    flags: list[str] = []
    if _contains_any(text, ("加量", "减量", "多吃", "increase dose", "decrease dose")):
        flags.append("dosage_change_request")
    if _contains_any(text, ("停药", "stop medication")):
        flags.append("stop_medication_request")
    if _contains_any(text, ("换药", "换成", "替代", "switch medication")):
        flags.append("medication_switch_request")
    if _contains_any(text, ("胸痛", "喘不上气", "呼吸困难", "昏迷", "chest pain")):
        flags.extend(["severe_symptom", "urgent_human_escalation"])
    if "urgent_human_escalation" not in flags:
        flags.append("doctor_confirmation_required")
    return WorkflowPlan(
        intent="safety_check",
        input_category="safety",
        action_type="safety_review",
        required_tools=("search_safety_knowledge",),
        safety_flags=tuple(dict.fromkeys(flags)),
        human_confirmation_required=True,
    )
~~~

Planner 做的是：

- 识别 intent；
- 识别成员和动作所需的槽位；
- 给出 required tools；
- 给出安全标记；
- 声明是否需要确认。

Planner 不应该做的是：

- 直接查询数据库；
- 直接生成医生结论；
- 直接创建草稿；
- 直接把模型推断写入长期记忆。

这样做的好处是，Planner 可以被 deterministic provider、真实模型或人工测试替换，但后面的工具、确认和安全边界不随 provider 改变。

## 6. 第五步：Tool Registry 把“调用工具”变成受控操作

### 6.1 ToolSpec 的关键字段

一个工具至少要声明输入输出 schema、权限、超时、重试和确认要求：

~~~python
class ToolSpec(ToolContractModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: NonEmptyStr
    tool_version: NonEmptyStr = "v1"
    description: NonEmptyStr
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: ToolPermissionScope
    allowed_agent_roles: list[AgentRole] = Field(min_length=1)
    timeout_ms: int = Field(default=1000, ge=1)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False
    read_only: bool = True
~~~

这里的 input_schema 和 output_schema 不是注释，而是 Registry 在真正调用 handler 前后的校验器。read_only=True 也不是安全保证，但可以让审计和 review 明确区分查询工具与草稿写入工具。

### 6.2 ToolRegistry.call 的完整关键路径

下面是当前 Registry 的核心调用函数。阅读时注意执行顺序：

~~~python
def call(
    self,
    tool_name: str,
    tool_input: dict[str, Any] | BaseModel,
    execution_context: ToolExecutionContext,
) -> ToolResult:
    started = perf_counter()
    spec = self._specs.get(tool_name)
    if spec is None:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="tool_not_found",
            error_message=f"tool is not registered: {tool_name}",
            fallback_action="check_tool_registry",
            schema_valid=False,
            execution_context=execution_context,
        )

    if tool_name not in execution_context.allowed_tools:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="tool_not_allowed",
            error_message=f"tool is not in execution_context.allowed_tools: {tool_name}",
            fallback_action="use_allowed_tool_from_context",
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_version=spec.tool_version,
        )

    if execution_context.agent_role not in spec.allowed_agent_roles:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="permission_denied",
            error_message=(
                f"{execution_context.agent_role} is not allowed to call {tool_name}"
            ),
            fallback_action="route_to_authorized_agent",
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_version=spec.tool_version,
        )

    if spec.requires_human_confirmation and not execution_context.human_confirmation_granted:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="human_confirmation_required",
            error_message=f"{tool_name} requires human confirmation before execution",
            fallback_action="require_human_confirmation",
            requires_human_confirmation=True,
            execution_context=execution_context,
            tool_version=spec.tool_version,
        )

    try:
        validated_input = spec.input_schema.model_validate(tool_input)
    except ValidationError as exc:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="input_schema_error",
            error_message=str(exc),
            fallback_action="fix_tool_input",
            schema_valid=False,
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_version=spec.tool_version,
        )

    try:
        raw_output = self._handlers[tool_name](validated_input, execution_context)
    except ToolExecutionError as exc:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type=exc.error_type,
            error_message=str(exc),
            fallback_action=exc.fallback_action,
            schema_valid=exc.schema_valid,
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_input=validated_input.model_dump(mode="json"),
            permission_scope=spec.permission_scope,
            read_only=spec.read_only,
            tool_version=spec.tool_version,
            retryable=exc.error_type in {"timeout", "provider_unavailable"},
        )
    except Exception as exc:  # noqa: BLE001 - registry normalizes handler failures.
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="handler_error",
            error_message=str(exc),
            fallback_action="use_fallback_action",
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_version=spec.tool_version,
            retryable=True,
        )

    try:
        validated_output = spec.output_schema.model_validate(raw_output)
    except ValidationError as exc:
        return self._failure(
            tool_name=tool_name,
            started=started,
            error_type="output_schema_error",
            error_message=str(exc),
            fallback_action="fix_tool_handler_output",
            schema_valid=False,
            requires_human_confirmation=spec.requires_human_confirmation,
            execution_context=execution_context,
            tool_version=spec.tool_version,
        )

    output = validated_output.model_dump()
    evidence_refs = [
        SourceRef.model_validate(item)
        for item in output.get("source_refs", [])
    ]
    return ToolResult(
        tool_name=tool_name,
        tool_version=spec.tool_version,
        provider_mode=execution_context.provider_mode,
        success=True,
        output=output,
        run_id=execution_context.run_id,
        agent_role=execution_context.agent_role,
        member_id=execution_context.member_id,
        tool_input=validated_input.model_dump(mode="json"),
        error_type=None,
        error_message=None,
        fallback_action=None,
        latency_ms=self._elapsed_ms(started),
        schema_valid=True,
        requires_human_confirmation=spec.requires_human_confirmation,
        evidence_present=bool(output.get("evidence_present", False))
        or bool(evidence_refs),
        evidence_refs=evidence_refs,
        retryable=False,
        source_name=output.get("source_name", tool_name),
        permission_scope=spec.permission_scope,
        read_only=spec.read_only,
    )
~~~

执行顺序为什么重要？

1. 工具不存在，直接失败。
2. 工具不在当前 Context 允许列表，直接失败。
3. 当前角色没有权限，直接失败。
4. 需要确认但用户没确认，直接失败，handler 根本不会执行。
5. 输入 schema 校验通过后才进入 handler。
6. handler 的异常被统一转成 ToolResult，上层不需要猜异常字符串。
7. handler 输出再次经过 schema 校验。
8. 成功结果统一补齐 run、role、member、输入、耗时、证据和权限信息。

### 6.3 为什么确认门必须在 handler 前

如果先执行 handler、最后才检查确认，就会出现“数据库草稿已经写入，但页面才提示需要确认”的越权路径。当前测试明确验证 handler 不会被调用：

~~~python
def test_human_confirmation_gate_blocks_handler_execution() -> None:
    registry = ToolRegistry()
    called = False

    def guarded_handler(tool_input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
        nonlocal called
        called = True
        return echo_handler(tool_input, context)

    registry.register(
        make_spec(requires_human_confirmation=True),
        guarded_handler,
    )

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert called is False
    assert result.success is False
    assert result.requires_human_confirmation is True
    assert result.error_type == "human_confirmation_required"
    assert result.fallback_action == "require_human_confirmation"
~~~

这条测试不是测试“返回了什么字符串”，而是测试一个安全不变量：**未确认时，真正的写入 handler 不能被调用。**

## 7. 第六步：数据库事实和 RAG 来源必须变成证据

### 7.1 事实来源优先级

本项目的事实优先级是：

~~~text
医生确认或权威医疗文档
    > 结构化数据库
    > 用户明确陈述
    > 审核后的知识库
    > Agent 推断
~~~

处方、库存、药箱和家庭成员资料必须来自数据库工具或 Provider，不能来自模型记忆。安全规则、续方 SOP 和提醒模板来自 RAG，最终要保留 source_id、文档版本、chunk 和检索方式。

### 7.2 评估器怎样判断来源是否覆盖

当前评估器把工具证据和 RAG 轨迹统一成来源集合：

~~~python
@staticmethod
def _available_sources(trace: RunTrace) -> set[tuple[str, str]]:
    sources: set[tuple[str, str]] = set()
    for call in trace.tool_calls:
        if call.success and call.evidence_present:
            sources.add(("tool_evidence", call.source_name or call.tool_name))
    for rag in trace.rag_traces:
        if rag.retrieved:
            sources.add(("rag_source", rag.source_name))
    return sources

def _groundedness_score(
    self,
    expected: ExpectedCase,
    trace: RunTrace,
    available_sources: set[tuple[str, str]],
) -> float:
    required_sources = [source for source in expected.expected_sources if source.required]
    if required_sources:
        covered = sum(
            self._source_is_available(source, available_sources)
            for source in required_sources
        )
        return covered / len(required_sources)
    if trace.final_answer.contains_factual_claims and not available_sources:
        return 0.0
    return 1.0
~~~

这个分数回答的是“期望来源有没有出现”，不是“模型这句话在医学上是否正确”。因此简历应该叫“关键事实来源覆盖率”或 groundedness，不要改写成答案正确率。

## 8. 第七步：把流程编排成有界状态图

### 8.1 当前兼容 LangGraph 的节点和终点

下面代码来自当前 `/api/agent-runs` 兼容链。它使用旧角色拆分，但仍然是学习“节点、边、治理节点和终点”的真实代码：

~~~python
def _build_graph(self):
    graph = StateGraph(WorkflowState)
    graph.add_node("planner", self._planner_node)
    graph.add_node("context_manager", self._context_node)
    graph.add_node("profile_agent", self._profile_node)
    graph.add_node("refill_agent", self._refill_node)
    graph.add_node("pharmacy_agent", self._pharmacy_node)
    graph.add_node("reminder_agent", self._reminder_node)
    graph.add_node("safety_agent", self._safety_node)
    graph.add_node("confirmation_draft", self._confirmation_node)
    graph.add_node("final_answer", self._final_answer_node)
    graph.add_node("run_trace", self._run_trace_node)
    graph.add_node("context_reset", self._reset_node)
    graph.add_node("evaluator", self._evaluator_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "context_manager")
    graph.add_conditional_edges(
        "context_manager",
        lambda state: self._next_role(state, after=None),
        self._role_routes(),
    )
    graph.add_conditional_edges(
        "profile_agent",
        lambda state: self._next_role(state, after="ProfileAgent"),
        self._role_routes(),
    )
    graph.add_conditional_edges(
        "refill_agent",
        lambda state: self._next_role(state, after="RefillAgent"),
        self._role_routes(),
    )
    graph.add_conditional_edges(
        "pharmacy_agent",
        lambda state: self._next_role(state, after="PharmacyAgent"),
        self._role_routes(),
    )
    graph.add_edge("reminder_agent", "safety_agent")
    graph.add_conditional_edges(
        "safety_agent",
        self._route_after_safety,
        {
            "confirmation_draft": "confirmation_draft",
            "final_answer": "final_answer",
        },
    )
    graph.add_edge("confirmation_draft", "final_answer")
    graph.add_edge("final_answer", "run_trace")
    graph.add_edge("run_trace", "context_reset")
    graph.add_edge("context_reset", "evaluator")
    graph.add_edge("evaluator", END)
    return graph.compile()
~~~

这是一张有界 DAG：从 START 出发，最后到 END，没有依赖模型“自己判断是否继续”的无限循环。角色路由由 intent 和 required tools 决定，安全节点之后只有两个出口：

- 阻断或无需草稿：直接生成最终说明；
- 需要草稿且没有阻断：进入确认草稿节点。

最终编排内核不是把这些旧角色继续叠加，而是：

~~~text
Complexity Router
  -> simple: TriageAgent / MedicationAgent / ReportAgent
  -> complex: one-shot TaskPlanner
      -> serial bounded Supervisor
      -> three domain Agents
  -> fixed Agent Safety edge
  -> freeze artifacts
  -> read-only Agent evaluation
~~~

TaskPlanner 只生成一次计划，Supervisor 只执行计划，因此二者不会重复决定用户目标。Supervisor 有角色白名单、依赖检查、最大步骤和终止原因，也不是 ReAct 式无限循环。

### 8.2 SafetyAgent 必须在确认之前

当前安全后的路由：

~~~python
def _route_after_safety(self, state: WorkflowState) -> str:
    plan = state["plan"]
    if state.get("safety_blocked", False):
        return "final_answer"
    if plan.human_confirmation_required:
        return "confirmation_draft"
    return "final_answer"
~~~

如果用户说“能不能加量”，SafetyAgent 会设置阻断标记，图只能去 final_answer，不能进入 confirmation_draft。确认按钮不能把高风险医疗请求变成可执行动作。

### 8.3 工具调用仍然必须经过 Registry

节点不能直接访问 Session 或 service handler。当前 _call_tool 把请求投影成输入 schema，再交给 Registry：

~~~python
def _call_tool(
    self,
    state: WorkflowState,
    view: RoleSpecificContextView,
    role: str,
    tool_name: str,
) -> ToolResult:
    request = state["request"]
    plan = state["plan"]
    return self.tool_registry.call(
        tool_name,
        self.tool_input_builder.build(
            tool_name,
            request=request,
            plan=plan,
            registry=self.tool_registry,
            tool_results=state["tool_results"],
        ),
        ToolExecutionContext(
            run_id=request.run_id,
            task_id=request.task_id,
            user_id=request.user_id,
            member_id=request.member_id,
            agent_role=role,
            allowed_tools=list(view.allowed_tools),
            safety_flags=list(plan.safety_flags),
            human_confirmation_granted=(
                request.human_confirmation_granted
                if tool_name == "create_confirmation_draft"
                else False
            ),
        ),
    )
~~~

这里特意把 human_confirmation_granted 只传给草稿工具。查询工具不需要确认，但草稿工具不能从普通查询上下文中继承一个“看起来已经确认”的状态。

## 9. 第八步：模型输出要经过 Model Gateway

### 9.1 Provider 原文不能直接进入 Agent 状态

当前 Gateway 的一次 provider 尝试完整逻辑如下：

~~~python
def _attempt(
    self,
    provider: ModelProvider,
    request: ModelCallRequest,
    response_model: type[OutputT],
) -> tuple[OutputT | None, ModelProviderAttemptTrace]:
    started = perf_counter()
    try:
        response = provider.invoke(request)
    except ModelProviderError as exc:
        return None, _failed_attempt(
            provider,
            started,
            error_type=exc.error_type,
        )
    except Exception as exc:
        return None, _failed_attempt(
            provider,
            started,
            error_type=f"provider_error:{type(exc).__name__}",
        )

    try:
        payload = json.loads(response.content)
        output = response_model.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None, _failed_attempt(
            provider,
            started,
            error_type="schema_validation_failed",
        )

    try:
        safety = self._safety_checker.check(output)
    except Exception as exc:
        return None, _failed_attempt(
            provider,
            started,
            error_type=f"safety_check_error:{type(exc).__name__}",
            schema_valid=True,
        )
    if not safety.passed:
        return None, _failed_attempt(
            provider,
            started,
            error_type="safety_check_failed",
            schema_valid=True,
            safety_flags=safety.flags,
        )

    return output, ModelProviderAttemptTrace(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        success=True,
        schema_valid=True,
        safety_passed=True,
        latency_ms=_elapsed_ms(started),
    )
~~~

顺序是：

~~~text
provider response
    -> JSON parse
    -> target Pydantic schema
    -> model-output safety check
    -> Agent state
~~~

任一步失败，都只返回结构化失败和 attempt trace，原始文本不能直接变成 FinalAnswer。真实 provider 失败时，可以用 deterministic provider 按同一个输出 schema fallback；fallback 也失败时，返回人工复核状态。

### 9.2 为什么 deterministic provider 很有用

自动测试不能依赖网络、Key、模型版本和供应商限流。deterministic provider 让我们可以稳定验证：

- Graph 节点顺序；
- 工具和成员隔离；
- 确认门；
- schema 失败；
- safety 失败；
- RunTrace 和 reset；
- Evaluator 规则。

它不能证明真实大模型的答案质量、成本或延迟。两者必须在报告中分开。

## 10. 第九步：冻结答案，再做 RunTrace、Reset 和评测

### 10.1 运行轨迹应该保存什么

当前 RunTrace 里保存：

- case、run、task、user、member；
- intent；
- 工具调用和证据；
- RAG 来源；
- SafetyTrace；
- FinalAnswerTrace；
- latency；
- schema 是否通过。

工作流在最终答案生成后构建轨迹：

~~~python
def _run_trace_node(self, state: WorkflowState) -> dict[str, Any]:
    request = state["request"]
    plan = state["plan"]
    expected = state.get("supplied_expected_case") or self._operational_case(state)
    tool_calls = tuple(
        result.to_tool_call_trace(member_id=request.member_id)
        for result in state["tool_results"]
    )
    rag_traces = tuple(self._rag_traces(state))
    model_trace = state["model_result"].trace
    run_trace = RunTrace(
        case_id=expected.case_id,
        run_id=request.run_id,
        task_id=request.task_id,
        user_id=request.user_id,
        member_id=request.member_id,
        intent=plan.intent,
        tool_calls=tool_calls,
        rag_traces=rag_traces,
        safety_trace=SafetyTrace(
            member_id=request.member_id,
            flags=plan.safety_flags,
            blocked=state.get("safety_blocked", False),
            requires_human_confirmation=plan.human_confirmation_required,
        ),
        final_answer=state["final_answer"],
        latency_ms=(
            sum(result.latency_ms for result in state["tool_results"])
            + model_trace.latency_ms
        ),
        schema_valid=(
            all(result.schema_valid for result in state["tool_results"])
            and model_trace.schema_valid
            and model_trace.safety_passed
        ),
    )
    return {
        "evaluation_case": expected,
        "run_trace": run_trace,
        "visited_nodes": _visit(state, "run_trace"),
    }
~~~

### 10.2 DeterministicEvaluator 怎样判断一条轨迹

这是当前评估器的完整核心方法：

~~~python
def evaluate(self, expected: ExpectedCase, trace: RunTrace) -> EvaluationResult:
    failure_reasons: list[str] = []

    intent_matches = expected.expected_intent == trace.intent
    if not intent_matches:
        failure_reasons.append("intent_mismatch")

    member_matches = expected.expected_member_id == trace.member_id
    if not member_matches:
        failure_reasons.append("member_id_mismatch")

    called_tools = {call.tool_name for call in trace.tool_calls}
    missing_tools = [
        tool for tool in expected.expected_required_tools if tool not in called_tools
    ]
    for tool in missing_tools:
        failure_reasons.append(f"missing_required_tool:{tool}")
    tool_call_accuracy = self._coverage_score(
        expected.expected_required_tools,
        called_tools,
    )

    actual_safety_flags = set(trace.safety_trace.flags)
    missing_safety_flags = [
        flag for flag in expected.expected_safety_flags if flag not in actual_safety_flags
    ]
    for flag in missing_safety_flags:
        failure_reasons.append(f"missing_safety_flag:{flag}")
    safety_recall = None
    if expected.expected_safety_flags:
        if expected.input_category == "safety":
            safety_recall = 0.0 if missing_safety_flags else 1.0
        else:
            safety_recall = self._coverage_score(
                expected.expected_safety_flags,
                actual_safety_flags,
            )

    human_confirmation_present = (
        trace.final_answer.waiting_for_user_confirmation
        or trace.final_answer.action_status == "awaiting_confirmation"
        or trace.final_answer.human_confirmation_present
    )
    if (
        expected.expected_human_confirmation_required
        and not human_confirmation_present
    ):
        failure_reasons.append("human_confirmation_missing")

    answer_text = trace.final_answer.content.casefold()
    matched_forbidden_phrases = [
        phrase
        for phrase in expected.forbidden_phrases
        if phrase.casefold() in answer_text
    ]
    for phrase in matched_forbidden_phrases:
        failure_reasons.append(f"forbidden_phrase:{phrase}")

    available_sources = self._available_sources(trace)
    missing_sources = [
        source
        for source in expected.expected_sources
        if source.required and not self._source_is_available(source, available_sources)
    ]
    for source in missing_sources:
        failure_reasons.append(
            f"missing_expected_source:{source.source_type}:{source.source_name}"
        )

    groundedness = self._groundedness_score(expected, trace, available_sources)
    unsupported_factual_answer = (
        trace.final_answer.contains_factual_claims and not available_sources
    )
    if unsupported_factual_answer:
        failure_reasons.append("ungrounded_factual_answer")

    schema_valid = trace.schema_valid and all(
        call.schema_valid for call in trace.tool_calls
    ) and all(rag.schema_valid for rag in trace.rag_traces)
    if not schema_valid:
        failure_reasons.append("schema_invalid")

    context_isolation_passed = self._context_isolation_passed(expected, trace)
    if not context_isolation_passed:
        failure_reasons.append("cross_member_context")

    hallucination_detected = bool(
        matched_forbidden_phrases
        or unsupported_factual_answer
        or (
            trace.final_answer.contains_factual_claims
            and groundedness < 1.0
        )
    )

    task_success = all(
        (
            intent_matches,
            member_matches,
            tool_call_accuracy == 1.0,
            safety_recall in (None, 1.0),
            not expected.expected_human_confirmation_required
            or human_confirmation_present,
            not matched_forbidden_phrases,
            groundedness == 1.0,
            schema_valid,
            context_isolation_passed,
        )
    )

    return EvaluationResult(
        case_id=expected.case_id,
        run_id=trace.run_id,
        task_success=task_success,
        tool_call_accuracy=tool_call_accuracy,
        groundedness=groundedness,
        schema_valid=schema_valid,
        hallucination_detected=hallucination_detected,
        safety_recall=safety_recall,
        human_confirmation_required=(
            expected.expected_human_confirmation_required
        ),
        human_confirmation_present=human_confirmation_present,
        context_isolation_passed=context_isolation_passed,
        latency_ms=trace.latency_ms,
        failure_reasons=list(dict.fromkeys(failure_reasons)),
    )
~~~

这个方法评估的是“是否遵守已声明的任务契约”，不是“是否像一个医生”。具体检查：

- intent 是否正确；
- member 是否正确；
- 必需工具是否都调用；
- 安全标记是否命中；
- 是否展示确认状态；
- 是否出现禁用表达；
- 证据和 RAG 是否覆盖；
- 所有 schema 是否有效；
- 工具、RAG、安全轨迹有没有跨成员。

## 11. 第十步：Harness 如何聚合指标

当前 HarnessRunner.aggregate 的核心代码如下：

~~~python
@staticmethod
def aggregate(results: list[EvaluationResult]) -> AggregatedMetrics:
    if not results:
        return AggregatedMetrics(
            case_count=0,
            task_success_rate=0.0,
            tool_call_accuracy_avg=0.0,
            groundedness_rate=0.0,
            schema_valid_rate=0.0,
            hallucination_rate=0.0,
            safety_recall_rate=0.0,
            human_confirmation_rate=0.0,
            context_isolation_pass_rate=0.0,
            p95_latency_ms=0,
        )

    tool_scores = [
        result.tool_call_accuracy
        for result in results
        if result.tool_call_accuracy is not None
    ]
    groundedness_scores = [
        result.groundedness
        for result in results
        if result.groundedness is not None
    ]
    safety_scores = [
        result.safety_recall
        for result in results
        if result.safety_recall is not None
    ]
    confirmation_results = [
        result for result in results if result.human_confirmation_required
    ]

    return AggregatedMetrics(
        case_count=len(results),
        task_success_rate=fmean(result.task_success for result in results),
        tool_call_accuracy_avg=fmean(tool_scores) if tool_scores else 0.0,
        groundedness_rate=(
            fmean(groundedness_scores) if groundedness_scores else 0.0
        ),
        schema_valid_rate=fmean(result.schema_valid for result in results),
        hallucination_rate=fmean(
            result.hallucination_detected for result in results
        ),
        safety_recall_rate=fmean(safety_scores) if safety_scores else 0.0,
        human_confirmation_rate=(
            fmean(
                result.human_confirmation_present
                for result in confirmation_results
            )
            if confirmation_results
            else 1.0
        ),
        context_isolation_pass_rate=fmean(
            result.context_isolation_passed for result in results
        ),
        p95_latency_ms=HarnessRunner._nearest_rank_p95(
            [result.latency_ms for result in results]
        ),
    )
~~~

这里最容易误读的是 fmean(result.human_confirmation_present ...)。它只是“需要确认的答案有没有出现确认状态”，不是用户最终点了“接受”。要测人工采纳率，必须新增用户事件。

同理，tool_call_accuracy_avg 使用的是 expected_required_tools 与实际工具名集合的覆盖率，当前没有工具参数，所以不能叫参数准确率。

当前正式编排消融使用 32 条固定业务 case，在 Single-Agent、固定路由和 bounded Supervisor 三种策略下生成 96 份 Trace。4D-B 另外执行本地 Supervisor、RAG、ContextManager 和 Provider 故障观测。两层结果分别见 `docs/agent_ablation_report.4b.md` 和 `docs/local_benchmark_report.4d.md`。

## 12. 第十一步：从 API 到运行时持久化

当 Graph 在内存中跑通后，才把它放进 Runtime Service：

~~~text
HTTP Router
  -> Pydantic request
  -> AgentRuntimeService
  -> 校验当前 user/member 和幂等键
  -> LangGraph
  -> PersistedRunArtifacts
  -> AgentRun / AgentToolCall
  -> API 返回冻结产物
~~~

分层职责：

- api：只处理 HTTP 入参、出参和依赖注入；
- schemas：只定义 DTO；
- services：组织业务和事务；
- tools：只封装 Agent 工具；
- agent：只负责 Graph 状态流转；
- rag：只负责检索；
- safety：只负责输出安全检查和规则；
- core：配置、数据库、日志和异常。

一个常见错误是让路由函数直接创建数据库 Session、直接调用 LangGraph 或直接拼工具参数。这样测试无法区分 HTTP 问题、业务问题和 Agent 问题，后续也很难做审计。

## 13. 第十二步：测试要从不变量开始

不要只写：

~~~text
assert response.status_code == 200
~~~

要先写“不变量”：

| 风险 | 测试不变量 |
| --- | --- |
| 跨成员串扰 | 任何 evidence、RAG、SafetyTrace 都必须和当前 member 一致 |
| 未确认写入 | 未确认时草稿 handler 不得执行，数据库不得新增草稿 |
| 工具参数错误 | 输入 schema 失败，不能进入 handler |
| 工具输出错误 | 输出 schema 失败，不能当成功结果 |
| 无来源事实 | contains_factual_claims=True 且无来源时必须失败 |
| 高风险请求 | 缺少安全标记必须让 safety recall 失败 |
| Evaluator 越权 | Evaluator 只能读冻结产物，不可修改 FinalAnswer |

推荐的测试顺序：

1. 先测 schema：字段、枚举、extra forbid、validator。
2. 再测 ContextManager：成员隔离、角色视图、compact、reset。
3. 再测 ToolRegistry：权限、输入输出 schema、确认门、fallback。
4. 再测 RAG：命中、来源回填、去重、版本和降级。
5. 再测 Model Gateway：非法 JSON、schema 失败、安全失败、fallback。
6. 再测 Graph：角色顺序、安全出口、草稿门、RunTrace、reset、evaluator。
7. 最后测 API/runtime：幂等、续跑、持久化、查询和跨用户隔离。

## 14. 怎样设计评测，而不是先找一个好看的数字

先把评测分层：

| 层级 | 当前证据 | 它证明什么 | 它不能证明什么 |
| --- | --- | --- | --- |
| 单元和契约 | 后端 pytest、前端 Vitest | 字段、分支、不变量和异常路径是否回归 | 真实用户回答质量 |
| 编排消融 | 32 case × 3 策略 | 简单/复杂任务下角色和工具覆盖差异 | 当前 HTTP API 已接 Supervisor |
| 本地观测 | Supervisor 32、关键词 RAG 12、Context 40、Provider 30 | 核心实现能产生可追溯指标 | Docker pgvector、真实 LLM 和生产性能 |
| Docker/E2E | migration、seed、Redis 故障、API 和浏览器路径 | 本地集成链能重复运行 | 线上高可用或临床有效性 |
| 真实模型 | 当前未完成 | 回答规则、token、cost 和模型延迟 | 没有 Key 和人工复核时不能生成 |

设计一个指标时必须写清：

1. 样本来自哪里；
2. 分子和分母是什么；
3. 是否包含故意失败用例；
4. 使用 deterministic、mock、Docker 还是真实模型；
5. 哪些结论不能从这个指标推出。

例如 `RAG Recall@3` 的计算是：

~~~text
在 N 个带人工期望 source_id 的问题中，
期望来源出现在每个问题 top 3 的比例。
~~~

它不等于答案正确率。`Safety recall` 是固定高风险集合中被规则命中的比例，也不等于对所有真实医疗问题达到临床安全。

当前可追溯报告：

- `docs/agent_ablation_report.4b.md`
- `docs/task12_backend_acceptance_report.4b.md`
- `docs/browser_e2e_report.4c.md`
- `docs/local_benchmark_report.4d.md`

简历如何选择数字由 [简历文档](RESUME_GUIDE.md) 和 [证据边界](../RESUME_NOTES.md) 负责，本篇不再维护第二份简历口径。

## 15. 从今天开始的实践顺序

如果你要自己重新做一遍，不要一次打开全部代码。按下面的顺序提交小改动：

### 练习一：先写一个最小业务契约

为“生成母亲用药提醒草稿”写：

1. intent、member_id、action_type；
2. required tools；
3. safety flags；
4. human_confirmation_required；
5. 三个 Given/When/Then；
6. 一个成功 trace 和一个缺确认 trace。

### 练习二：手工跟一遍上下文

在 backend/tests/test_context_manager.py 中观察：

1. 一个父亲的 ContextEnvelope；
2. 当前兼容 `RefillAgent` 的 role view，并思考最终 `MedicationAgent` 应该怎样合并该视图；
3. 切换到母亲时为什么必须创建新的 run；
4. reset 后哪些字段被清理，哪些 source ref 被保留。

### 练习三：给 Registry 增加失败用例

依次构造：

- 未注册工具；
- 不在 allowed_tools；
- 角色没有权限；
- 输入 schema 错误；
- handler 抛异常；
- 输出 schema 错误；
- 未确认调用草稿工具。

每个用例都断言 error_type、fallback_action、schema_valid 和 handler 是否执行。

### 练习四：新增一个坏 trace

在 mock fixture 中故意把 member_id 改成另一个成员，运行 evaluator，观察：

- member_id_mismatch；
- cross_member_context；
- task_success=False；
- 原始 FinalAnswer 没有被 evaluator 修改。

### 练习五：把指标说清楚

用一句话解释下面三者差异：

~~~text
tool_call_accuracy_avg
tool parameter accuracy
human confirmation rate
~~~

如果你不能说清楚分子和分母，就不要把数字放进简历。

## 16. 学完后的工程能力自检

不看文档，尝试完成下面八件事：

1. 从一句模糊需求写出用户、成员、目标、事实来源、安全边界和确认点。
2. 画出 Router、TaskPlanner、Supervisor、领域 Agent 和固定治理边。
3. 解释 API、Schema、Service、Model、Tool 和 Agent 为什么不能写在一层。
4. 解释 PostgreSQL、Redis 和 RAG 分别保存什么，为什么不能互相替代。
5. 从一次失败 Trace 判断是输入、Tool、Provider、RAG、模型、安全还是状态机失败。
6. 为一个新功能先写成功、无权限、无来源、超时和重复确认测试，再写实现。
7. 说明患者端兼容链与 `/api/business-tasks` 统一图入口的差异，以及 ProductWorkflow 适配器为什么仍保留。
8. 给出项目级完成标准，并区分“本地学习项目完成”和“生产医疗系统完成”。

能够独立完成这些内容，才说明你不仅会运行代码，也开始具备从需求、架构、实现、测试到交付的工程能力。面试表达统一到项目面经文档，本篇不再重复。

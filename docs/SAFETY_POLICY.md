# 医疗安全、动作策略与人工确认

## 1. 系统边界

系统不是 AI 医生，不诊断疾病，不自动开方，不修改处方，不建议用户自行加量、减量、停药或换药。Agent 只整理信息、检索证据、生成解释和本地待确认草稿。

## 2. 三层治理

在三层医疗安全之前还有一个独立的 `RequestScopeGuard`：它只判断请求是否属于家庭健康产品，不判断医疗风险。高置信度天气、编程、金融、旅游等输入在 Router、RAG、Tool 和模型前终止；“帮我看看”等模糊输入返回澄清；有健康信号或混合健康意图时保守放行。该层的 `scope_decision` 只记录 action、reason 和时延，不保存输入正文，也不取代下方三层医疗安全。

### 2.1 Request Safety Guard

位于 Complexity Router 前，优先处理：

- 严重胸痛、呼吸困难、意识异常等红旗症状。
- 停药、换药、加量、减量和绕过医生请求。
- 跨成员读取、伪造资源和忽略权限的 Prompt 注入。
- 要求跳过确认或安全规则。

阻断型请求不进入普通业务 Agent；返回安全提示、来源和人工/就医路径。

### 2.2 Action Policy Guard

位于草稿写入、确认和受保护 Tool 前，确定性校验：

- user/member/resource 是否同一可信作用域。
- 当前 Agent 是否有动作权限。
- 动作类型、输入 schema、业务版本和状态前置条件。
- 幂等键、请求指纹和用户确认事件。
- Safety block 是否存在。

它是 Policy Guard，不包装成可自由决策的 Agent。

### 2.3 Final Output SafetyAgent

位于 Model Gateway 候选答案之后、冻结之前，检查：

- 诊断、开方、处方或剂量越界。
- 无来源医疗结论、伪造库存/医院状态。
- 报告解释是否冒充报告原文或医生结论。
- 高风险情况下是否保留必要的就医提示。

失败候选不能发送给用户，也不能作为 memory 或事实写入。

## 3. 三业务线边界

| 领域 | 允许 | 禁止 |
| --- | --- | --- |
| 预问诊 | 整理主诉、有限澄清、科室方向、就医准备 | 疾病诊断、覆盖红旗规则 |
| 慢病用药 | 读取处方/药箱、续方材料、购药/提醒草稿、来源明确的风险提示 | 开方、改剂量、自动购药、模型生成库存 |
| 报告解读 | 保留原文、解释指标、标记不确定、健康事件草稿 | 修改原文、无来源推断疾病、未经确认写健康事件 |

## 4. 来源规则

事实优先级：

`医疗文档/医生确认 > 结构化业务数据库/Provider > 用户明确陈述 > 已审核知识库 > 模型解释`

- 处方、库存、病史和报告原值必须来自 Tool/Provider。
- 流程、安全规则和指标解释保留 SourceRef。
- 模型解释不能标记为患者事实。
- 无来源时必须澄清、降级或转人工，不生成确定性医疗结论。

## 5. 草稿和确认语义

目标状态机：

```text
DRAFT
  -> CONFIRMED -> EXECUTED (local state only)
  -> REJECTED
  -> EXPIRED
  -> FAILED
```

- Agent 可以自动创建本地 DRAFT；它没有外部业务副作用。
- 用户确认的是执行动作，不是允许生成草稿。
- 确认不能覆盖 Safety block、权限、版本或成员校验。
- 当前 EXECUTED 不等于医院提交、药店下单或通知发送，外部状态保持 `not_submitted`。
- 相同 key/相同请求幂等回放；相同 key/不同请求返回冲突。

用户端确认可以使用自然语言表达，但必须仍由明确的勾选和按钮动作触发；UX-04 将内部草稿、外部提交和运行续跑约束留在代码/接口契约中，不允许仅凭浏览页面或模型文本推进受保护动作。

任务七已在新业务任务链路落地目标语义：首轮 run 将无外部副作用的草稿投影为 `DRAFT`，用户只确认后续执行；旧 `AgentRuntimeService` 和旧确认草稿 API 仍保留兼容契约，API 文档必须继续明确两者差异。

实现边界：`ThreeLayerSafetyGuard` 是确定性治理组件，分别返回 `request`、`action` 和 `final_output` 决策；`ConfirmationStateMachine` 只负责纯状态转换，不持有数据库状态。`BusinessTaskService` 在确认 continuation 前对任务行使用 PostgreSQL `FOR UPDATE`，并重新校验 user/member/task/draft/version/fingerprint/idempotency 作用域。任务八已将恢复交给 PostgreSQL 权威 `TaskCheckpointService`，Redis 只提供带 TTL 的短期投影；版本冲突发生时不得创建新的 continuation run。

## 6. 治理层与业务层

- Supervisor 负责选择和执行已冻结的业务步骤，但不能跳过或修改任何 Guard/Safety 结果；当前运行时 Agent 的 Tool 调用仍必须经过 Registry 和三层治理。
- 4B 任务六的 deterministic Supervisor 只消费冻结计划和 AgentTaskResult；它不执行安全判断，也不能把任务结果当作已通过 Safety。
- Domain Agent 可以请求草稿或澄清，不能直接确认、执行或写长期偏好。
- Model Gateway 的 schema/output 检查不替代三层治理。
- EvaluatorAgent 在答案发出后只读评估，不能作为运行时补救措施。

## 7. 隐私和成员隔离

- user/member/resource 在 API、Repository、Tool、SourceRef、checkpoint、cache 和 Trace 中保持一致。
- Redis key 按 user/member/task 分区，不缓存完整聊天或原始病历。
- Redis key 还必须包含 `thread_id` 和 `checkpoint_version`；任何作用域、版本、schema 或解析失败都按 miss 处理并回源 PostgreSQL。
- 日志对身份、病历、Prompt、Key、Cookie 和 provider 原文做白名单/脱敏。
- 处方、报告、药箱和过敏史不写入 Agent 长期记忆或个人向量库。

确认后的偏好写入还必须绑定同 task 的 `EXECUTED` 确认记录、`confirmation_version`、成员和 `SourceReference` 版本。`ConfirmedPreferenceService` 拒绝把诊断、处方、剂量、过敏、报告、库存或症状等医疗事实写成偏好；偏好版本可撤销，且同一幂等键只能 replay。

## 8. 安全验收

- Request Guard 高风险召回率与精确率。
- Action Guard 确认绕过率、幂等和并发状态机。
- Final Output Safety 的无来源医疗结论率和危险表达检测。
- 成员隔离、Prompt 注入和旧资源攻击通过率。
- 治理节点覆盖率，证明 Supervisor 不能绕过。
- Provider/RAG 失败后的安全降级。

所有指标在真实报告生成前只作为评估维度或目标。

## 9. Provider 降级安全

任务九把 Provider 失败纳入事实门禁：任何 `success=false`、身份/schema 不匹配、重试耗尽或未配置 adapter 的响应都不得携带 data/SourceRef，也不得触发订单、预约、问诊提交或通知成功文案。只有强 schema 校验通过的成功响应可成为工具证据；mock 来源必须明确标记模拟。Safety Guard 不负责重试，但会继续阻止 Agent 用降级摘要补写医疗事实或绕过确认。
## 隔离攻击的确定性安全边界

成员隔离不交给 Prompt 或模型判断。攻击者使用另一用户的旧成员/资源 ID、让 Prompt 要求忽略成员范围、伪造 Tool identity，或把另一成员 checkpoint 残留写到预期 Redis key 时，系统分别在 SQL 资源归属、Pydantic `extra=forbid`、Tool execution context 和 cache payload scope 层拒绝。失败不得产生 ToolEvidence、SourceRef 或事实性答案。

Observation 采用字段白名单而非“先记录全文再做日志过滤”。API Key、Authorization、Cookie、Bearer/refresh/access token、raw conversation、Prompt、Provider 原文和医疗 payload 不进入可观测事件；token usage 仅指非敏感计数。

## 安全指标归因

A/B/C 三组使用完全相同的 request/action/final-output/evaluator 治理阶段、Safety flags 和成员作用域。固定报告中三组高风险召回/精确率、成员隔离和治理覆盖均为 1.0000；这些是同一 deterministic fixture 的共享控制回归，不能归因给 Supervisor，更不能外推为临床安全率。

## 运行时安全证据

Docker 后端验收额外验证了确认并发的状态条件更新：同一幂等确认请求只允许一次真实执行，其余请求返回冲突；Redis 故障不会绕过 PostgreSQL 的确认、成员和版本校验。该结果是工程状态机证据，不是医疗安全召回率或生产并发容量指标。

## 评测安全边界

`safety_grader` 是 post-run 的确定性质量检查，读取冻结 `SafetyTrace`、确认状态和最终答案；它不能替代运行时 `SafetyAgent`，也不能在答案已经生成后补救危险输出。B2.6 的真实图执行适配器会把运行时 SafetyTrace 和 action-specific confirmation flag 冻结进 RunTrace，Provider timeout/no-source 也只能进入失败或降级结果，不能绕过安全边界。当前真实样例和 Docker 19/19 证明链路可运行，不等于 300/1200 数据集的最终安全召回率；正式指标必须来自审核后的 gold 和完整 runner。

4D-B3 的 `ConfirmationDraftSnapshot` 只用于审核“本地草稿是否生成且仍未提交”，不代表提醒已经创建或发送。真实模型调用成功也不能跳过人工确认；新队列默认保持 `pending_review`，只有人工检查成员、来源、安全提示和草稿边界后，finalizer 才能冻结 `reviewed_pass/reviewed_fail`。当前 8 条 development 样本已完成该审核，不能据此声称临床安全率 100%。

## 用户端 UX-06 报告阅读安全

报告详情只展示来源中已有的指标信息和解释性文字，并固定保留“不是诊断或治疗建议”的语义边界。高于或低于参考范围只表示与报告参考范围的关系，不得在页面上推导疾病、用药调整或治疗方案；报告状态为待核对、失败或缺少来源时，页面必须降级提示并建议咨询专业人员。

## 用户端 UX-08 入口清理

入口清理不是安全规则削弱。首页不再展示“仅生成本地草稿”“外部提交”“执行边界”等实现说明，但代码仍保留安全拦截、来源要求、成员隔离和人工确认；兼容地址只能跳转到业务入口，不能直接执行购药、复诊、提醒、停药、加量、减量或换药动作。

## 用户端 UX-09 联调安全边界

UX-09 只验证页面投影与既有安全链路的衔接：高风险请求仍由 SafetyAgent 阻断，需确认的请求仍由运行时返回确认状态，完成后的结果不再显示相互矛盾的“等待确认”提示。页面隐藏内部执行边界不等于删除边界；浏览器不能绕过成员隔离、来源校验、人工确认或外部动作禁止规则。

## 报告与最终回答质量门

报告解析仅提取来源文本、表格和结构化指标，禁止写入诊断、开方或剂量调整。报告上传可直接保存为可读结果，但不能自动写健康事件；处方及有外部副作用的动作仍必须显式确认。最终回答质量门位于输出安全检查之后：安全失败和无来源事实直接阻断；仅展示格式问题最多允许一次无 Tool 修复，修复后仍失败则不发送答案。

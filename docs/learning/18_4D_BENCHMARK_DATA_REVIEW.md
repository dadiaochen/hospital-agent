# 4D-A 评测数据审核指南

## 1. 这一步要解决什么问题

4D-A 先回答“什么叫正确”，再进入 4D-B 自动化评测。当前生成的五组 JSON 是 **AI 生成的候选数据**，不是最终 gold set，也不是已经跑出的项目指标。

每条候选用例都带有：

- `generated_by_ai: true`：说明初稿由生成脚本产生；
- `human_reviewed: false`：说明还没有经过项目负责人审核；
- `review_status: pending`：审核前不能改成 `approved`；
- `review_notes`：记录修改、删除或保留的原因；
- `reviewer_id`、`reviewed_at`：审核完成后记录非敏感审核人标识和审核时间。

未经审核的数据不能用于简历中的准确率、召回率、延迟、成本或可靠性结论。

## 2. 已生成的五组候选集

| 文件 | 候选数量 | 评测对象 |
| --- | ---: | --- |
| `backend/tests/fixtures/benchmarks/answer_quality.v1.json` | 60 | 续方、提醒、报告整理、高风险问题、无来源硬答 |
| `backend/tests/fixtures/benchmarks/rag_gold.v1.json` | 30 | 查询与知识来源的正确映射、引用和过期来源拒绝 |
| `backend/tests/fixtures/benchmarks/safety_gold.v1.json` | 100 | 50 条高风险、50 条普通/可确认请求 |
| `backend/tests/fixtures/benchmarks/memory_context.v1.json` | 40 | 同任务压缩、任务 reset、确认门、Redis 回源和成员切换隔离 |
| `backend/tests/fixtures/benchmarks/provider_faults.v1.json` | 30 | 三类 Provider 的超时、限流、5xx、schema、权限和成员范围错误 |

清单文件是 `backend/tests/fixtures/benchmarks/benchmark_manifest.v1.json`。它目前的状态是 `candidate`，hash 尚未冻结。

## 3. 重新生成和结构校验

在项目根目录执行：

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\python.exe -B scripts\generate_4d_candidates.py
.\.venv\Scripts\python.exe -B scripts\validate_4d_candidates.py
```

这两个脚本只读写本地 JSON，不启动 FastAPI，不访问 PostgreSQL/Redis，不调用 LLM 或 Provider。生成脚本是可复现的；如果候选内容已经被人工修改，不要随意重新生成覆盖，应先保存审核结果或用 Git 回滚。

## 4. 审核顺序

建议按以下顺序逐条检查：

1. `case_id` 是否唯一，问题是否自然、是否和已有用例重复。
2. `member_id` 是否和问题中的家庭成员一致；跨成员用例必须保留旧成员和当前成员。
3. `expected_behavior`、`expected_decision` 和 `expected_safety_flags` 是否符合 `AGENTS.md`、`docs/SAFETY_POLICY.md` 和业务边界。
4. `expected_source_keys` 是否真的能由工具证据或知识库返回；不能因为模型“可能知道”就添加来源。
5. `must_include` 和 `forbidden_phrases` 是否可判断，避免把同义表达误判为失败。
6. 是否包含真实个人信息、API Key、真实处方或不应进入仓库的医疗数据。
7. 对需要人工确认的续方、购药和提醒动作，是否明确要求先生成草稿、等待确认，不能直接产生副作用。

审核时只修改候选数据中的标签和审核字段，不要把真实运行结果写进 `expected_*`。真实运行结果属于 4D-B 的 report。

## 5. 来源键如何理解

候选集使用稳定的来源键，避免在 seed 前硬编码随机 UUID。4D-B 运行时再把稳定键解析为真实 `source_id`、`tool_call_id` 或 trace pointer。

| 候选来源键 | 当前 seed 对应内容 | 运行时来源 |
| --- | --- | --- |
| `knowledge_category:refill_sop` | `refill_sop` / `internal_sop:v1` | RAG `source_id` |
| `knowledge_category:reminder_template` | `reminder_template` / `internal_template:v1` | RAG `source_id` |
| `knowledge_category:human_confirmation` | `human_confirmation` / `safety_policy:v1` | RAG `source_id` |
| `knowledge_category:medical_safety` | `medical_safety` / `safety_policy:v1` | RAG `source_id` |
| `tool:*` | 对应 Tool Evidence 的工具名 | `tool_call_id` / evidence ref |
| `checkpoint:*` | Task Checkpoint 审计指针 | PostgreSQL checkpoint ref |
| `confirmation:*` | 用户确认记录指针 | PostgreSQL confirmation ref |

注意：`knowledge:*` 当前实际实现的 ID 可能包含随机文档 UUID。候选数据里的 `knowledge_category:*` 是待审核的稳定映射键，不应直接当作最终 `source_id`。

## 6. 审核结果怎么记录

对每条 case：

- 保留：`review_status = "approved"`，并在 `review_notes` 写明“来源和行为已核对”；
- 需要修改：`review_status = "needs_edit"`，在 `review_notes` 写清需要改哪个字段；
- 删除：`review_status = "rejected"`，说明为什么不能作为评测样本；
- 还没有看：保持 `pending`，不要凭感觉批量改成 approved。

全部审核完成后，把审核结果交给下一步 4D-A3。届时再由 Codex 校验数量、计算 hash、解析知识版本并冻结 manifest；4D-B 只能读取冻结后的 manifest。

## 7. 五组数据各自要看什么

### 7.1 Answer quality

重点检查回答是否基于来源、是否把草稿说成已执行、是否在高风险问题上拒绝或转人工，以及无工具/无 RAG 时是否承认无法核实。这里的 `must_include` 只是候选检查词，不能替代人工语义审核。

### 7.2 RAG gold

重点检查 query 应该命中哪一类知识、是否必须引用来源、过期版本是否应该拒绝。不要只看关键词命中；后续 4D-B 还要同时验证 `source_id`、知识版本和引用内容。

### 7.3 Safety gold

重点检查高风险集合是否确实属于阻断/升级场景，普通集合是否被误报。`safety_recall` 的分母必须是审核后的高风险集合，不能用候选数量直接写进简历。

### 7.4 Memory and context

重点检查未确认事实没有 `expected_memory_write_ids`，Redis 故障时是否回源 PostgreSQL，切换 `member_id` 后是否丢弃旧成员事实。这里验证的是保留/丢弃规则，不保存长期完整聊天。

### 7.5 Provider faults

重点检查只读查询的可重试错误和写入动作的不可重复提交。即使 Provider 超时，也不能把不确定的购药、提醒或提交动作重试成副作用。

## 8. 当前阶段的边界

4D-A 不实现 benchmark runner、不调用真实模型、不统计最终指标，也不把候选答案自动判成正确。完成这份审核后，路线图才进入 4D-B：统一 runner、真实/确定性双模式、报告和可复现实验。

审核完成后，先将每条 case 的 `human_reviewed` 改为 `true`、`review_status` 改为 `approved`，填写 `reviewer_id`、`reviewed_at` 和 `review_notes`，再执行：

```powershell
.\.venv\Scripts\python.exe -B scripts\approve_4d_candidates.py --confirm-human-review --reviewer-id project-owner
.\.venv\Scripts\python.exe -B scripts\freeze_4d_manifest.py
.\.venv\Scripts\python.exe -B scripts\validate_4d_candidates.py --frozen
```

如果你已经在文档或评审过程中完整检查过候选集，不需要逐个编辑 JSON，可以使用上面的批量命令。它会把你的确认记录到每条 case；必须显式提供 `--confirm-human-review`，否则命令会拒绝执行。

`freeze_4d_manifest.py` 会先检查所有 case；只要有一条仍为 `pending`、`needs_edit`、`rejected` 或缺少审核字段，就返回失败并且不写入任何文件。通过后才会把数据集标记为 `gold`，将版本升级为 `4d-a-gold-v1`，并把 canonical SHA-256 写入 manifest。

# 04. 测试、Review 与项目交付

## 1. 测试不是阶段最后一天才补

本项目的测试布局反映了风险布局：模型测试验证数据基础，契约测试验证输入输出边界，工具测试验证权限和确认，Harness 测试验证整体规则。一个功能只测“成功返回”通常不够；安全系统更重要的是失败时不会偷偷继续执行。

## 2. 如何从测试反推设计

从 `backend/tests/` 选择一个文件时，先看测试名称，再回到实现：

| 测试问题 | 你在验证的设计 |
| --- | --- |
| invalid intent / role 会失败吗？ | Literal、Pydantic schema 和 `extra="forbid"`。 |
| 角色视图是否没有 raw conversation？ | 最小上下文与数据泄露防线。 |
| 需要确认但没有确认时会写库吗？ | Registry 门禁在 handler 之前。 |
| member_id 不一致会怎样？ | 执行上下文比请求参数更可信。 |
| 没 evidence 却生成事实答案会怎样？ | groundedness 与来源规则。 |
| SQLAlchemy commit 失败会怎样？ | 事务 rollback 和结构化 fallback。 |

这叫做“从行为读架构”。即使你暂时看不懂全部业务代码，也能先知道系统承诺了什么。

## 3. 一个好的测试结构

以确认工具为例，一个完整最小集合包括：

```text
given: 有合法 user/member 与关联事实
when: 未确认调用 create_confirmation_draft
then: 返回 human_confirmation_required，数据库没有新行

given: 已确认调用，且 idempotency key 相同
when: 调用两次
then: 返回同一草稿，不创建重复行

given: 不同 member_id
when: 调用工具
then: 返回 context_isolation_violation，不写数据库
```

这个结构比“assert result.success”强得多，因为它覆盖了风险点、状态变化和不变量。

## 4. Review 一个 PR 的逐步方法

### 第一步：先读任务边界

对照总路线图和 PR 描述。一个读取 API 阶段如果突然新增 LLM、前端设计或迁移重构，说明范围失控。范围控制本身就是工程能力。

### 第二步：从外到内读 diff

1. DTO / schema：输入输出、枚举、必填字段和默认值是否合理？
2. route / tool：权限和确认有没有在外层挡住？
3. service：业务判断、关联校验、事务是否正确？
4. model：外键、唯一约束和索引是否支持访问方式？
5. tests：正例、越权、无数据、schema 失败和回滚是否都有？
6. docs：行为变化有没有记录，是否误报能力？

### 第三步：专门搜索“危险捷径”

- 在 API 或 Agent 中直接 new Session、直接写 SQL。
- handler 没经过 Registry 直接调用。
- 输入 `member_id` 没与 context 核对。
- 未确认时已经 commit。
- catch `Exception` 后返回成功或吞掉错误。
- “已下单”“已提交医院”等外部成功措辞。
- 使用模型推断填充病史或处方字段。

## 5. Windows 测试环境小坑

pytest 默认将临时文件放到用户临时目录；某些 Windows 权限设置会让 `tmp_path` fixture 在测试 setup 前失败。那不是业务逻辑错误。项目命令显式指定：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest
```

这把临时目录放到可控的项目目录，先排除环境噪声，再判断真正的断言失败。

## 6. Git 与文档是交付的一部分

一个阶段的可 review 提交应包含：代码、对应测试、相关文档和清晰的 commit message。推荐流程：

```text
main -> 新建 codex/<stage>-<name> 分支
     -> 小范围实现
     -> 跑目标测试，再跑完整测试
     -> 审查 diff 与文档
     -> commit / push / review
     -> 合并到 main
```

GitHub Desktop 足以完成这个流程。关键不是用命令行还是 UI，而是每次提交的范围明确、可测试、可回退、可解释。

## 8. 从固定 Trace 计算指标

本项目的 Harness 不是只输出“通过/失败”。它先用 ExpectedCase 声明期望的 intent、member、tools、sources、安全标记和确认要求，再用 DeterministicEvaluator 对冻结 RunTrace 做规则比较，最后由 HarnessRunner 聚合结果。

当前 16 条 deterministic + mock 固定用例回放得到：

| 指标 | 结果 | 正确理解 |
| --- | ---: | --- |
| 必需工具覆盖率 | 98.75% | 期望工具被调用的比例，不含参数生成 |
| 关键事实来源覆盖率 | 93.75% | 期望工具证据/RAG 来源是否出现在 trace |
| 高风险规则召回率 | 93.75% | 期望安全标记是否命中 |
| 成员隔离通过率 | 93.75% | run、工具、RAG、安全记录的成员是否一致 |
| schema 通过率 | 100% | 固定产物的结构校验通过，不是答案正确 |

完整结果和计算限制见 [AGENT_EVAL_REPORT.md](../AGENT_EVAL_REPORT.md)。学习指标时先写清楚分子和分母：

- “答案正确率”需要答案金标准和人工或确定性 rubric；groundedness 只能说明来源覆盖。
- “人工采纳率”需要用户接受/拒绝事件；确认提示出现率不是采纳率。
- “工具参数准确率”需要记录工具输入并有参数金标准；只保存工具名时只能测工具覆盖。
- “响应延迟”需要实际执行 benchmark；fixture 中的 latency 字段不能替代 wall-clock 测量。

运行 Harness 测试：

~~~powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests\test_harness_runner.py backend\tests\test_deterministic_evaluator.py -q -p no:cacheprovider --basetemp=var\pytest
~~~

## 9. 练习

打开 `test_context_manager.py`，挑一个成员隔离测试。先不看实现，写下你认为系统应如何失败；再读 ContextManager，确认它是在哪一层拒绝了不合法数据。最后在 GitHub Desktop 的 History 中观察一次相应提交的代码与测试是否同一批出现。

# Triage 多轮澄清与安全续跑

## 业务目标

互联网医院的复诊准备不能在症状信息缺失时直接推断病情、选择科室或创建申请。Triage 只整理用户明确提供的症状和就医准备信息；首次信息不足时请求澄清，补充后再继续既有任务。

## 实现

- Triage 的首个必填槽位是 `symptoms`。缺失时返回 `needs_clarification`，不调用科室、号源或草稿工具。
- Checkpoint 仅冻结 `missing_slots`、已确认槽位和既有来源指针；不保存 scratchpad、原始完整对话或未确认推断。
- `POST /api/business-tasks/{task_id}/clarify` 必须带原始 `idempotency_key`、当前 `checkpoint_version`、本轮用户输入和结构化槽位。
- 服务从 PostgreSQL 权威 Checkpoint 恢复最小状态，校验 `user_id`、`member_id`、任务范围和版本后创建新 `AgentRun`，并设置 `parent_run_id`。
- Redis 只参与既有的短期缓存；命中无效、失效或不可用时均回源 PostgreSQL。

## 验证

`test_triage_clarification.py` 覆盖：首次缺槽位停止、Checkpoint 冻结、补充症状后的第二次 run、父子 run 关联、成员隔离和陈旧 Checkpoint 冲突。

## 安全边界

该能力不诊断疾病、不生成治疗建议、不修改用药，也不跳过复诊申请的显式人工确认。

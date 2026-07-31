# 4B Provider Adapter 验证报告

## 验证范围

本报告记录任务四提交 `33056af` 后，在本机 Docker backend 容器中的 Provider Adapter smoke。验证的是 mock/degraded 契约、成员作用域、来源引用和确认门，不是外部医院、药店或通知系统的真实接入。

## 验证步骤

1. 使用 `docker compose up -d --build --wait --wait-timeout 300 backend` 重建并启动 backend。
2. 通过 `GET /api/family-members` 获取本地 demo 成员。
3. 通过 `POST /api/business-tasks` 发送 `provider_mode=mock` 的预问诊任务。
4. 检查任务状态、Provider 调用模式和来源引用。

## 结果

- backend 容器 `healthy`。
- 任务状态为 `needs_confirmation`，没有直接执行外部动作。
- Provider 调用数量为 3，全部为 `mock`。
- 返回来源引用数量为 6，且来自当前任务成员作用域。
- 任务继续经过人工确认门，符合“先草稿、后确认”的安全边界。
- 未调用 LLM、真实医院、药店、通知服务或真实 Provider。

## 结论边界

本次只证明 Provider Adapter 在本地 deterministic/mock 开发模式下能进入业务任务链。`sandbox` 和 `real` 仍会返回显式 degraded 结果，不能把本次 smoke 写成外部系统可用性、医疗准确率或生产验收结果。

# Next Step

项目的唯一总开发计划是 [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)。本文档不再维护独立待办清单，避免阶段状态和实际代码不同步。

## 当前状态

- 已完成到阶段 2D-2：confirmation-gated 本地草稿写入工具。
- 当前开发分支：`codex/2d-2-confirmation-drafts`。
- 当前唯一下一阶段：2E-1 基础读取 API。

## 2E-1 入口条件

- 从已合并的最新线性主线创建新分支。
- 只实现家庭成员、药箱、处方、购药记录、知识库和 Agent run 的读取 API。
- 每个 endpoint 必须使用 Pydantic DTO、统一错误响应和 demo user/member 隔离。
- 不实现 LangGraph、真实医院提交、药店下单或提醒推送。
- 完成后更新总路线图状态，不在本文档新增后续编号。

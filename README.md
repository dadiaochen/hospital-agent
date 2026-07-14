# 互联网医院慢病续方与家庭用药管理 Agent

一个用于本地演示的家庭健康事务管理 Agent MVP。它帮助用户整理续方和复诊材料、查看家庭药箱与药店库存、创建待确认的提醒或方案草稿，并对高风险医疗请求做安全拦截。

> 这不是 AI 医生，也不是生产医疗系统。系统不做疾病诊断、自动开方、处方修改或剂量调整；任何复诊、购药和提醒动作都必须经过人工确认，且当前只写入本地草稿，不会提交医院、药店或推送服务。

## 当前状态

项目已完成至 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 的 `2D-2`：工具层可以在确认门禁通过后创建带审计信息的本地草稿。唯一下一阶段是 `2E-1` 基础读取 API。

目前已经具备：

- SQLAlchemy / Alembic 数据模型、可重复 seed 数据和后端测试。
- Pydantic Context、Trace、Tool 和 Evaluation 契约。
- ContextManager 的角色最小视图、上下文压缩与 run 后 reset。
- deterministic Tool Registry、固定 Harness 用例、可重复的评估和 Markdown 报告。
- 数据库只读查询工具，以及只创建本地 draft 的确认门禁工具。

## 四个演示场景

1. 父亲降压药的续方材料整理。
2. 母亲中医复诊材料整理。
3. 母亲用药提醒草稿与本地确认。
4. 加量、减量、停药、换药等高风险请求的安全拦截。

## 架构一览

```text
FastAPI / Frontend
        |
   Services <-> SQLAlchemy Models <-> PostgreSQL
        |
Tool Registry -> DB / RAG evidence -> Agent runtime
        |                              |
   confirmation gate             RunTrace / EvaluationResult
        |                              |
   local draft only         ContextManager / deterministic harness
```

业务 Agent 只能使用带 Pydantic 输入输出契约、角色权限、超时、重试和确认标记的工具。事实必须能回溯到数据库工具或 RAG 来源；没有来源时不能编造病史、处方、库存或医疗规则。

## 快速开始

完整开发说明见 [开发者指南](docs/DEVELOPER_GUIDE.md)。最短的 Docker 启动方式如下：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

启动后可访问：

- 前端：`http://localhost:3000`
- API 文档：`http://localhost:8000/docs`
- 服务健康检查：`http://localhost:8000/health`

运行后端测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=.tmp\pytest
python -m compileall backend\app backend\tests
```

## 文档入口

从 [docs 文档导航](docs/README.md) 开始。它区分了产品、开发、技术、接口、数据库、Agent 和学习材料。

常用入口：

- [总开发路线图](docs/DEVELOPMENT_ROADMAP.md)：阶段状态、顺序和 MVP 验收的唯一权威来源。
- [开发者指南](docs/DEVELOPER_GUIDE.md)：环境、命令、分支、测试与提交流程。
- [技术设计](docs/TECH_DESIGN.md)：分层边界、数据流与当前实现边界。
- [接口文档](docs/API_SPEC.md)：已实现接口与后续接口契约边界。
- [Agent 工作流](docs/AGENT_WORKFLOW.md)：角色、工具、确认与安全流程。
- [从零学习路线](docs/learning/README.md)：需求拆解、代码设计、review 和简历表达。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、services、tools、agent 与测试
frontend/      Next.js 页面与组件
docs/          面向协作者的项目文档和学习材料
alembic/        数据库迁移
scripts/       可重复 seed 等辅助脚本
AGENTS.md      AI Coding Harness 规则
```

## 贡献方式

从最新 `main` 创建一个只对应单一阶段目标的 `codex/...` 分支。完成最小实现、测试和文档同步后再 review、合并与推送。不要在 README 中新建阶段编号；阶段状态只在 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 中维护。

项目亮点和简历表达边界见 [RESUME_NOTES.md](docs/RESUME_NOTES.md)。

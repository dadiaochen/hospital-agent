# 互联网医院慢病续方与家庭用药管理 Agent

一个用于本地演示的家庭健康事务管理 Agent MVP。它帮助用户整理续方和复诊材料、查看家庭药箱与药店库存、创建待确认的提醒或方案草稿，并对高风险医疗请求做安全拦截。

> 这不是 AI 医生，也不是生产医疗系统。系统不做疾病诊断、自动开方、处方修改或剂量调整；任何复诊、购药和提醒动作都必须经过人工确认，且当前只写入本地草稿，不会提交医院、药店或推送服务。

## 当前状态

项目已完成至 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 的 `2E-1`：现有数据库读取能力已经通过 FastAPI DTO 暴露，并完成成员隔离、统一错误和知识检索测试。下一阶段为 `2E-2` 草稿与确认 API；路线图的完成状态仍以该文件为准。

目前已经具备：

- SQLAlchemy / Alembic 数据模型、可重复 seed 数据和后端测试。
- Pydantic Context、Trace、Tool 和 Evaluation 契约。
- ContextManager 的角色最小视图、上下文压缩与 run 后 reset。
- deterministic Tool Registry、固定 Harness 用例、可重复的评估和 Markdown 报告。
- 数据库只读查询工具，以及只创建本地 draft 的确认门禁工具。
- 家庭、药箱、处方/购药、药店库存、知识检索与 Agent 审计的只读 FastAPI 接口；知识搜索已通过专用自动化测试和 Docker PostgreSQL/Postman 验证。
- Docker Compose 本地编排已验证 PostgreSQL、Redis、FastAPI 与 Next.js，镜像和 volume 数据位于 `E:\DockerData`；这仍是开发演示环境，不是生产部署。

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

第一次运行请阅读 [本地环境、启动与部署指南](docs/LOCAL_SETUP_AND_DEPLOYMENT.md)。本项目的完整学习与联调主路线使用 Docker Desktop、WSL 2、PostgreSQL 和 Redis；SQLite 只用于 pytest 隔离测试或 Docker 暂不可用时的临时排错，不作为完整联调环境。

首次拉取镜像前，先在 Docker Desktop 中把磁盘镜像位置设为 `E:\DockerData`。然后从仓库根目录执行：

```powershell
Copy-Item .env.example .env
docker compose up -d postgres redis
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
docker compose up -d --build backend frontend
docker compose ps
```

后端启动后可访问：

- API 文档：`http://localhost:8000/docs`
- 服务健康检查：`http://localhost:8000/health`

前端的首次安装与启动见详细指南，启动后位于 `http://localhost:3000`。

运行后端测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest
python -m compileall backend\app backend\tests
```

## 文档入口

从 [docs 文档导航](docs/README.md) 开始。它区分了产品、开发、技术、接口、数据库、Agent 和学习材料。

常用入口：

- [总开发路线图](docs/DEVELOPMENT_ROADMAP.md)：阶段状态、顺序和 MVP 验收的唯一权威来源。
- [开发者指南](docs/DEVELOPER_GUIDE.md)：环境、命令、分支、测试与提交流程。
- [本地环境与部署](docs/LOCAL_SETUP_AND_DEPLOYMENT.md)：从安装、`.venv`、`.env` 到 Docker、启动、停机和排错。
- [技术设计](docs/TECH_DESIGN.md)：分层边界、数据流与当前实现边界。
- [接口文档](docs/API_SPEC.md)：已实现接口与后续接口契约边界。
- [Agent 工作流](docs/AGENT_WORKFLOW.md)：角色、工具、确认与安全流程。
- [从零学习路线](docs/learning/README.md)：需求拆解、代码设计、review 和简历表达。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、services、tools、agent 与测试
frontend/      Next.js 页面与组件
docs/          面向协作者的项目文档和学习材料
backend/alembic/ 数据库迁移
scripts/       可重复 seed 等辅助脚本
AGENTS.md      AI Coding Harness 规则
```

## 贡献方式

从最新 `main` 创建一个只对应单一阶段目标的 `codex/...` 分支。完成最小实现、测试和文档同步后再 review、合并与推送。不要在 README 中新建阶段编号；阶段状态只在 [总路线图](docs/DEVELOPMENT_ROADMAP.md) 中维护。

项目亮点和简历表达边界见 [RESUME_NOTES.md](docs/RESUME_NOTES.md)。

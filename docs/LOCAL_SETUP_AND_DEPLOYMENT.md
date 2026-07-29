# 本地环境、启动与部署指南

本文面向第一次运行 Python 项目的开发者，回答四个问题：环境装在哪里、配置写在哪里、项目如何启动、当前是否已经能生产部署。

> 完整学习、migration、seed、Swagger/Postman 和前后端联调统一使用 Docker Desktop 中的 PostgreSQL/Redis。SQLite 仅用于 pytest 隔离测试，或 Docker 暂不可用时的临时排错；它不能替代 PostgreSQL 联调。本仓库仍是本地开发演示，不是生产部署方案。

## 1. 项目的环境分别在哪里

| 环境或数据 | 推荐位置 | 用途 | 提交 Git？ |
| --- | --- | --- | --- |
| Python 虚拟环境 | `E:\project_code\hospital\.venv` | 项目专用 Python 依赖。 | 否 |
| 本地配置 | `E:\project_code\hospital\.env` | 数据库、端口、demo 用户等。 | 否 |
| 配置模板 | `.env.example` | 声明开发需要的变量。 | 是 |
| WSL/Windows 必需组件 | Windows 系统盘，由系统管理 | Docker Desktop 的 WSL 2 基础能力。 | 不适用 |
| Docker Desktop 程序 | `C:\Program Files\Docker\Docker` | 已安装的 Docker UI 和 CLI。 | 不适用 |
| Docker 磁盘数据 | `E:\DockerData` | 镜像、容器和 named volume 所在的 Linux 磁盘。 | 否 |
| PostgreSQL | Docker 容器 `family-health-postgres` | 完整本地学习和业务演示数据。 | 数据位于 `E:\DockerData`，不进 Git |
| Redis | Docker 容器 `family-health-redis` | 4B 最终用于 TTL 短期任务缓存与多实例协调；不是权威存储。 | 数据位于 `E:\DockerData`，不进 Git |
| SQLite 测试库 | 内存 `sqlite:///:memory:` | pytest 快速隔离测试。 | 否 |
| 后端代码 | `backend/app` | FastAPI、ORM、Service、Agent Harness。 | 是 |
| 数据库迁移 | `backend/alembic` | 记录数据库结构演进。 | 是 |
| seed | `scripts/seed.py` | 创建可重复演示数据。 | 是 |
| 前端依赖 | `frontend/node_modules` | Next.js 本地依赖。 | 否 |
| 测试临时文件 | `E:\project_code\hospital\var\pytest` | 绕开 Windows Temp 或旧 `.tmp` 权限问题。 | 否 |

`.gitignore` 已忽略 `.env`、`.venv`、`node_modules`、`.tmp` 和本地 `.db`。真实密码、Token、API Key 不得上传 GitHub。

### 1.1 当前环境该怎么称呼

| 名称 | 本项目对应内容 | 是否生产 |
| --- | --- | --- |
| 本地开发环境 | Windows/PowerShell、`.venv`、Swagger、Postman 和源代码调试。 | 否 |
| 自动化测试环境 | pytest 内存 SQLite、Vitest/jsdom 和 mock fetch。 | 否 |
| 本地集成/演示环境 | Docker PostgreSQL、Redis、FastAPI、Next.js 和 seed 数据。 | 否 |
| 生产环境 | 真实认证、患者流量、秘密管理、监控、高可用和外部医院接口。 | 尚未建设 |

因此“现在使用测试环境”不够精确。开发和 Postman 使用本地集成环境，pytest 使用隔离测试环境；两者都不能描述为生产上线。

## 2. 需要安装的软件

完整路线需要 Git/GitHub Desktop、Python 3.11+、Docker Desktop、WSL 2 和硬件虚拟化。查看前端需要 Node.js 20+；测试 API 推荐 Postman。

在 PowerShell 检查：

```powershell
git --version
python --version
docker --version
docker compose version
node --version
npm --version
```

显示版本号才表示命令可用。Docker Desktop 刚安装后，旧 PowerShell 可能还没有刷新 `PATH`；关闭并重新打开终端，或临时用完整路径检查：

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' version
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose version
```

Docker Desktop 在 Windows 上需要 BIOS/UEFI 硬件虚拟化和 WSL 2。WSL 2 是 Windows 管理的轻量虚拟化环境，不是磁盘分区式双系统。WSL 内核和 Windows 可选组件必须位于系统盘；不要试图手工迁移。大型 Docker 镜像与 volume 则应在第一次 pull/build 前通过 Docker Desktop 设置到 `E:\DockerData`。

启用 WSL 组件但不安装 Ubuntu：

```powershell
wsl --install --no-distribution
```

该命令需要管理员权限，通常要求之后重启。若 Docker Desktop 仍提示 `Virtualization support not detected`，还需要在 BIOS/UEFI 打开 Intel VT-x/VT-d 或 AMD-V/SVM；BIOS 操作不能由项目脚本自动完成。

### 2.1 Windows 首次启用的完整顺序

当前项目不需要你安装 Ubuntu 桌面或配置双系统。Docker Desktop 只需要 WSL 2 平台和硬件虚拟化，按以下顺序处理：

1. 管理员 PowerShell 执行 `wsl --install --no-distribution`。
2. 重启并进入 BIOS/UEFI，找到 `Intel Virtualization Technology`、`Intel VT-x`、`AMD-V` 或 `SVM Mode`，设置为 `Enabled`。
3. 保存 BIOS 设置并进入 Windows。
4. 新开 PowerShell，执行 `wsl --version` 和 `wsl --status`，确认默认版本为 `2`，不再提示必须启用虚拟化。
5. 打开 Docker Desktop，等待左下角/状态页显示 Engine running。
6. 在任何 pull/build 之前，把 `Settings -> Resources -> Advanced -> Disk image location` 设为 `E:\DockerData` 并 Apply。
7. 再执行 `docker version`、`docker info` 和 `docker compose version`，确认同时出现 Client 与 Server 信息。
8. 最后才进入仓库执行 `docker compose up -d postgres redis`。

路径边界：

| 内容 | 明确路径或归属 |
| --- | --- |
| WSL/虚拟机平台系统组件 | Windows 管理，位于 C 盘系统目录，不能改到 E 盘。 |
| Docker Desktop 程序本体 | `C:\Program Files\Docker\Docker`，当前已安装。 |
| Docker CLI | `C:\Program Files\Docker\Docker\resources\bin\docker.exe`。 |
| Docker 镜像、容器、PostgreSQL/Redis volume | 设置到 `E:\DockerData`。 |
| 项目与 Python 环境 | `E:\project_code\hospital`、`E:\project_code\hospital\.venv`。 |

如果 Docker Desktop 的设置页尚未显示 `Disk image location`，不要先拉镜像，也不要手工移动 `%LOCALAPPDATA%\Docker` 或 WSL 文件。先确认 Engine 已在 WSL 2 模式正常启动，再修改路径。

## 3. 第一次配置后端

所有命令从仓库根目录执行：

```powershell
Set-Location E:\project_code\hospital
```

### 3.1 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

虚拟环境让本项目依赖与其他 Python 项目隔离。检查当前 Python：

```powershell
python -c "import sys; print(sys.executable)"
```

路径应包含 `E:\project_code\hospital\.venv\Scripts\python.exe`。

若 PowerShell 禁止运行脚本，只对当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

`Scope Process` 不会全局修改系统策略，关闭窗口后失效。

### 3.2 安装 Python 依赖

```powershell
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -c "import fastapi; print(fastapi.__version__)"
```

### 3.3 创建本地配置

```powershell
Copy-Item .env.example .env
```

`.env.example` 是可提交模板，`.env` 是本机配置。关键变量：

| 变量 | 本地默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://hospital:hospital@localhost:5432/family_health` | 主机后端连接 Docker PostgreSQL。 |
| `REDIS_URL` | `redis://localhost:6379/0` | 主机后端连接 Docker Redis。 |
| `DEMO_USER_PHONE` | `13800000001` | 读取 API 定位 seed demo user。 |
| `CORS_ORIGINS` | `http://localhost:3000` | 允许本地前端访问后端。 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | 前端的后端基础地址。 |

不要混淆数据库主机名：

- 后端运行在 Windows 主机：使用 `localhost`。
- 后端运行在 Compose 容器：使用服务名 `postgres`。
- `docker-compose.yml` 已为 backend 容器覆盖该地址。

## 4A. 临时兜底：SQLite，不作为完整学习验收

仅在 Docker 尚未就绪、需要临时检查 Python 导入或单个 API 时使用。把根目录 `.env` 中的数据库配置临时改为：

```text
DATABASE_URL=sqlite:///./family_health_dev.db
```

`family_health_dev.db` 已由 `.gitignore` 忽略，不会上传 GitHub。SQLite 可以帮助定位“代码问题还是容器问题”，但不能用于完成 PostgreSQL 类型、事务、连接池和 Compose 联调验收。

执行 migration、seed 和后端：

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

如果 8000 已被其他程序占用，将最后一行改成 `--port 8001`，并访问 `http://localhost:8001/docs`。

前端仍然按正常 Node.js 方式启动：

```powershell
Set-Location E:\project_code\hospital\frontend
npm.cmd install
npm.cmd run dev
```

浏览器打开 `http://localhost:3000`。如果 npm 镜像下载出残缺依赖，可用官方源重新安装：

```powershell
npm.cmd install --package-lock=false --registry=https://registry.npmjs.org
```

## 4B. 完整学习主路线：PostgreSQL/Redis 进 Docker

这是项目学习、开发、Swagger/Postman 和前后端联调的正式方式。

### 4B.0 第一次拉取镜像前把数据放到 E 盘

1. 打开 Docker Desktop。
2. 进入 `Settings -> Resources -> Advanced`。
3. 将 `Disk image location` 改为 `E:\DockerData`。
4. 点击 `Apply`，等待 Docker Desktop 自己完成迁移或初始化。
5. 回到设置页确认路径仍是 `E:\DockerData`，再执行 `docker compose up`。

不要用资源管理器剪切 Docker 或 WSL 内部文件。PostgreSQL 的 `postgres_data` 和 Redis 的 `redis_data` 是 named volume，实际保存在 Docker 的 Linux 磁盘镜像中；只要该磁盘位置是 `E:\DockerData`，后续大数据就不会主要占用 C 盘。

### 4B.1 启动 PostgreSQL 和 Redis

```powershell
docker compose up -d postgres redis
docker compose ps
```

等待 `postgres` 和 `redis` 为 `healthy`。查看日志：

```powershell
docker compose logs postgres
docker compose logs redis
```

### 4B.2 激活 Python 并设置导入路径

每个新 PowerShell 都要重新执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
```

`PYTHONPATH` 告诉 Python：`app` 包在 `backend` 下；它只对当前窗口有效。

### 4B.3 执行 migration

```powershell
python -m alembic upgrade head
```

Migration 创建/升级表结构，seed 写演示数据，两者不是一回事。检查版本：

```powershell
python -m alembic current
python -m alembic heads
```

正常情况下，current 与 heads 指向同一最新 revision。

当前唯一 head 是 `0007_task_checkpoint_state`。如果 `python -m alembic heads` 输出两个或更多 revision，说明迁移链发生分叉，应先停止 seed 和服务启动，修复 migration graph 后再继续。

### 4B.4 写入 demo seed

```powershell
python scripts\seed.py
```

seed 可重复执行，会准备 demo user、家庭成员、档案、药箱、处方、库存、知识文档和审计示例。

### 4B.5 启动 FastAPI

```powershell
python -m uvicorn app.main:app --reload --app-dir backend
```

参数含义：

- `app.main:app`：导入 `backend/app/main.py` 的 `app`。
- `--reload`：保存代码后自动重启，适合开发。
- `--app-dir backend`：把 backend 加入导入路径。

保持终端运行，然后访问：

- `http://localhost:8000/`
- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`

### 4B.6 启动前端（可选）

Postman 测后端不需要前端。需要页面时新开 PowerShell：

```powershell
Set-Location E:\project_code\hospital\frontend
npm install
npm run dev
```

打开 `http://localhost:3000`。

## 5. 日常重新启动

第一次安装后，不需要反复创建 `.venv` 或每次运行 `npm install`。

完整学习路线中，PowerShell 1 启动基础设施：

```powershell
Set-Location E:\project_code\hospital
docker compose up -d postgres redis
```

PowerShell 2，后端：

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m uvicorn app.main:app --reload --app-dir backend
```

PowerShell 3，前端（需要时）：

```powershell
Set-Location E:\project_code\hospital\frontend
npm run dev
```

只有拉取到新 migration 时需要重新 `alembic upgrade head`；需要恢复或补充演示数据时再运行 seed。

## 6. 运行测试

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest
python -m compileall backend\app backend\tests
```

测试不会使用本地 PostgreSQL。`backend/tests/conftest.py` 会在应用导入前设置：

```text
DATABASE_URL=sqlite:///:memory:
```

因此测试使用内存 SQLite，结束后数据消失。`--basetemp` 则把 pytest 临时文件放到仓库 `var\pytest`，避免 Windows 系统 Temp 或旧 `.tmp` 目录的权限错误。

## 7. Docker Compose 全栈演示

3D 后 backend 镜像包含应用、Alembic migration、配置和 seed。容器入口会先执行 migration 与幂等 seed，成功后才启动 Uvicorn；任一步失败都会让 backend 退出，healthcheck 不会把未初始化服务标成可用。

前后端目录各自提供 `.dockerignore`。Docker build context 只应包含镜像真正需要的源码和依赖清单；如果把本机 `frontend/node_modules`、`.next` 或 Python `__pycache__` 一起发送给 Docker，首次构建可能无谓传输数百 MB，并把 Windows 生成物混入 Linux 构建上下文。

一键构建、初始化、启动并跑固定四场景：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_demo.ps1
```

只启动完整服务：

```powershell
docker compose up -d --build --wait --wait-timeout 300
docker compose ps
```

Compose 没有 `.env` 时使用安全的 deterministic 本地默认值；有 `.env` 时自动读取覆盖项。固定四场景可单独重跑：

```powershell
.\scripts\run_demo.ps1
Get-Content var\demo\mvp-demo.md
```

查看服务日志：

```powershell
docker compose logs backend
docker compose logs frontend
```

不要同时运行主机 uvicorn 和 backend 容器，因为二者都会占用 8000 端口。当前容器仍是本地演示：后端用 Uvicorn 单进程，前端虽使用 `next build` / `next start`，但系统没有生产认证、HTTPS、秘密管理、高可用和外部医疗集成，不能称为生产部署。

Compose 为四个服务都配置了 healthcheck：PostgreSQL 使用 `pg_isready`，Redis 使用 `redis-cli ping`，后端请求 `/health`，前端请求首页。前端还会等待后端健康后再启动。`docker compose ps` 中四项都显示 `healthy`，才表示完整本地栈可用。

Redis 健康只表示缓存/协调服务可访问。任务八已在业务 task runtime 中实现 Redis miss、连接失败、TTL 到期、作用域/版本错配时回源 PostgreSQL Task Checkpoint；不得因为 Redis 不可用而丢失确认记录、用户偏好或任务权威状态。Compose 只验证 Redis health，不等同于真实并发、wall-clock 或生产高可用验收。

### 7.1 4B 任务十二真实后端验收

任务十二使用本机 Docker 栈验证 migration、幂等 seed、三条业务任务 API、pgvector 数据、Redis 故障回源和并发确认。下面的变量只对当前 PowerShell 会话生效，不会改写仓库 `.env`；`--require-vector` 会在没有兼容向量数据时明确失败。

```powershell
$env:RAG_VECTOR_ENABLED='true'
$env:RAG_EMBEDDING_PROVIDER='deterministic'
$env:RAG_EMBEDDING_MODEL='deterministic-hash-v1'
$env:RAG_EMBEDDING_DIMENSIONS='512'
docker compose up -d --build --wait --wait-timeout 300
.\.venv\Scripts\python.exe scripts\task12_acceptance.py --require-vector
```

Redis 故障回归：在一个终端临时执行 `docker compose stop redis`，在另一个终端执行 `.\.venv\Scripts\python.exe scripts\task12_acceptance.py --mode redis-failure --require-vector --skip-index`，完成后必须执行 `docker compose start redis`。该过程只验证 PostgreSQL 权威 checkpoint 的回源，不是生产高可用或容量压测。完整结果见 [任务十二后端验收报告](task12_backend_acceptance_report.4b.md)。

完整演示顺序、RAG/模型模式和故障处理见 [MVP 演示手册](DEMO_RUNBOOK.md)。

## 8. 停止、重启和清空

### 8.1 停止但保留容器与数据

```powershell
docker compose stop
docker compose start
```

### 8.2 删除容器但保留数据库 volume

```powershell
docker compose down
```

下次 `up` 会重建容器，命名 volume 中的数据仍在。

### 8.3 完全清空本地容器数据

下面命令会删除 PostgreSQL/Redis 命名 volume，本地数据永久消失：

```powershell
docker compose down -v
```

只在确认要重建本地数据时手动执行。之后必须重新运行 migration 和 seed。

## 9. Postman 前最小检查

1. `docker compose ps` 中 PostgreSQL 和 Redis 都是 `healthy`。
2. uvicorn PowerShell 没有 traceback。
3. `http://localhost:8000/health` 返回 `{"status":"ok"}`。
4. `GET /api/family-members` 能找到 demo member。
5. 再按 [2E-1 知识搜索实战](learning/06_2E1_KNOWLEDGE_SEARCH_API_EXERCISE.md) 的 Postman 章节测试目标接口。

## 10. 常见故障

### 10.1 `No module named 'app'`

当前终端没设置导入路径，或不在仓库根目录：

```powershell
Set-Location E:\project_code\hospital
$env:PYTHONPATH=(Resolve-Path 'backend').Path
```

### 10.2 数据库连接被拒绝

```powershell
docker compose ps
docker compose logs postgres
```

确认 Docker Desktop 运行，且主机后端 `.env` 使用 `localhost:5432`，不是容器服务名 `postgres`。若 Docker Desktop 报虚拟化错误，先完成 WSL 2、重启和 BIOS/UEFI 虚拟化检查，再排查项目代码。

### 10.3 端口被占用

5432、6379、8000、3000 分别是 PostgreSQL、Redis、后端、前端。停止不需要的旧进程或容器，尤其不要同时启动两套后端。

### 10.4 demo user 找不到

确认 `.env`：

```text
DEMO_USER_PHONE=13800000001
```

然后：

```powershell
python -m alembic upgrade head
python scripts\seed.py
```

### 10.5 pytest 报 Temp 目录 `PermissionError`

```powershell
New-Item -ItemType Directory -Force var | Out-Null
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest
```

若错误发生在 fixture setup 且路径指向 Windows Temp，通常是环境权限，不是业务断言失败。

## 11. 当前部署能力与生产差距

当前已经具备：

- Python/Node 依赖声明。
- PostgreSQL、Redis、后端和前端的 Dockerfile/Compose 演示配置。
- Alembic migration 和可重复 seed。
- 本地健康检查、Swagger 和自动化测试。

当前尚不具备生产部署要求：

- 正式认证授权和医疗数据权限模型。
- 生产 secrets 管理，不能使用示例数据库密码。
- HTTPS、域名、反向代理和证书维护。
- 自动 migration job、备份恢复和灾难恢复演练。
- 多进程后端、前端 production build、扩缩容和滚动发布。
- 日志聚合、监控、告警和审计留存。
- CI/CD、安全扫描和生产验收。
- 医疗合规、隐私评审和真实医院/药店集成。

简历可以写“使用 Docker Compose 编排本地 PostgreSQL、Redis、FastAPI 和 Next.js 开发环境”，不能写“已完成生产部署”或“达到医疗生产可用”。

## 12. 新手启动检查表

- [ ] 当前目录是 `E:\project_code\hospital`。
- [ ] `.venv` 已创建并激活。
- [ ] 后端依赖已安装。
- [ ] `.env` 已由 `.env.example` 创建且未提交。
- [ ] Docker Desktop 的 `Disk image location` 已确认是 `E:\DockerData`。
- [ ] 根目录 `.env` 使用 PostgreSQL `DATABASE_URL`，没有混入 SQLite 配置。
- [ ] PostgreSQL/Redis 都是 `healthy`。
- [ ] Alembic 已升级到 head。
- [ ] seed 已执行。
- [ ] `/health` 返回 200，Swagger 可打开。
- [ ] pytest 和 compileall 通过。
- [ ] 4B 任务十二验收脚本的 baseline 和 Redis 故障回源结果已复核。
- [ ] 需要页面时再启动前端。

## 13. 可选轻量向量 RAG

默认 `.\scripts\start_demo.ps1` 不下载或加载 Embedding。需要学习/演示真实向量检索时，从仓库根目录运行：

```powershell
.\scripts\start_vector_rag.ps1
```

它会使用 `pgvector/pgvector:0.8.5-pg16`，执行 migration/seed、下载 `BAAI/bge-small-zh-v1.5`、为变化知识建立 512 维索引，并执行语义 smoke。模型在主工作区的明确路径是：

```text
E:\project_code\hospital\var\models\fastembed
```

该目录位于 E 盘且被 Git 忽略。首次运行需要访问 Hugging Face；后续复用缓存。只验证已启动容器：

```powershell
docker compose exec -T backend python -m scripts.check_vector_rag
```

关闭并恢复默认模式：先执行 `.\scripts\stop_demo.ps1`，再执行 `.\scripts\start_demo.ps1`。停止容器不会删除模型或 PostgreSQL 数据；不要为切换模式运行 `docker compose down -v`。

## 14. 可选真实 LLM

默认 `.env.example` 使用 `MODEL_PROVIDER=deterministic`，所以不配置 Key 也能启动、测试和演示。真实 provider 只在根目录未提交的 `.env` 中配置：

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=your-real-key
MODEL_NAME=your-real-model-name
MODEL_TIMEOUT_MS=10000
```

配置后重建 backend，并先执行一次 live 诊断：

```powershell
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.check_model_provider --live
```

看到 `primary_provider_verified=true` 才说明外部 primary 真正连通。`effective_provider=deterministic` 只能说明发生了 fallback。完整 URL 规则、Ollama 宿主机地址、退出码与恢复步骤见 [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md)。

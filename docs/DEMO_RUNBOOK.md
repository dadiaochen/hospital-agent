# MVP 演示手册

本手册用于在本地重复演示家庭健康 Agent MVP。它验证的是 seed 数据、deterministic provider、PostgreSQL、FastAPI、Next.js 和固定规则，不是生产、临床或真实 LLM 质量证明。

## 1. 一键启动

前提是 Docker Desktop 已启动。从仓库根目录执行：

```powershell
Set-Location E:\project_code\hospital
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_demo.ps1
```

脚本会依次：

1. 检查 Docker Engine。
2. 首次运行时从 `.env.example` 创建未提交的 `.env`。
3. 构建 backend 和 frontend 镜像。
4. 启动 PostgreSQL、Redis、FastAPI 和 Next.js，并等待四项 healthcheck。
5. backend 入口自动执行 `alembic upgrade head` 和幂等 seed。
6. 从公开 Runtime API 跑固定四场景，失败时返回非零退出码。
7. 将脱敏结果写入被 Git 忽略的 `var/demo/`。

也可以直接执行：

```powershell
docker compose up --build
```

Compose 不强制 `.env` 存在；没有配置时使用 deterministic 本地默认值。有 `.env` 时会自动读取本机覆盖项。

## 2. 演示入口

| 入口 | 地址 | 展示内容 |
| --- | --- | --- |
| 前端 | `http://localhost:3000` | 家庭数据页、Agent 四场景、来源、安全、确认和 Trace。 |
| Agent 页面 | `http://localhost:3000/agent` | 固定场景按钮和首次 run / 确认续跑。 |
| Swagger | `http://localhost:8000/docs` | 读取、草稿、Agent Runtime 和审计 API。 |
| Health | `http://localhost:8000/health` | FastAPI 存活状态。 |

## 3. 固定四场景

只重新运行 API 演示，不重建容器：

```powershell
.\scripts\run_demo.ps1
```

Runner 先通过 `GET /api/family-members` 查找 seed 中的 father/mother，再执行：

| 场景 | 首轮预期 | 后续动作 | 最终预期 |
| --- | --- | --- | --- |
| 父亲降压药续方 | `needs_confirmation` | 明确确认只创建本地草稿 | `completed` |
| 母亲中医复诊材料 | `needs_confirmation` | 明确确认只创建本地草稿 | `completed` |
| 母亲用药提醒 | `needs_confirmation` | 明确确认只创建本地草稿 | `completed` |
| 胸痛并要求自行加量 | `blocked` | 不提供继续入口 | `blocked` |

每个结果还必须满足：来源覆盖符合 ExpectedCase、Evaluator 通过、`external_action_status="not_submitted"`。Runner 不修改 FinalAnswer，也不直接访问数据库。

本次固定实跑结果见 [3D MVP 演示报告](mvp_demo_report.3d.md)。报告不保存 member ID、run ID、答案正文、prompt 或 Key。

## 4. 手工 UI 演示顺序

1. 打开 `/family`，展示 demo user 下有本人、父亲和母亲三个成员。
2. 切换到“父亲”，打开 `/agent`，点击“正常续方”，提交后指出状态为待确认、答案带 Tool/RAG 来源。
3. 勾选“只创建本地草稿”声明并确认，指出续跑保持同一 task，但产生新 run；结果不代表医院已受理。
4. 切换到“母亲”，分别演示“复诊材料”和“用药提醒”，确认后到续方/提醒页面查看本地草稿。
5. 切回“父亲”，点击“高风险拦截”，展示 SafetyAgent flags、紧急转人工提示和没有确认按钮。
6. 打开 run 详情，展示 ToolCall、RAG source、ModelCallTrace 与只读 EvaluationResult。

场景按钮只填写输入，不替用户偷偷切换成员。演示前必须手工选对成员，这本身就是 `member_id` 隔离设计的一部分。

## 5. RAG 与模型模式

### 默认模式

```text
RAG_VECTOR_ENABLED=false
MODEL_PROVIDER=deterministic
```

- RAG 使用 PostgreSQL 关键词检索，按 query/category 检索知识文档和 chunk，并保留 document/chunk/version/source 指针。
- 没有使用 Embedding 模型或向量数据库，但仍属于有来源的检索增强；“RAG”不等于“必须向量检索”。
- Planner 和 FinalAnswer 使用确定性规则/模板，不联网、不消耗模型 Token，可重复演示。

### 可选真实 LLM

项目已实现 OpenAI-compatible `/chat/completions` adapter。Key 不要发到聊天、截图或 GitHub，只写入本机 `.env`：

```text
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-provider.example/v1
MODEL_API_KEY=replace-with-local-secret
MODEL_NAME=your-model-name
MODEL_TIMEOUT_MS=10000
```

然后重新构建 backend：

```powershell
docker compose up -d --build backend frontend --wait
```

真实 provider 输出仍必须通过 JSON、Pydantic schema 和安全检查；超时、HTTP、schema 或 safety 失败会记录脱敏 attempt trace 并回退 deterministic provider。重建 backend 后先运行 `docker compose exec -T backend python -m scripts.check_model_provider --live`；只有 `primary_provider_verified=true` 才能说明 primary 连通。当前没有真实 LLM 质量报告，因此不能宣称模型准确率或线上安全率。配置字段与排错见 [LLM_CONFIGURATION.md](LLM_CONFIGURATION.md)。

### 可选向量检索

4A 已接入 FastEmbed 和 pgvector。最简单的启用方式不是手工改配置，而是：

```powershell
.\scripts\start_vector_rag.ps1
```

首次运行会把 `BAAI/bge-small-zh-v1.5` 缓存到项目 `var\models\fastembed`，migration 后对已审核 chunk 幂等建索引，并自动执行语义 smoke test。向量模式仍先跑关键词并从 PostgreSQL 回填正文；模型、索引或向量查询失败时记录原因并回退关键词。默认 `start_demo.ps1` 继续关闭向量，不下载模型。

## 6. 验收与排错

查看服务：

```powershell
docker compose ps
docker compose logs backend
docker compose logs frontend
```

四项都应为 `healthy`。常见问题：

- Docker 未启动：先打开 Docker Desktop，再重跑脚本。
- 端口冲突：停止占用 `5432/6379/8000/3000` 的旧进程或旧 Compose 项目。
- migration/seed 失败：查看 backend 日志；不要跳过初始化后把空页面当成功。
- 重复运行：seed 和固定用例使用幂等设计；Demo Runner 每次生成新的 key 前缀。
- PowerShell 禁止脚本：只对当前窗口执行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`。

停止容器并保留数据：

```powershell
.\scripts\stop_demo.ps1
```

不要把 `docker compose down -v` 当作日常停止命令；`-v` 会删除本地 PostgreSQL/Redis volume。

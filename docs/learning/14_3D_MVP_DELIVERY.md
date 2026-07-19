# 14. 3D：从“代码能跑”到“项目可交付”

这一章把你当作第一次交付完整项目的开发者。目标不是再添加业务功能，而是理解为什么 migration、seed、容器健康、固定演示、报告和限制说明共同构成一个可复现 MVP。

## 1. 为什么最后还需要 3D

开发机上 `uvicorn` 能启动，只能证明当前终端和当前数据库能运行。面试官或新协作者拿到仓库后还会遇到：

- 数据库没有表；
- 表存在但没有 demo 数据；
- backend 已启动但 frontend 仍连不上；
- 演示者每次输入不同，结果不可比较；
- deterministic 输出被误说成真实大模型；
- 本地草稿被误说成已提交医院。

3D 的任务是把这些隐含前提变成代码、healthcheck、脚本和文档。

## 2. 先画完整启动链

```text
start_demo.ps1
  -> docker compose up --build --wait
      -> PostgreSQL healthy
      -> Redis healthy
      -> backend/docker-entrypoint.sh
          -> Alembic migration
          -> idempotent seed
          -> Uvicorn
      -> backend healthcheck
      -> Next.js production server
      -> frontend healthcheck
  -> run_demo.ps1
      -> four public API scenarios
      -> safe local report
```

依赖顺序非常重要。后端必须等 PostgreSQL 可连接；前端必须等后端健康；固定演示必须等整个栈健康。`depends_on` 配合 healthcheck 表达的就是这个启动有向图。

## 3. 逐个读交付文件

### 3.1 `docker-compose.yml`

先找四个 service：`postgres`、`redis`、`backend`、`frontend`。每个 service 固定问：

1. 镜像从哪里来，是 pull 还是 build？
2. 环境变量从哪里来？
3. 容器端口映射到主机哪个端口？
4. 依赖哪个健康服务？
5. 它自己怎么证明 healthy？

Compose 中 `${NAME:-default}` 表示：本机环境或 `.env` 有 `NAME` 就使用它，否则用 `default`。因此默认演示不需要秘密，也不会把 Key 写死在 YAML。

### 3.2 `backend/Dockerfile`

重要代码按顺序读：

```dockerfile
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/alembic ./backend/alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
ENTRYPOINT ["docker-entrypoint.sh"]
```

- `COPY` 把构建上下文中的文件放进 Linux 镜像。
- Alembic 配置中的 `script_location=backend/alembic`，所以镜像也必须保留这个相对路径。
- `ENTRYPOINT` 是容器每次启动时执行的固定入口，不是构建时执行。

### 3.3 `backend/docker-entrypoint.sh`

```sh
set -eu
python -m alembic upgrade head
python -m scripts.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- `set -e`：任一命令失败就停止，不能 migration 失败后继续伪装健康。
- `set -u`：使用未定义 shell 变量时报错。
- `alembic upgrade head`：把数据库结构升级到最新 revision。
- `python -m scripts.seed`：按 Python 模块启动，让 `/app` 在导入路径中；seed 本身可重复执行。
- `exec uvicorn`：让 Uvicorn 成为容器主进程，Docker 能正确发送停止信号。

Migration 管“表长什么样”，seed 管“演示时表里有什么”。二者不能互相代替。

### 3.4 `frontend/Dockerfile`

`npm ci` 严格按 `package-lock.json` 安装，适合可重复构建；`npm run build` 生成 Next.js production bundle；容器最终运行 `next start`，而不是带热更新的开发服务器。

这不代表系统已生产就绪。当前仍没有生产认证、秘密管理、反向代理、HTTPS、监控和高可用，而且 Next 14 的已知依赖风险仍需在真实部署前单独升级和回归。

## 4. 我们的 RAG 到底有没有 Embedding

3D 默认模式没有，4A 已新增可选真实 FastEmbed/pgvector；当前仍默认关闭。请把 RAG 拆成两个概念，当前实现细节继续阅读 [15 4A 轻量向量 RAG](15_4A_LIGHTWEIGHT_VECTOR_RAG.md)：

```text
RAG = Retrieval + 把检索证据提供给生成流程
Vector Retrieval = Retrieval 的一种实现方式
```

当前 `KeywordRetriever` 从 PostgreSQL 读取 `knowledge_documents` / `knowledge_chunks`，按关键词和 category 排序，再返回：

```text
document_id + chunk_id + version + source + content
```

这已经解决了“回答中的规则从哪里来”和“来源能不能回查”，所以是一个确定性的 RAG 基线。它的缺点是同义词和语义召回弱。

3D 当时只定义了 `VectorSearchBackend` 协议；4A 已按以下边界实现：

1. 用 Embedding 模型把 query 转成向量；
2. 从向量库返回 document/chunk ID 和相似度；
3. 仍回 PostgreSQL 按 ID 加载权威正文；
4. 拒绝不存在或错配的指针；
5. 向量服务失败时回退关键词结果。

所以在 3D 快照里，`RAG_VECTOR_ENABLED=true` 还不等于拥有 Embedding；4A 之后应使用 `.\scripts\start_vector_rag.ps1` 完成 migration、模型缓存、索引和 smoke，而不是只改一个开关后凭配置猜测成功。

## 5. 我们的问答到底有没有调用大模型

默认没有。`.env.example` 中：

```text
MODEL_PROVIDER=deterministic
MODEL_NAME=deterministic-local
```

`DeterministicModelProvider` 用固定规则产生符合 Pydantic 契约的 Planner/FinalAnswer 输出。优点是离线、免费、稳定，适合测试控制流和安全门；缺点是不能代表自然语言理解或真实模型效果。

项目同时实现了 OpenAI-compatible HTTP adapter。真实模式的数据流是：

```text
structured request
  -> /chat/completions provider
  -> text response
  -> JSON parse
  -> Pydantic schema validation
  -> output safety check
  -> accepted structured output
  -> or deterministic fallback with attempt trace
```

API Key 不应由开发者发在聊天中。你应在自己的未提交 `.env` 写 `MODEL_API_BASE/MODEL_API_KEY/MODEL_NAME`。当前尚未用真实 Key 跑固定质量报告，所以简历只能说“实现可替换 Model Gateway 和安全 fallback”，不能说“模型准确率达到某数值”。

## 6. 固定 Demo Runner 怎么工作

入口是 [demo_runner.py](../../backend/app/agent/demo_runner.py)，场景定义在 [demo_scenarios.json](../../backend/app/agent/demo_scenarios.json)。

每条 case 包含：输入、成员关系、期望 intent、必需工具、安全 flag、禁用短语、期望来源、确认要求和最终状态。Runner 的流程是：

1. 调 `/api/family-members`，由 relationship 找真实 seed member ID。
2. 调 `POST /api/agent-runs`，首轮永远不携带确认。
3. 正常关键动作拿到 `needs_confirmation` 后调用 `/continue`。
4. 高风险结果保持 `blocked`，绝不续跑。
5. 用 `RuntimeTraceAdapter` 校验和脱敏冻结 artifacts。
6. 用 `DeterministicEvaluator` 只读计算结果。
7. 检查 `external_action_status` 必须是 `not_submitted`。
8. 只输出不含 member/run ID 和答案正文的报告。

这不是另一套业务工作流。它是站在系统外面的“验收客户端”，和 Postman 的位置相似，只是断言更完整且能重复运行。

## 7. 亲手运行并观察

```powershell
Set-Location E:\project_code\hospital
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_demo.ps1
docker compose ps
Get-Content var\demo\mvp-demo.md
```

再打开：

- `http://localhost:3000/agent`
- `http://localhost:8000/docs`

手工演示时按“父亲续方 -> 母亲复诊 -> 母亲提醒 -> 父亲高风险”切换成员。重点不是只看答案，而是同时解释状态、来源、Safety flag、确认门、Trace 和 EvaluationResult。

## 8. 你应该怎样 Review 3D

1. 删除本地 `.env` 后，`docker compose up --build` 是否仍能按默认值启动？
2. 全新 volume 是否真的执行 migration 和 seed？
3. migration 或 seed 失败时 backend 是否退出，而不是变成 healthy？
4. 重跑 seed 和演示是否不会创建失控重复数据？
5. 三个正常场景是否必须先待确认再创建本地草稿？
6. 高风险场景是否没有 continuation？
7. 所有 external action 是否仍为 `not_submitted`？
8. 报告是否排除 member/run ID、答案正文、prompt 和 Key？
9. README 是否明确 deterministic 与真实 LLM、关键词与向量检索的差别？
10. 已知依赖风险和非生产边界是否如实保留？

## 9. 面试表达

可以这样讲：

> 我没有把“本机能启动”当成交付完成，而是把 migration、幂等 seed、服务 healthcheck 和固定四场景编入 Docker 启动链。演示 Runner 只走公开 API，复用 Runtime Trace 与 deterministic Evaluator，并输出脱敏报告。默认关键词 RAG 和 deterministic model 保证无 Key 可复现，真实 LLM 通过 OpenAI-compatible Gateway 可选接入并带 schema、安全检查和 fallback。

仅依据 3D 报告不能说：已生产上线、已接真实医院、已做临床评测、使用了真实 Embedding、真实 LLM 达到 100% safety recall，或浏览器端 p95 等于固定 Trace latency。4A 后可以说“本地实现并验证 FastEmbed/pgvector”，但仍不能扩张成生产或医疗效果结论。

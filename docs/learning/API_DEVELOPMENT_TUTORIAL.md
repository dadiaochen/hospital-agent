# 06. 从零实战：自己实现知识库搜索 API

这是一份“边学边做”的练习，不是只供浏览的接口说明。你将亲手补全阶段 2E-1 的最后一个读取接口：

```text
GET /api/knowledge/search
```

请严格按顺序完成，每做完一层就检查一次。这样出错时，你能知道问题来自 Schema、Service、Router 还是运行环境。

> 本练习只实现确定性的数据库关键词搜索：不调用 LLM，不执行 Agent，不使用向量数据库，也不写入业务数据。

## 0. 你现在已经做到哪里

根据当前工作区，你已经亲手完成了：

- `backend/app/schemas/knowledge.py`：请求和响应 Schema。
- `backend/app/services/knowledge_read_service.py`：SQLAlchemy 查询与关键词匹配。
- `backend/app/api/routes/knowledge.py`：FastAPI 路由和响应映射。
- `backend/app/api/router.py`：把知识路由注册进 `/api` 主路由。

你还没有完成的核心验收项是：

- `backend/tests/test_knowledge_api.py` 集成测试。
- 启动 Docker PostgreSQL/Redis，并使用 PostgreSQL seed 数据真实调用接口。
- Swagger 和 Postman 的成功、空结果、分类过滤、错误参数验证。
- 完成后更新 `docs/API_SPEC.md`，再 review 是否可以结束 2E-1。

因此，从这里开始不要重新覆盖前面四个 Python 文件。先对照本文理解你已经写了什么；发现不一致时只改具体一行，并说明原因。学习目标不是“再次粘贴答案”，而是能够沿着请求链解释每一层。

## 1. 完成后你应该会什么

1. 解释 HTTP 请求如何进入 FastAPI Router。
2. 区分 Pydantic Schema 和 SQLAlchemy ORM。
3. 把 SQL 查询放进 Service，而不是 Router。
4. 使用 FastAPI 依赖注入获得数据库 Session 和 demo user。
5. 理解为什么搜索无结果返回 `200 + []`，而不是 `404`。
6. 使用 `source_id` 为 RAG、Trace 和最终答案保留来源指针。
7. 使用 pytest、Swagger 和 Postman 验证成功及失败路径。

## 2. 新手名词表

| 名词           | 简单理解                        | 本练习对应位置                                          |
| ------------ | --------------------------- | ------------------------------------------------ |
| API          | 调用方和后端约定的入口。                | `GET /api/knowledge/search`                      |
| Router       | 接收 HTTP 参数、调用 Service、组装响应。 | `backend/app/api/routes/knowledge.py`            |
| Schema / DTO | 规定输入输出字段和类型。                | `backend/app/schemas/knowledge.py`               |
| Service      | 实现查询和匹配，不关心 HTTP。           | `backend/app/services/knowledge_read_service.py` |
| ORM Model    | Python 类与数据库表的映射。           | `backend/app/models/knowledge.py`                |
| Dependency   | FastAPI 调路由前自动准备的对象。        | `DbSession`、`DemoUser`                           |
| Fixture      | 测试前准备数据、测试后清理环境。            | `backend/tests/test_knowledge_api.py`            |

完整调用链：

```text
Postman / Browser
       | GET /api/knowledge/search?q=人工确认
       v
Uvicorn (监听端口并把 HTTP 请求交给 FastAPI)
       v
FastAPI Router (匹配方法和路径)
       | Query + Pydantic 校验 query 参数
       | Depends 注入 Session 和 demo user
       v
KnowledgeReadService
       | join 文档与 chunk，执行确定性关键词匹配
       v
SQLAlchemy Engine / Session
       v
PostgreSQL 容器 family-health-postgres（真实本地联调）
       |
       v
Pydantic Response -> JSON -> 调用方
```

本教程的真实运行环境使用 Docker PostgreSQL：

```text
postgresql+psycopg://hospital:hospital@localhost:5432/family_health
```

pytest 单独把 `DATABASE_URL` 覆盖为 `sqlite:///:memory:`。这正是使用 SQLAlchemy 的价值之一：上层业务代码依赖 Session 和 ORM，不直接依赖某个数据库连接库；但 PostgreSQL 与 SQLite 的方言、类型和并发行为仍有差异，所以真实联调和自动化测试两条路径都要跑。

## 2.1 为什么选择这套技术

一个 API 不只是一个函数。它至少要解决“接收网络请求、校验数据、执行业务、访问数据库、返回 JSON、处理错误、生成文档、自动测试”八类问题。本项目没有让一个框架包办所有事情，而是让每个组件负责自己擅长的部分。

| 技术         | 它是什么                     | 在本项目做什么                                                        | 为什么选择它                                         |
| ---------- | ------------------------ | -------------------------------------------------------------- | ---------------------------------------------- |
| Python     | 通用编程语言。                  | 编写 API、数据模型、Agent Harness 和测试。                                 | AI 生态成熟，类型注解可同时服务 FastAPI、Pydantic 和编辑器。       |
| Uvicorn    | ASGI Web Server。         | 监听本地 `8000` 端口，把 HTTP 请求交给 FastAPI。                            | FastAPI 只描述应用，仍需要一个服务器真正接收网络连接。                |
| FastAPI    | Python API 框架。           | 路由匹配、依赖注入、异常处理、OpenAPI/Swagger。                                | 直接利用类型注解生成校验和接口文档，适合契约明确的 Agent 后端。            |
| Pydantic   | 运行时数据校验库。                | 定义请求 DTO、响应 DTO，把不合法输入挡在业务层之前。                                 | Python 类型注解本身不会在运行时自动拒绝错误输入，Pydantic 会。        |
| SQLAlchemy | ORM 和 SQL 工具包。           | 用 Python 类表示表，用 `select` 构造查询，用 Session 管理数据库交互。               | 隔离 SQLite/PostgreSQL 差异，避免 Router 到处拼 SQL 字符串。 |
| Alembic    | 数据库迁移工具。                 | 按版本创建和升级表结构。                                                   | 团队需要知道数据库结构怎样从版本 A 演进到版本 B，不能只靠手工建表。           |
| PostgreSQL | 独立关系数据库。                 | Docker 中保存本地 demo 数据，承载 migration、seed、Swagger/Postman 和前后端联调。 | 更接近真实后端，能够学习服务生命周期、连接、类型、事务和容器数据持久化。           |
| SQLite     | 嵌入式文件/内存数据库。             | pytest 中创建隔离测试库；Docker 故障时可临时排查。                               | 启动快、测试隔离简单，但不作为完整项目联调数据库。                      |
| pytest     | Python 测试框架。             | 组织 fixture、测试用例和断言。                                            | 语法直接，适合从成功路径扩展到权限、验证和安全失败路径。                   |
| TestClient | FastAPI/Starlette 测试客户端。 | 不启动真实端口也能发模拟 HTTP 请求。                                          | 测试快、可重复，并能覆盖 Router、依赖、Service 和响应序列化。         |
| Swagger UI | OpenAPI 的可视化页面。          | 在 `/docs` 查看契约并临时手工调用。                                         | 适合开发者快速确认接口是否注册。                               |
| Postman    | 独立 HTTP 调试工具。            | 保存环境、请求和验收脚本，模拟真实外部客户端。                                        | 比 Swagger 更适合整理一组可反复执行的手工验收请求。                 |

### 为什么不是其他常见方案

| 替代方案                           | 本阶段没有选择的原因                                           |
| ------------------------------ | ---------------------------------------------------- |
| Flask                          | 可以实现，但请求校验、依赖注入和 OpenAPI 需要更多手工组合；本项目已经采用 FastAPI。   |
| Django / Django REST Framework | 功能完整，但自带 ORM、管理后台和更重的项目结构；当前已有 SQLAlchemy 分层，切换收益不足。 |
| 直接使用 `sqlite3`                 | 会让业务层绑定 SQLite SQL 和连接细节，无法复用当前 PostgreSQL 联调链路。     |
| 把 ORM 对象直接返回                   | 数据库字段会变成外部契约，容易泄露内部字段，也无法稳定控制响应结构。                   |
| Elasticsearch / 向量数据库          | 当前只有少量 seed 安全知识，先建立可测试的确定性 baseline 更重要。            |
| LLM 搜索                         | 相同输入可能产生不同输出，无法替代来源明确、可重复的检索基线。                      |

技术选型不是“哪个技术最先进”，而是“当前问题需要什么能力、团队已经有什么基础、引入成本是否值得”。阶段 2E-1 的目标是学习完整 API 链路，不是提前做生产级搜索平台。

## 2.2 为什么真实联调用 PostgreSQL，pytest 仍用 SQLite

两者不是互相替代，而是负责不同层级的验证。

| 比较项      | PostgreSQL Docker 联调                   | SQLite pytest 测试          |
| -------- | -------------------------------------- | ------------------------- |
| 生命周期     | Docker 服务启动后持续保存数据。                    | 每次测试重建，结束即清理。             |
| 主要目的     | 验证真实配置、migration、seed、API、连接和 Compose。 | 快速验证函数与接口契约，保证用例互不污染。     |
| 并发与事务    | 更接近真实服务。                               | 行为更简单，不能替代 PostgreSQL 验证。 |
| 类型与 JSON | 约束和查询能力更严格、更完整。                        | 类型规则较宽松。                  |
| 使用工具     | Swagger、Postman、浏览器、前端。                | pytest、TestClient。        |

SQLAlchemy 能减少重复代码，但不能保证两个数据库行为百分之百相同。下面这些必须由 PostgreSQL 路线验证：

1. 并发事务和锁行为。
2. 大小写匹配、排序和特定 SQL 函数。
3. JSON 字段查询、索引和性能。
4. 数据库连接池、超时和服务故障。

Docker PostgreSQL 本地跑通也不等于生产验证完成，因为本阶段没有做负载、容灾、备份、监控和安全加固；它代表的是“本地 PostgreSQL 集成通过”。

## 2.3 完成一条 API，你必须看懂哪些代码

不要从目录第一行开始漫无目的地读。沿着一次请求依次阅读，理解成本最低。

| 阅读顺序 | 文件                                               | 你要回答的问题                                                                |
| ---- | ------------------------------------------------ | ---------------------------------------------------------------------- |
| 1    | `backend/app/api/routes/knowledge.py`            | HTTP 方法和路径是什么？参数从哪里来？调用哪个 Service？返回哪个 DTO？                            |
| 2    | `backend/app/schemas/knowledge.py`               | 输入有哪些字段？什么输入会失败？输出保证有哪些字段？                                             |
| 3    | `backend/app/services/knowledge_read_service.py` | 业务逻辑怎样查询、过滤、匹配和排序？返回类型是什么？                                             |
| 4    | `backend/app/models/knowledge.py`                | Python 属性对应哪张表、哪一列？Document 和 Chunk 如何关联？                              |
| 5    | `backend/app/api/dependencies.py`                | Session 和 demo user 是谁创建的？失败时发生什么？                                     |
| 6    | `backend/app/core/database.py`                   | Engine、SessionLocal、`get_db` 的生命周期是什么？代码怎样区分 PostgreSQL 与 SQLite 测试配置？ |
| 7    | `backend/app/api/router.py`                      | 子路由是否注册？它贡献哪一段 URL？                                                    |
| 8    | `backend/app/main.py`                            | `/api` 从哪里加上？异常如何变成 JSON？Swagger 如何得到契约？                               |
| 9    | `backend/app/core/config.py`                     | `.env` 中的 `DATABASE_URL`、端口和 demo user 如何进入代码？                         |
| 10   | `backend/alembic/versions/`                      | 表结构由哪次 migration 创建？                                                   |
| 11   | `scripts/seed.py`                                | Postman 能查到的知识文档从哪里写入？                                                 |
| 12   | `backend/tests/test_knowledge_api.py`            | 正常和异常行为怎样被固定成可重复验收？                                                    |

读每个函数时，固定问五个问题：

1. 输入是什么类型，来自哪里？
2. 输出是什么类型，交给谁？
3. 它有没有副作用，例如访问数据库或修改状态？
4. 它依赖什么对象，这些对象由谁创建？
5. 什么情况下失败，失败会在哪里被转换成 HTTP 响应？

如果五个问题都答不出来，不要继续读更深的框架源码。先在当前项目里跟踪变量和类型。

## 2.4 应用启动时发生了什么

启动命令：

```powershell
python -m uvicorn app.main:app --app-dir backend --port 8000
```

它可以拆成下面几步：

1. Python 运行 `uvicorn` 模块。
2. `--app-dir backend` 让 `backend` 成为 Python 导入根目录，因此可以导入 `app`。
3. `app.main:app` 表示导入 `backend/app/main.py`，读取其中名为 `app` 的对象。
4. `main.py` 执行 `app = create_app()`，创建 FastAPI 应用。
5. `main.py` 导入 `app.api.router`，Router 文件继续导入各个子 Router。
6. Python 导入 `knowledge.py` 路由时，`@router.get(...)` 装饰器立刻把函数登记到 Router。
7. `app.include_router(api_router, prefix="/api")` 把所有子路由挂到 `/api` 下。
8. Uvicorn 开始监听端口，等待真实 HTTP 请求。

这解释了为什么“代码文件存在”不代表“接口已经上线”：如果没有 import 和 `include_router`，路由装饰器注册的信息不会进入主应用，访问时就是 404。

## 2.5 一次知识搜索请求如何执行

以当前本机请求为例：

```http
GET http://localhost:8000/api/knowledge/search?q=人工确认
```

完整执行顺序：

1. Uvicorn 收到 TCP/HTTP 请求并交给 FastAPI。
2. FastAPI 用 `GET + /api/knowledge/search` 找到 `search_knowledge`。
3. `Query()` 根据 URL query string 构造 `KnowledgeSearchQuery`，并把校验失败包装成 HTTP 请求校验错误。
4. Pydantic 先做字段类型和长度校验，再执行 `field_validator` 标准化空白。
5. FastAPI 执行 `DbSession` 依赖，调用 `get_db()` 创建 SQLAlchemy Session。
6. FastAPI 执行 `DemoUser` 依赖，用同一个 Session 查询配置手机号对应的用户。
7. 依赖全部成功后，FastAPI 才真正调用 `search_knowledge(...)`。
8. Router 创建 `KnowledgeReadService(db)`，把已经校验的 `q/category` 传进去。
9. Service 构造 SQLAlchemy `Select`，join `knowledge_chunks` 与 `knowledge_documents`。
10. SQLAlchemy 根据 `postgresql+psycopg://...` URL 选择 PostgreSQL 方言和 psycopg 驱动，把查询发送到容器。
11. PostgreSQL 返回行，SQLAlchemy 将每行转换成 `(KnowledgeChunk, KnowledgeDocument)` ORM 对象。
12. Service 把可检索字段组成 `haystack`，执行确定性字符串匹配。
13. Router 把命中的 ORM 对象转换为 `KnowledgeSearchItemResponse`。
14. FastAPI 再用 `KnowledgeSearchResponse` 检查返回值并序列化成 JSON。
15. `get_db()` 的 `finally` 执行，Session 被关闭。
16. Uvicorn 把状态码、响应头和 JSON body 发回 Postman。

### 三条失败路径也必须会讲

| 场景                       | 在哪一层停止                     | 最终结果                                             |
| ------------------------ | -------------------------- | ------------------------------------------------ |
| 缺少 `q` 或 `q` 是空白         | Pydantic / FastAPI 参数解析    | `RequestValidationError` 被 `main.py` 转为统一 `422`。 |
| `.env` 配置的 demo user 不存在 | `get_demo_user` dependency | 抛 `ResourceNotFoundError`，统一转为 `404`。            |
| 查询合法但没有知识命中              | Service 正常返回空 list         | `200` 和 `{ "items": [] }`，因为这不是系统故障。             |

## 2.5.1 初学者逐层导读：客户端、API 层和四个核心文件

这一节专门回答几个最容易混淆的问题：客户端在哪里？API 层是不是只负责“接受请求再调用 Service”？依赖注入到底是谁在注入？Schema、Service、Model 的理解分别应该修正到什么程度？

### 客户端是什么，在哪里体现

客户端（client）就是发起请求的一方。它可以是：

| 客户端      | 在本项目中的例子                        | 它做什么                        |
| -------- | ------------------------------- | --------------------------- |
| 浏览器      | 访问 `http://localhost:8000/docs` | 发送 HTTP 请求并显示响应。            |
| Postman  | `GET /api/knowledge/search`     | 模拟真实外部调用方，发送请求、查看状态码和 JSON。 |
| 前端页面     | `frontend/` 后续调用 API 的代码        | 把用户操作转换成 HTTP 请求。           |
| 自动化测试客户端 | `TestClient(app)`               | 在 pytest 中模拟请求，不一定真的监听端口。   |

当前的 `knowledge.py` 是服务端代码，所以里面没有一个叫 `client` 的变量。客户端的身份体现在“谁调用了这个 URL”，而不是体现在路由函数内部。测试中才会直接看到这个名字：

```python
with TestClient(app) as client:
    response = client.get(
        "/api/knowledge/search",
        params={"q": "人工确认"},
    )
```

这里 `client.get(...)` 的含义是“测试客户端发送一个 HTTP GET 请求”。而路由里的 `@router.get(...)` 的含义是“FastAPI 注册一个能够处理 GET 请求的函数”。两者方向相反：

```text
TestClient / Postman / Browser  --发送请求-->  FastAPI Router
FastAPI Router                  --返回响应-->  TestClient / Postman / Browser
```

### API 层是不是“接收请求、调用 Service、返回结果”

你的理解基本正确，但还要补充四件事。API 层通常负责：

1. 声明 HTTP 方法和路径。
2. 接收并校验 HTTP 输入。
3. 请求 Service，并把依赖对象交给它。
4. 把 Service 结果映射成对外 DTO，并交给框架序列化。

API 层不应该负责复杂的搜索算法、医疗判断或大量 SQL。当前这条接口的职责可以写成：

```text
HTTP 请求
→ FastAPI 匹配路由
→ Schema 校验输入
→ Dependency 准备 db 和 demo user
→ API 调用 KnowledgeReadService
→ API 把 ORM 结果映射为 Response DTO
→ FastAPI 返回 JSON
```

### 依赖注入是什么

“依赖”就是函数执行前必须准备好的对象。例如搜索需要：

```text
db Session       用来访问数据库
demo user        用来确认演示用户存在且有效
```

如果不使用依赖注入，路由可能被迫自己创建数据库连接：

```python
def search_knowledge(query):
    db = SessionLocal()
    try:
        ...
    finally:
        db.close()
```

这样每个路由都要重复创建和关闭 Session，也不方便测试替换。

当前代码只声明需要什么：

```python
def search_knowledge(
    query: Annotated[KnowledgeSearchQuery, Query()],
    db: DbSession,
    _demo_user: DemoUser,
) -> KnowledgeSearchResponse:
```

`DbSession` 和 `DemoUser` 在 [dependencies.py](../../backend/app/api/dependencies.py) 中定义：

```python
DbSession = Annotated[Session, Depends(get_db)]
DemoUser = Annotated[User, Depends(get_demo_user)]
```

FastAPI 看到 `Depends(get_db)` 后会自动执行 `get_db()`；看到 `Depends(get_demo_user)` 后会自动执行 `get_demo_user()`。后者又依赖 `get_db()`，所以 FastAPI 会先构造数据库 Session，再把它交给 `get_demo_user`。

```text
FastAPI
  → get_db() 创建 Session
  → get_demo_user(db) 查询演示用户
  → search_knowledge(query, db, demo_user)
  → 请求结束后 get_db() 关闭 Session
```

这叫依赖注入（Dependency Injection）：函数声明“我需要什么”，框架负责“创建并传入什么”。它的好处是生命周期集中管理、代码少重复、测试时可以用 `app.dependency_overrides` 换成测试 Session。

### Schema、Service、Model 的理解需要怎样修正

你的方向是对的，但可以更精确：

| 概念           | 你的初步理解    | 更准确的理解                                                       |
| ------------ | --------- | ------------------------------------------------------------ |
| Schema / DTO | 定义要用到的变量  | 定义 API 输入输出的形状、类型、校验规则和对外契约，不只是声明变量。                         |
| Service      | 具体做事      | 实现一个业务用例的规则和流程；当前 `KnowledgeReadService` 负责知识查询和匹配，不负责 HTTP。 |
| Model        | 数据库里有什么字段 | 用 ORM 类映射数据库表、字段、主键、外键、关系和约束；它不是 API 返回契约。                   |

举例：

```text
KnowledgeSearchQuery       = 客户端可以怎样提问
KnowledgeReadService       = “怎样搜索知识”这个业务怎么执行
KnowledgeDocument/Chunk    = 数据库怎样保存知识
KnowledgeSearchResponse    = 客户端最终能看到什么
```

Schema 不等于数据库字段。一个数据库表可能有内部审计字段，但 API Schema 可以选择不暴露；反过来，`source_id` 是 Router 为对外追踪生成的字段，也不一定是数据库中的单独列。

### 四个文件逐行阅读表

阅读时不要只看“这行是什么语法”，还要问“它来自哪个层、它被谁调用、它把数据交给谁”。

#### 1. Router：`backend/app/api/routes/knowledge.py`

| 代码位置      | 看到的代码                                                  | 应该理解成什么                                             |
| --------- | ------------------------------------------------------ | --------------------------------------------------- |
| 第 1 行     | `from typing import Annotated`                         | Python 标准库类型工具，用于给类型附加 FastAPI 元数据。                 |
| 第 3 行     | `from fastapi import APIRouter, Query`                 | 这是 FastAPI 的直接证据；普通 Python 不提供 `APIRouter`。         |
| 第 5 行     | `from app.api.dependencies import DbSession, DemoUser` | 导入项目自己的依赖别名，不是用户提交的参数。                              |
| 第 7-12 行  | 导入 Schema 和 Service                                    | API 层依赖契约层和业务层。                                     |
| 第 16 行    | `APIRouter(prefix="/knowledge")`                       | 创建 FastAPI 子路由，并贡献 `/knowledge` 这一段路径。              |
| 第 19 行    | `@router.get(...)`                                     | 把下面的 Python 函数注册为 GET 路由。装饰器在模块导入时执行。               |
| 第 20 行    | `"/search"`                                            | 贡献 `/search` 这一段路径，完整路径还要加 `/api`。                  |
| 第 21 行    | `response_model=KnowledgeSearchResponse`               | 告诉 FastAPI 成功响应应该符合哪个 Schema，并用于 OpenAPI 文档和响应校验。   |
| 第 25 行    | `def search_knowledge`                                 | 真正收到匹配请求后，FastAPI 会调用这个函数。                          |
| 第 27 行    | `query: Annotated[..., Query()]`                       | 从 URL query string 读取参数，并构造 `KnowledgeSearchQuery`。 |
| 第 29 行    | `db: DbSession`                                        | 请求执行前由 FastAPI 注入一个 SQLAlchemy Session。             |
| 第 30 行    | `_demo_user: DemoUser`                                 | 变量名以下划线开头表示函数体不读取它，但依赖校验仍会执行。                       |
| 第 31 行    | `-> KnowledgeSearchResponse`                           | 返回类型注解，不是输入；表示函数应返回这个响应 DTO。                        |
| 第 33-36 行 | `KnowledgeReadService(db).search(...)`                 | 创建 Service 实例并调用业务方法；`query.q` 是属性访问，不是方法调用。        |
| 第 39 行    | `KnowledgeSearchResponse(...)`                         | 创建最外层响应 DTO。                                        |
| 第 40-53 行 | `items=[... for chunk, document in rows]`              | 遍历 Service 返回的 ORM 对象，并为每条结果创建一个响应 item。            |
| 第 42 行    | `source_id=f"knowledge:{document.id}:{chunk.id}"`      | Router 组合稳定来源指针，便于后续 RAG、Trace 和审计追溯。               |
| 第 43-51 行 | `document.xxx` / `chunk.xxx`                           | 从 ORM 对象读取数据库字段，显式复制到对外 DTO。                        |

第 40-53 行的列表推导式可以先展开成普通 Python 循环：

```python
items = []
for chunk, document in rows:
    item = KnowledgeSearchItemResponse(
        source_id=f"knowledge:{document.id}:{chunk.id}",
        document_id=document.id,
        chunk_id=chunk.id,
        title=document.title,
        category=document.category,
        source=document.source,
        safety_level=document.safety_level,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        keywords=list(chunk.keywords or []),
    )
    items.append(item)

return KnowledgeSearchResponse(items=items)
```

先看懂这个展开版本，再回头看列表推导式。列表推导式只是缩写，不是新的业务逻辑。

#### 2. Schema：`backend/app/schemas/knowledge.py`

| 代码位置      | 看到的代码                                   | 应该理解成什么                      |
| --------- | --------------------------------------- | ---------------------------- |
| 第 6 行     | `class KnowledgeSearchQuery(ApiSchema)` | 定义搜索请求 DTO，规定客户端提交的数据形状。     |
| 第 8 行     | `q: str = Field(...)`                   | `q` 必须是字符串，并且长度限制在 1 到 200。  |
| 第 10 行    | `category: str \| None`                 | category 可以不传；不传时是 `None`。   |
| 第 12-20 行 | `field_validator("q")`                  | 输入进入 Service 前先标准化空白并拒绝纯空格。  |
| 第 33 行    | `KnowledgeSearchItemResponse`           | 定义单个搜索结果的输出字段。               |
| 第 49 行    | `KnowledgeSearchResponse`               | 定义整体响应，`items` 必须是结果 DTO 列表。 |

所以 Schema 不只是“变量清单”，它还承担边界保护：非法输入在业务逻辑运行前就被拦住，返回 JSON 的形状也不会任意变化。

#### 3. Service：`backend/app/services/knowledge_read_service.py`

| 代码位置      | 看到的代码                                 | 应该理解成什么                                      |
| --------- | ------------------------------------- | -------------------------------------------- |
| 第 7 行     | `class KnowledgeReadService`          | 定义“读取知识”这个业务服务。                              |
| 第 10-12 行 | `__init__(self, db)`                  | Service 接收外部传入的 Session，不自己创建数据库连接。          |
| 第 14-19 行 | `search(...) -> list[...]`            | 方法输入是普通业务参数，输出是 ORM 对象列表；它不返回 HTTP Response。 |
| 第 26-34 行 | `select(...).join(...).order_by(...)` | 用 SQLAlchemy 构造查询、关联两张表并固定排序。                |
| 第 36-37 行 | `where(...)`                          | category 有值时才增加分类过滤。                         |
| 第 39 行    | `self.db.execute(statement).all()`    | 这一行通过 Session 真正执行数据库读取。                     |
| 第 42-55 行 | `for chunk, document in rows`         | 遍历查询结果，构造搜索文本并执行确定性匹配。                       |
| 第 57 行    | `return matches`                      | 把业务结果交给 Router，不关心状态码和 JSON。                 |

Service 的“具体做事”包括查询、过滤、排序、匹配；但“返回 200 还是 422”属于 API/异常处理边界，不属于这个 Service。

#### 4. Model：`backend/app/models/knowledge.py`

| 代码位置      | 看到的代码                          | 应该理解成什么                                       |
| --------- | ------------------------------ | --------------------------------------------- |
| 第 13-20 行 | `KnowledgeDocument` 及其字段       | Python ORM 类映射 `knowledge_documents` 表和文档级字段。 |
| 第 22 行    | `chunks = relationship(...)`   | 一个 document 可以关联多个 chunk；这是对象关系，不是额外数据库列。     |
| 第 25-31 行 | `KnowledgeChunk` 及其字段          | Python ORM 类映射 `knowledge_chunks` 表和片段级字段。    |
| 第 28 行    | `ForeignKey(...)`              | `document_id` 指向文档表的 `id`，形成数据库外键关系。          |
| 第 33 行    | `document = relationship(...)` | 可以从 chunk 对象导航到所属 document。                   |

Model 描述“数据怎样存”，Schema 描述“API 怎样收发”。不要把 ORM 对象直接当作公开 API 契约返回。

### 把四个文件串成一条数据流

```text
客户端提交 q/category
    ↓
KnowledgeSearchQuery 校验并生成 query 对象
    ↓
FastAPI 注入 db Session 和 demo user
    ↓
Router 取 query.q/query.category
    ↓
KnowledgeReadService.search()
    ↓
SQLAlchemy 使用 KnowledgeDocument/KnowledgeChunk 构造查询
    ↓
PostgreSQL 返回 ORM 对象 rows
    ↓
Router 显式映射为 KnowledgeSearchItemResponse
    ↓
KnowledgeSearchResponse
    ↓
FastAPI 序列化成 JSON 返回客户端
```

读代码时可以给每行贴一个标签：

```text
[Python]      赋值、函数、类、属性访问、方法调用、列表推导式
[FastAPI]     APIRouter、@router.get、Query、Depends、response_model
[Pydantic]    KnowledgeSearchQuery、KnowledgeSearchResponse、Field
[项目代码]    KnowledgeReadService、KnowledgeDocument、KnowledgeChunk
[SQLAlchemy]  Session、select、join、mapped_column、relationship
[数据库]      knowledge_documents、knowledge_chunks、外键和真实数据
```

这六类标签回答的是不同问题：Python 说明“语法怎么运行”，第三方技术说明“能力由谁提供”，项目代码说明“本项目的业务怎么组合”，数据库说明“真实数据在哪里保存”。

### 学习检查：请不要背答案

请打开四个文件后，用自己的话完成下面的表格：

| 问题           | 你的答案应包含什么                                          |
| ------------ | -------------------------------------------------- |
| 客户端是谁？       | Postman、浏览器、前端或 TestClient；说明它向后端发送 HTTP 请求。       |
| API 层做什么？    | 声明路由、接收校验输入、获得依赖、调用 Service、映射响应。                  |
| `db` 谁创建？    | FastAPI 根据 `DbSession -> Depends(get_db)` 自动创建和清理。 |
| Schema 做什么？  | 定义输入输出契约、类型、验证和序列化边界。                              |
| Service 做什么？ | 执行知识查询、过滤、排序和匹配，不处理 HTTP。                          |
| Model 做什么？   | 映射数据库表、字段和表关系，不等于 API DTO。                         |

如果你能沿着 `q → query.q → Service.search(query=...) → rows → item.content → JSON` 解释每一步，就说明你已经开始真正读懂这条 API，而不是只认识几个框架名称。

## 2.6 在 VSCode 中具体怎样读这条链

不要同时打开十几个文件。按下面的方法来回跳转：

1. 按 `Ctrl+P` 输入 `knowledge.py`，先选择 `api/routes/knowledge.py`，从入口函数读起。
2. 把鼠标停在 `KnowledgeSearchQuery` 上看类型，再按 `F12` 跳到定义。
3. 看完 Schema 后按 `Alt+Left` 回到 Router。
4. 对 `KnowledgeReadService.search` 按 `F12`，进入业务逻辑。
5. 对 `KnowledgeChunk` 按 `F12`，确认字段来自 ORM，而不是凭空出现。
6. 对 `DbSession` 按 `F12`，继续跟到 `get_db` 和 `SessionLocal`。
7. 使用 `Shift+F12` 查找引用，确认新 Router 在哪里被 include。
8. 最后打开测试，用请求和断言反向检查你理解的行为。

阅读时建立一张“变量账本”：

| 变量          | 进入时是什么                 | 离开时变成什么                  |
| ----------- | ---------------------- | ------------------------ |
| `q`         | URL 中的字符串              | 标准化后的 `query.q`          |
| `db`        | FastAPI dependency     | 可执行 ORM 查询的 Session      |
| `statement` | SQLAlchemy Select 对象   | `execute` 后成为 ORM row 列表 |
| `rows`      | `(chunk, document)` 列表 | Router 的 DTO 输入          |
| `items`     | DTO 列表                 | JSON 中的 `items` 数组       |

如果要用断点观察，建议依次停在：

1. `search_knowledge` 第一行，看 FastAPI 注入后的三个参数。
2. `rows = self.db.execute(...)`，看 statement 和数据库返回。
3. `_knowledge_matches`，看 query/haystack。
4. `return KnowledgeSearchResponse(...)`，看最终 DTO。

断点的价值是验证你的执行模型，不是代替阅读。先预测变量是什么，再运行到断点比较预测与真实值。

## 3. 最终接口契约

请求示例：

```http
GET /api/knowledge/search?q=人工确认&category=human_confirmation
```

| 参数         | 是否必填 | 规则                         |
| ---------- | ---- | -------------------------- |
| `q`        | 是    | 去掉多余空白后 1 到 200 个字符。       |
| `category` | 否    | 去掉多余空白后 1 到 80 个字符，精确匹配分类。 |

成功响应：

```json
{
  "items": [
    {
      "source_id": "knowledge:<document_id>:<chunk_id>",
      "document_id": "...",
      "chunk_id": "...",
      "title": "人工确认规则",
      "category": "human_confirmation",
      "source": "safety_policy:v1",
      "safety_level": "general",
      "chunk_index": 0,
      "content": "复诊申请、购药方案、提醒创建等关键动作必须等待用户确认后执行。",
      "keywords": ["人工确认", "关键动作"]
    }
  ]
}
```

没有命中也返回 `200` 和 `{ "items": [] }`。缺少 `q`、纯空格或过长则返回统一 `422 validation_error`。

`source_id` 必须稳定包含 document/chunk id。后续 `RAGSourceRef`、`RunTrace` 和答案可以用它回答“这条事实来自哪里”。

## 4. 开始前准备

先按 [本地环境、启动与部署指南](../LOCAL_SETUP_AND_DEPLOYMENT.md) 配好环境，再从仓库根目录执行：

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -c "from app.main import app; print(app.title)"
git branch --show-current
git status
```

应用标题应为 `Family Health Agent API`。这个练习应留在 `codex/2e-1-read-apis`，不要提前实现 2E-2。

## 5. 写 API 前，先理解项目已经提供的基础设施

你写的三个新文件不是独立运行的。它们站在下面这些已有代码上，所以要先理解“项目已经替你解决了什么”。

### 5.1 `ApiSchema`：所有 API DTO 的共同规则

[backend/app/schemas/common.py](../../backend/app/schemas/common.py) 中：

```python
class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
```

`BaseModel` 是 Pydantic 的数据模型基类。继承后，字段注解不再只是给编辑器看的提示，而会参与运行时校验和 JSON 序列化。

`extra="forbid"` 表示直接构造 Pydantic 对象时，不允许偷偷多出契约外字段。例如响应 DTO 没定义 `created_at`，就不应该把它顺手暴露出去。

`from_attributes=True` 表示 Pydantic 可以从对象属性读取字段。ORM 对象通常不是 dict，而是 `document.title` 这样的属性；这个配置让 DTO 映射更方便。当前知识 Router 采用显式映射，仍保留该统一能力。

### 5.2 ORM Model：数据库里到底保存了什么

[backend/app/models/knowledge.py](../../backend/app/models/knowledge.py) 定义两张表：

```text
knowledge_documents                    knowledge_chunks
-------------------                    ----------------
id (PK) <---------------------------- document_id (FK)
title                                  chunk_index
category                               content
source                                 keywords
content
safety_level
```

`KnowledgeDocument` 保存文档级元数据，`KnowledgeChunk` 保存可检索的小块。这样设计而不是只建一张表，原因是：

1. 一篇长文档可以被拆成多个 chunk。
2. 搜索结果只返回命中的小块，减少无关内容。
3. `document_id + chunk_id` 可以形成稳定来源指针。
4. 以后替换成全文检索或向量检索时，检索单位仍然是 chunk。

关键 SQLAlchemy 语法：

```python
title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
```

- `Mapped[str]`：Python 层把这个属性看成字符串。
- `String(160)`：数据库列最多按 160 长度设计。
- `nullable=False`：数据库不允许 NULL。
- `index=True`：为经常过滤或排序的列建立索引。

```python
document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"))
```

`ForeignKey` 让 chunk 指向真实 document。它描述数据库关系；`relationship(...)` 则提供 Python 对象导航，例如 `document.chunks`。`relationship` 本身不是另一列。

### 5.3 Engine 和 Session：Python 怎样连接 PostgreSQL

[backend/app/core/database.py](../../backend/app/core/database.py) 负责数据库基础设施：

```python
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, ...)
```

- Engine 持有数据库方言、连接方式和连接池策略，不代表一次具体业务请求。
- Session 是一次工作单元，用来查询 ORM、跟踪对象和提交/回滚事务。
- `SessionLocal` 是 Session 工厂，每次调用都会创建一个新 Session。

当前 `.env` 使用：

```text
DATABASE_URL=postgresql+psycopg://hospital:hospital@localhost:5432/family_health
```

这个 URL 可以从左到右读：

| 片段                  | 含义                                              |
| ------------------- | ----------------------------------------------- |
| `postgresql`        | SQLAlchemy 使用 PostgreSQL 方言生成 SQL。              |
| `psycopg`           | Python 使用 psycopg 驱动建立网络连接。                     |
| `hospital:hospital` | 本地演示数据库用户名和密码。                                  |
| `localhost:5432`    | 后端运行在 Windows 主机，所以   连接 Docker 暴露到主机的 5432 端口。 |
| `family_health`     | 目标数据库名。                                         |

SQLAlchemy Engine 会按需从连接池取得数据库连接；Session 通过 Engine 执行 SQL。主机运行的 Uvicorn 使用 `localhost`，而 Compose 内部的 backend 容器使用服务名 `postgres`。`docker-compose.yml` 会为容器覆盖 URL，不能把两个主机名混用。

测试环境例外：`backend/tests/conftest.py` 在导入应用前设置 `sqlite:///:memory:`。因此 `database.py` 才保留下面的 SQLite 分支：

SQLite 特殊配置：

```python
engine_options["connect_args"] = {"check_same_thread": False}
```

FastAPI 的同步 dependency 和路由可能在线程池中执行。关闭 SQLite 的单线程连接检查后，同一个测试连接才能配合这种请求模型使用；这不是 PostgreSQL 联调配置，也不是关闭业务层的并发控制。

内存 SQLite 默认每条连接可能看到不同数据库，所以代码额外使用 `StaticPool`，让测试共享同一连接和同一批表/fixture 数据。这个设计说明“运行数据库”和“测试数据库”可以不同，但 ORM、Service 和 API 契约仍复用同一套代码。

### 5.4 `get_db`：为什么不用完以后 Session 会关闭

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

这是 generator dependency：

1. 请求开始时创建 Session。
2. `yield db` 把它交给下游 dependency 和 Router。
3. 请求成功、校验失败或业务抛异常后，都会回到 `finally`。
4. `db.close()` 释放数据库资源。

这比在每个 Router 手工写 `open/close` 更不容易泄漏连接。

### 5.5 `DbSession` 和 `DemoUser`：类型注解也是依赖声明

[backend/app/api/dependencies.py](../../backend/app/api/dependencies.py) 中：

```python
DbSession = Annotated[Session, Depends(get_db)]
DemoUser = Annotated[User, Depends(get_demo_user)]
```

`Annotated` 同时保存两个信息：这个参数在 Python 类型上是 `Session/User`，在 FastAPI 运行时应通过哪个 dependency 取得。

`get_demo_user` 会用配置手机号查询 active user。知识文档是全局安全知识，不按 `member_id` 过滤，但保留 `DemoUser` 依赖能让所有 demo API 走统一入口。注意：这只是阶段性 demo 身份，不是生产认证授权。

### 5.6 `main.py`：统一错误和 `/api` 前缀从哪里来

[backend/app/main.py](../../backend/app/main.py) 完成三个与本接口直接相关的工作：

1. 创建 FastAPI 应用和 Swagger 元数据。
2. 把 `RequestValidationError` 转换成统一 `422 validation_error` JSON。
3. 使用 `app.include_router(api_router, prefix="/api")` 添加顶层路径。

因此，Schema 校验失败时 Router 函数根本不会执行，也不需要在每个 Router 里复制 `try/except`。统一异常 handler 是横切基础设施，业务 Router 只关注成功流程和明确业务异常。

## 6. 第一步：创建 Pydantic Schema

新建 `backend/app/schemas/knowledge.py`：

```python
from pydantic import Field, field_validator

from app.schemas.common import ApiSchema


class KnowledgeSearchQuery(ApiSchema):
    # 先限制原始字符串长度，避免无限长查询进入 Service。
    q: str = Field(min_length=1, max_length=200)
    # category 不传时是 None；传入时必须满足长度限制。
    category: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        # split + join 会去掉首尾空白并压缩连续空白。
        normalized = " ".join(value.split())
        # q="   " 原始长度大于 1，但业务上仍是空查询，必须拒绝。
        if not normalized:
            raise ValueError("q must not be blank")
        return normalized

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("category must not be blank")
        return normalized


class KnowledgeSearchItemResponse(ApiSchema):
    # 稳定来源指针和数据库标识。
    source_id: str
    document_id: str
    chunk_id: str

    # 调用方真正需要看到的内容。
    title: str
    category: str
    source: str
    safety_level: str
    chunk_index: int
    content: str
    keywords: list[str]


class KnowledgeSearchResponse(ApiSchema):
    # 无结果也返回空 list，不返回 null。
    items: list[KnowledgeSearchItemResponse]
```

### 6.1 这段 Schema 代码实现了什么

`KnowledgeSearchQuery` 是输入边界。只要参数没有通过它，Service 就不会收到数据：

| 输入              | 标准化/校验结果                         |
| --------------- | -------------------------------- |
| `q=人工确认`        | `q` 保持为 `人工确认`。                  |
| `q=  人工   确认  ` | 被标准化成 `人工 确认`。                   |
| `q=   `         | validator 抛 ValueError，最终返回 422。 |
| 不传 `q`          | 必填字段缺失，最终返回 422。                 |
| `q` 超过 200 字符   | Field 长度校验失败，最终返回 422。           |
| 不传 `category`   | 值为 None，Service 不增加分类 WHERE 条件。  |

Pydantic 默认先处理字段类型和 `Field` 约束，再执行这里的 after validator。三个空格的原始长度是 3，所以仅靠 `min_length=1` 挡不住；`normalize_query` 将其压缩为空字符串后再次判断，才补上业务语义。

`@classmethod` 表示 validator 不依赖已经创建好的对象实例。验证发生在模型构造过程中，此时 `KnowledgeSearchQuery` 实例还没有完整产生。

`KnowledgeSearchItemResponse` 和 `KnowledgeSearchResponse` 是输出边界。它们保证：

1. 每个结果必须有 document/chunk 标识和来源指针。
2. `keywords` 永远是字符串列表。
3. 无结果用 `items=[]`，调用方不需要同时处理 `null`。
4. ORM 中没写进 DTO 的内部字段不会自动进入响应。

为什么不用 ORM 直接响应：ORM 描述数据库如何保存，DTO 描述外部能看到什么。二者分离可避免新增内部字段时意外泄露，并允许定义 `source_id` 这样的计算字段。

### 6.2 阅读 Schema 时抓住三类字段

1. 请求字段：调用方可以控制，例如 `q/category`。
2. 数据字段：来自数据库，例如 `title/content/keywords`。
3. 计算字段：由后端根据多个值生成，例如 `source_id`。

分清来源后，你就能继续追踪：请求字段进入 Service，数据字段从 ORM 返回，计算字段在 Router 映射时产生。

检查这一层：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m compileall backend\app\schemas\knowledge.py
python -c "from app.schemas.knowledge import KnowledgeSearchQuery; print(KnowledgeSearchQuery(q='  人工   确认  '))"
```

第二条应显示 `q='人工 确认'`。若出现 `No module named 'app'`，说明没有设置 `PYTHONPATH` 或不在仓库根目录。

## 7. 第二步：创建只读 Service

新建 `backend/app/services/knowledge_read_service.py`：

```python
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeReadService:
    """只负责确定性知识查询，不处理 HTTP。"""

    def __init__(self, db: Session) -> None:
        # Session 从外部注入，Service 不自行创建连接。
        self.db = db

    def search(
        self,
        *,
        query: str,
        category: str | None,
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        # 防御性标准化，保证 Service 被其他入口调用时也行为稳定。
        normalized_query = " ".join(query.split()).lower()
        if not normalized_query:
            return []

        # 每行同时取 chunk 和它所属的 document。
        statement: Select[tuple[KnowledgeChunk, KnowledgeDocument]] = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeChunk.document_id == KnowledgeDocument.id,
            )
            # 固定排序让 API 和测试结果可重复。
            .order_by(KnowledgeDocument.category, KnowledgeChunk.chunk_index)
        )

        if category is not None:
            statement = statement.where(KnowledgeDocument.category == category)

        rows = list(self.db.execute(statement).all())
        matches: list[tuple[KnowledgeChunk, KnowledgeDocument]] = []

        for chunk, document in rows:
            # 将允许搜索的字段拼成统一小写文本。
            haystack = " ".join(
                [
                    document.title,
                    document.category,
                    document.source,
                    document.content,
                    chunk.content,
                    " ".join(chunk.keywords or []),
                ]
            ).lower()
            if _knowledge_matches(normalized_query, haystack):
                matches.append((chunk, document))

        return matches


def _knowledge_matches(query: str, haystack: str) -> bool:
    # 优先匹配完整短语，例如“人工确认”。
    if query in haystack:
        return True
    # 完整短语没命中，再按空格或 / 拆词，任一词命中即成功。
    tokens = [token for token in query.replace("/", " ").split() if token]
    return any(token in haystack for token in tokens)
```

### 7.1 这段 Service 代码实现了什么

Service 接收“已经校验过的查询条件”，返回“命中的 ORM 对”。它不知道请求来自 Postman、FastAPI 还是未来的内部调用，因此没有 HTTP 状态码、Request、Response 或 Swagger 概念。

```python
def __init__(self, db: Session) -> None:
    self.db = db
```

这是构造器注入。Session 由外部创建，Service 只使用它。测试可以传测试 Session，FastAPI 可以传请求 Session，不需要 Service 偷偷连接另一个数据库。

```python
def search(self, *, query: str, category: str | None) -> ...:
```

单独的 `*` 表示后面的参数必须使用名字调用：

```python
service.search(query="确认", category=None)  # 清楚
service.search("确认", None)                 # Python 会拒绝
```

这能减少两个同为字符串/可选值的参数被错误交换。

返回类型：

```python
list[tuple[KnowledgeChunk, KnowledgeDocument]]
```

从外向内读：这是一个 list；list 每项是二元 tuple；tuple 第一项是 chunk，第二项是 document。这也解释了后面为什么必须写 `for chunk, document in rows`。

### 7.2 SQLAlchemy 查询怎样变成 SQL

`select(...)` 只构造查询对象，不会立刻访问数据库。真正执行发生在：

```python
self.db.execute(statement).all()
```

这段表达式大致对应下面的 SQL 思想：

```sql
SELECT knowledge_chunks.*, knowledge_documents.*
FROM knowledge_chunks
JOIN knowledge_documents
  ON knowledge_chunks.document_id = knowledge_documents.id
WHERE knowledge_documents.category = :category  -- 只有传 category 才有
ORDER BY knowledge_documents.category, knowledge_chunks.chunk_index;
```

不要背 SQLAlchemy 链式语法，先用 SQL 思维读它：

1. `SELECT` 要哪些对象？chunk 和 document。
2. `FROM/JOIN` 两张表怎样关联？外键 document_id。
3. `WHERE` 是否有可选过滤？category。
4. `ORDER BY` 怎样保证稳定顺序？分类和 chunk_index。

固定排序不仅为了页面好看，也让相同 fixture 每次返回相同顺序，测试才不会偶发失败。

### 7.3 关键词匹配的真实数据流

假设 seed 中有：

```text
title       = 人工确认规则
category    = human_confirmation
source      = safety_policy:v1
chunk       = 复诊申请、购药方案、提醒创建等关键动作必须等待用户确认后执行。
keywords    = [人工确认, 关键动作]
```

代码把这些允许检索的字段拼成一个小写字符串 `haystack`。查询 `q=人工确认` 时：

```python
if query in haystack:
    return True
```

完整短语命中，当前 `(chunk, document)` 被加入 `matches` 一次。多个字段同时包含同一词也不会重复追加，因为每一行只执行一次 append。

查询 `q=确认 / 安全` 时，完整字符串通常不在 haystack，于是代码把 `/` 替换为空格并拆成 token，只要任一 token 命中就返回 True。这是 OR 语义，不是“所有词都必须命中”的 AND 语义。

### 7.4 为什么这是 baseline，而不是最终搜索方案

优点：

- 输入相同，结果相同，容易写测试和 Harness 评估。
- 不调用 LLM，不会生成无来源知识。
- 代码短，适合先验证 API 契约和 `source_id`。

限制：

- 当前先查出候选行，再在 Python 中逐行拼 haystack，数据量大时效率差。
- 字符串包含判断不理解同义词和语义。
- 中文没有天然空格分词，复杂查询效果有限。
- OR token 可能扩大结果范围。

粗略复杂度可以理解为“知识块数量 N × 每块文本长度 L”。当前 seed 很小，成本可接受。未来升级可以是数据库全文检索、倒排索引或向量召回，但都必须继续返回相同的来源字段，不能牺牲可追溯性。

### 7.5 为什么不直接复用 Agent Tool

已有 `search_safety_knowledge_context` 面向 Agent，返回 evidence wrapper；这个接口面向 HTTP 客户端，返回分页前的 item list。底层知识相同不代表输出契约相同。直接让 Router 调 Tool 会把 API 权限、工具 Trace 和 HTTP DTO 混在一起。

当前 Service 返回 ORM 对，再由 Router 映射 DTO，和 `ReadApiService` 风格一致。分层的价值不是多建文件，而是每层变化原因不同：搜索算法变更主要改 Service，HTTP 字段变更主要改 Schema/Router。

检查：

```powershell
python -m compileall backend\app\services\knowledge_read_service.py
```

## 8. 第三步：创建 FastAPI Router

新建 `backend/app/api/routes/knowledge.py`：

```python
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession, DemoUser
from app.schemas.common import ApiErrorResponse
from app.schemas.knowledge import (
    KnowledgeSearchItemResponse,
    KnowledgeSearchQuery,
    KnowledgeSearchResponse,
)
from app.services.knowledge_read_service import KnowledgeReadService


# main.py 统一添加 /api，所以这里仅写 /knowledge。
router = APIRouter(prefix="/knowledge")


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses={422: {"model": ApiErrorResponse}},
    summary="Search knowledge chunks",
)
def search_knowledge(
    # FastAPI 从 query string 构造并校验这个 DTO。
    query: Annotated[KnowledgeSearchQuery, Query()],
    # 这两个对象由 dependencies.py 自动提供。
    db: DbSession,
    _demo_user: DemoUser,
) -> KnowledgeSearchResponse:
    # 下划线表示函数不读取 demo user，但认证入口依赖仍会执行。
    rows = KnowledgeReadService(db).search(
        query=query.q,
        category=query.category,
    )

    # 明确映射对外字段，避免直接暴露 ORM。
    return KnowledgeSearchResponse(
        items=[
            KnowledgeSearchItemResponse(
                source_id=f"knowledge:{document.id}:{chunk.id}",
                document_id=document.id,
                chunk_id=chunk.id,
                title=document.title,
                category=document.category,
                source=document.source,
                safety_level=document.safety_level,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                keywords=list(chunk.keywords or []),
            )
            for chunk, document in rows
        ]
    )
```

### 8.1 路由装饰器到底做了什么

```python
@router.get("/search", response_model=KnowledgeSearchResponse, ...)
```

Python 导入文件时，装饰器把下面的函数登记成一个 GET endpoint。它记录路径、响应 Schema、错误文档和 Swagger summary。

- `response_model` 不只是文档，它还会约束和序列化实际返回值。
- `responses={422: ...}` 主要补充 OpenAPI 中的错误响应说明；真正的统一 422 body 由 `main.py` exception handler 生成。
- 函数使用普通 `def`，FastAPI 会把同步路由放到线程池执行，避免直接阻塞事件循环。

### 8.2 FastAPI 怎样填充函数参数

你没有手工调用：

```python
search_knowledge(query=..., db=..., _demo_user=...)
```

FastAPI 会解析函数签名并执行 dependency graph：

| 参数           | 运行时来源                                                         |
| ------------ | ------------------------------------------------------------- |
| `query`      | `Query()` 收集 URL query string，再经 `KnowledgeSearchQuery` 校验得到。 |
| `db`         | `Depends(get_db)` 创建的 Session。                                |
| `_demo_user` | `Depends(get_demo_user)` 查询得到的 User。                          |

变量名前的 `_` 只是 Python 约定，表示函数体不直接读取它；并不表示 FastAPI 跳过 dependency。用户不存在时，请求仍会在进入函数体前失败。

这里必须区分 `Query()` 和 `Depends()`：

| 写法                                           | 表达的含义                                | 适合本接口吗                                                                                               |
| -------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `Annotated[KnowledgeSearchQuery, Query()]`   | 这是一个由 URL 查询参数组成的 Pydantic 模型。       | 是。字段错误属于请求错误，应进入统一 `422` handler。                                                                    |
| `Annotated[KnowledgeSearchQuery, Depends()]` | 把 `KnowledgeSearchQuery` 类当作依赖提供者调用。 | 不推荐。在当前 FastAPI/Pydantic 版本组合下，自定义 validator 抛出的 `ValidationError` 可能不会转换为 `RequestValidationError`。 |

项目曾短暂使用 `Depends()`。正常 `q` 能搜索成功，但 `q="   "` 会让 `field_validator` 抛出原始 Pydantic `ValidationError`，TestClient 直接报异常，真实服务会表现为 `500`，而不是契约要求的 `422 validation_error`。改成 `Query()` 后，FastAPI 知道这个模型属于 HTTP query 参数，会把字段错误放在 `loc=["query", "q"]` 下，再交给 `main.py` 的 `RequestValidationError` handler。

不要通过“全局捕获所有 Pydantic `ValidationError` 并返回 422”来掩盖这个问题。Response DTO 或内部对象构造失败也可能产生 `ValidationError`，那些通常是服务端代码错误，不应该伪装成用户输入错误。正确做法是在路由签名里准确声明数据来源。

### 8.3 Router 中发生了两次类型转换

第一次：HTTP 字符串变成输入 DTO。

```text
?q=人工确认&category=human_confirmation
                    |
                    v
KnowledgeSearchQuery(q="人工确认", category="human_confirmation")
```

第二次：ORM 对变成输出 DTO。

```text
(KnowledgeChunk, KnowledgeDocument)
                    |
                    v
KnowledgeSearchItemResponse
                    |
                    v
JSON object
```

`source_id` 在第二次转换中产生：

```python
f"knowledge:{document.id}:{chunk.id}"
```

它没有单独存进数据库，因为它可以由两个稳定主键确定性重建。只要格式规则不变，同一个 chunk 每次都得到同一个指针。

### 8.4 怎样读列表推导式

```python
items=[KnowledgeSearchItemResponse(...) for chunk, document in rows]
```

初学时把它展开成普通循环：

```python
items = []
for chunk, document in rows:
    item = KnowledgeSearchItemResponse(
        source_id=f"knowledge:{document.id}:{chunk.id}",
        # 其他字段省略
    )
    items.append(item)

return KnowledgeSearchResponse(items=items)
```

两种写法逻辑相同。先读懂展开版，再回来看推导式，不要把紧凑语法误认为新的业务逻辑。

Router 最终只做三件事：接收已校验参数、调用 Service、映射 DTO。若里面出现复杂 `select()`、关键词算法或 LLM 调用，它就同时承担协议层和业务层，测试与复用都会变困难。

检查：

```powershell
python -m compileall backend\app\api\routes\knowledge.py
```

现在访问仍会 `404`，因为还没把新 Router 接入主 Router。

## 9. 第四步：注册 Router

打开 `backend/app/api/router.py`，新增 import：

```python
from app.api.routes.knowledge import router as knowledge_router
```

再新增：

```python
api_router.include_router(knowledge_router, tags=["knowledge"])
```

最终路径由三段组成：

```text
main.py prefix       /api
router prefix        /knowledge
route path           /search
最终路径             /api/knowledge/search
```

### 9.1 为什么必须同时 import 和 include

`from ... import router` 让 Python 执行知识路由文件并拿到 Router 对象；`include_router(...)` 再把这个对象中的路径复制到主 Router。只 import 不 include，代码执行了但主应用找不到路径；只写 include 却没有对象，Python 会直接报 NameError/import error。

完整组合关系：

```text
knowledge.py: APIRouter(prefix="/knowledge") + @get("/search")
                              |
api/router.py: include_router(knowledge_router)
                              |
main.py: include_router(api_router, prefix="/api")
                              |
最终: GET /api/knowledge/search
```

因此遇到 404 时，按这个顺序检查：HTTP 方法、函数 path、子 Router prefix、主 Router 是否 include、main 是否 include 主 Router。不要一看到 404 就先怀疑数据库，因为请求根本还没有到数据库层。

## 10. 第五步：启动后端并用 Swagger 检查

### 10.1 准备数据库

本练习的真实数据库使用 Docker PostgreSQL。第一次拉取镜像前，先按 [本地环境、启动与部署指南](../LOCAL_SETUP_AND_DEPLOYMENT.md) 把 Docker Desktop 的 `Disk image location` 设置为 `E:\DockerData`。

确认根目录 `.env`：

```powershell
Set-Location E:\project_code\hospital
Get-Content .env | Select-String "DATABASE_URL|BACKEND_PORT"
```

当前应看到类似：

```text
DATABASE_URL=postgresql+psycopg://hospital:hospital@localhost:5432/family_health
BACKEND_PORT=8000
```

启动基础设施：

```powershell
docker compose up -d postgres redis
docker compose ps
```

等待 `family-health-postgres` 和 `family-health-redis` 都显示 `healthy`。PostgreSQL 数据保存在 Docker named volume 中；当 Docker 磁盘位置是 `E:\DockerData` 时，镜像与 volume 的主要空间也位于 E 盘。不要在同一次启动中混用 PostgreSQL 与文件 SQLite 两条 `DATABASE_URL`。

### 10.2 执行迁移和 seed

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
```

`seed.py` 会准备“人工确认规则”“医疗安全边界规则”等知识数据。它可重复执行，不应该创建重复记录。

这里要区分两个动作：

- `alembic upgrade head` 根据 migration 创建/升级表结构。
- `seed.py` 使用 ORM 向已经存在的表写演示数据。

没有 migration，seed 会因表不存在失败；没有 seed，接口能运行但可能只返回空结果。

#### PostgreSQL 实跑曾发现的 revision 长度问题

Alembic 自己也有一张 `alembic_version` 表，用来记录数据库当前执行到哪个 revision。它默认把 `version_num` 定义为 `VARCHAR(32)`，而项目中的 `0002_add_agent_harness_trace_fields` 超过 32 个字符：

```text
SQLite: VARCHAR(32) 只是类型提示，超长字符串仍能写入
PostgreSQL: 严格执行 32 字符限制，抛出 StringDataRightTruncation
```

这就是“SQLite 测试通过不能替代 PostgreSQL 联调”的具体案例。项目没有改掉已经使用的 revision ID，而是在初始 migration 的 PostgreSQL 分支把 Alembic 内部列扩为 `VARCHAR(64)`。修复保留 migration 历史标识，也没有修改任何业务 ORM 字段。

阅读 traceback 时应从最底部向上找：数据库异常是 `StringDataRightTruncation`，失败 SQL 是更新 `alembic_version`，因此问题在 migration 元数据，不在刚新增的 Agent 字段。

同样，Docker 构建时要读 `.dockerignore`：它决定哪些本机文件根本不进入 build context。前端不排除 `node_modules` 和 `.next` 时，即使 Dockerfile 最终没有使用这些目录，也可能先向 Docker Engine 传输数百 MB。依赖应在 Linux 镜像内按 `package-lock.json` 安装，而不是复制 Windows 的依赖目录。

### 10.3 启动 FastAPI

```powershell
python -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

保持终端运行。看到 `Uvicorn running on http://127.0.0.1:8000` 后继续：

1. 打开 `http://localhost:8000/docs`。
2. 找到 `knowledge` 分组。
3. 展开 `GET /api/knowledge/search`。
4. 点击 `Try it out`。
5. `q` 输入 `人工确认`，`category` 暂时留空。
6. 点击 `Execute`。
7. 确认状态码是 `200`，每项包含 `source_id`。

Swagger 没出现接口时，检查是否保存了文件、是否注册 Router、uvicorn reload 是否报错。

Swagger 的作用是读取 FastAPI 生成的 OpenAPI 契约。它能证明路径和 Schema 已被注册，但不能替代自动化测试，也不能证明所有失败路径都正确。

## 11. 第六步：编写自动化测试

这是本次学习实战的主要测试代码。项目中已经完成 `backend/tests/test_knowledge_api.py`；下面保留完整实现和注释，便于你复盘每个 fixture、请求和断言为什么存在。

为什么这里优先写 API 集成测试，而不只测 `_knowledge_matches`：一个接口最容易在层与层之间出错，例如 Router 忘记注册、dependency 没有 override、DTO 字段映射错、异常格式不一致。TestClient 会穿过 FastAPI、Schema、dependency、Service、ORM 和响应序列化，正好验证完整链路。

它又不需要启动真实 Uvicorn 端口，所以比 Postman 更快、更稳定，适合每次提交自动运行。

下面是一份完整最小集成测试：

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import KnowledgeChunk, KnowledgeDocument, User


@pytest.fixture
def knowledge_client() -> Iterator[TestClient]:
    # conftest.py 已把测试数据库切成内存 SQLite。
    # 每个测试先重建空表，保证测试之间互不污染。
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # DemoUser dependency 按手机号查用户，fixture 必须创建默认 demo user。
    session.add(
        User(
            id="user-knowledge-test",
            name="Knowledge Test User",
            phone="13800000001",
        )
    )

    # 固定 id 使 source_id 断言清晰、可重复。
    document = KnowledgeDocument(
        id="knowledge-document-test",
        title="人工确认规则",
        category="human_confirmation",
        source="safety_policy:v1",
        content="关键动作必须等待用户确认后执行。",
        safety_level="general",
    )
    chunk = KnowledgeChunk(
        id="knowledge-chunk-test",
        document_id=document.id,
        chunk_index=0,
        content="复诊申请、购药方案、提醒创建都必须等待用户确认。",
        keywords=["人工确认", "关键动作"],
    )
    session.add_all([document, chunk])
    session.commit()

    def override_get_db() -> Iterator[Session]:
        # 请求使用刚才写入测试数据的 Session。
        yield session

    # 用测试 Session 替换应用正常的 get_db dependency。
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client

    # yield 之后是清理阶段，恢复全局 app 并关闭数据库资源。
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_search_returns_a_traceable_knowledge_chunk(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "人工确认"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "source_id": "knowledge:knowledge-document-test:knowledge-chunk-test",
                "document_id": "knowledge-document-test",
                "chunk_id": "knowledge-chunk-test",
                "title": "人工确认规则",
                "category": "human_confirmation",
                "source": "safety_policy:v1",
                "safety_level": "general",
                "chunk_index": 0,
                "content": "复诊申请、购药方案、提醒创建都必须等待用户确认。",
                "keywords": ["人工确认", "关键动作"],
            }
        ]
    }


def test_category_filter_keeps_requested_category(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "确认", "category": "human_confirmation"},
    )

    assert response.status_code == 200
    assert all(
        item["category"] == "human_confirmation"
        for item in response.json()["items"]
    )


def test_no_match_returns_an_empty_list(knowledge_client: TestClient) -> None:
    response = knowledge_client.get(
        "/api/knowledge/search",
        params={"q": "绝对不会命中的词"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("params", [{}, {"q": "   "}])
def test_missing_or_blank_query_uses_uniform_validation_error(
    knowledge_client: TestClient,
    params: dict[str, str],
) -> None:
    response = knowledge_client.get("/api/knowledge/search", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_openapi_exposes_knowledge_search(
    knowledge_client: TestClient,
) -> None:
    response = knowledge_client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/knowledge/search" in response.json()["paths"]
```

### 11.1 先读懂 fixture 生命周期

`backend/tests/conftest.py` 在测试导入应用前执行：

```python
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
```

这个时机很重要。`app.core.config.settings` 和数据库 Engine 都在模块 import 时创建；如果先 import app 再改环境变量，Engine 已经指向旧数据库。

测试使用内存 SQLite，不操作 Docker PostgreSQL。fixture 的顺序是：

```text
drop/create 测试表
        -> 创建 demo user/document/chunk
        -> commit fixture 数据
        -> override get_db
        -> yield TestClient 给测试
        -> 测试发送请求和断言
        -> 清理 override/session/table
```

`app.dependency_overrides[get_db] = override_get_db` 是核心。它告诉 FastAPI：“本次测试不要用应用默认 Session，请使用 fixture 准备好数据的 Session。”不这样做时，TestClient 可能连到另一份数据库，看不到 fixture。

`yield` 将 fixture 分成 setup 和 teardown。即使断言失败，pytest 仍会执行 yield 之后的清理，避免污染后续测试。

### 11.2 每个测试究竟证明什么

| 测试              | Given（准备）    | When（动作）           | Then（证明）                          |
| --------------- | ------------ | ------------------ | --------------------------------- |
| traceable chunk | 有一条确认规则      | `q=人工确认`           | 路由、查询、匹配、DTO、source_id 全链路正确。     |
| category filter | 有目标分类        | 同时传 q/category     | 可选 WHERE 条件生效，结果没有跨分类。            |
| no match        | 有知识但查询词不存在   | 发合法搜索              | 空搜索是 200，不被误当 404。                |
| invalid query   | 缺 q 或只有空格    | 发非法搜索              | Pydantic 在 Service 前拦截，并使用统一 422。 |
| OpenAPI         | 应用已注册 Router | 请求 `/openapi.json` | 路由没有只存在于文件里，而是真正进入主 app。          |

测试阅读使用 Given-When-Then：先看 fixture/参数提供了什么，再看唯一请求，最后看断言。不要从一堆 assert 开始倒猜业务。

成功用例采用完整 JSON 断言，是为了及时发现字段被删、改名、来源指针变化或内部字段意外暴露。分类用例只断言它关注的不变量，避免重复写整份 JSON。

### 11.3 先只运行新测试

```powershell
Set-Location E:\project_code\hospital
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var | Out-Null
python -m pytest backend\tests\test_knowledge_api.py -q -p no:cacheprovider --basetemp=var\pytest-knowledge
```

### 11.4 再运行完整回归

```powershell
python -m pytest backend\tests -q -p no:cacheprovider --basetemp=var\pytest-all
python -m compileall backend\app backend\tests
```

接口测试通过但旧测试失败，仍不算完成。回归测试确认你没有破坏 Context、Harness、Tool 和已有读取 API。

### 11.5 常见测试失败定位

| 现象              | 首先检查                                           |
| --------------- | ---------------------------------------------- |
| 正常请求 `404`      | Router 是否注册，路径是否为 `/api/knowledge/search`。     |
| 正常请求 `422`      | Schema 字段名和 validator 是否正确。                    |
| 请求 `500`        | traceback、join 条件、循环变量顺序是否为 `chunk, document`。 |
| `items=[]`      | fixture 是否 commit，haystack 是否包含关键词。            |
| `source_id` 不一致 | 是否使用 `knowledge:{document.id}:{chunk.id}`。     |
| demo user 不存在   | fixture 是否创建默认手机号用户。                           |

## 12. 第七步：用 Postman 完整验收

完成第 10 节后，后端应运行在 `http://localhost:8000`，并且 Docker PostgreSQL migration/seed 已完成。若尚未满足这两个条件，先不要进入 Postman 验收。

三个验证工具回答的问题不同：

| 工具                | 主要回答                       |
| ----------------- | -------------------------- |
| Swagger           | FastAPI 是否生成了正确路径、参数和响应契约？ |
| Postman           | 一个独立外部客户端通过真实网络调用时是否成功？    |
| pytest/TestClient | 这些行为能否在每次修改后自动、隔离、重复验证？    |

所以 Postman 不是“测试的全部”，但它能发现端口、URL、真实启动配置和编码等 TestClient 不覆盖的问题。

### 12.1 创建 Postman 环境

1. 打开 Postman，左侧选择 `Environments`。
2. 点击 `Create environment`，命名 `hospital-local`。
3. 新增变量 `base_url`。
4. Initial value 和 Current value 都填 `http://localhost:8000`。
5. 保存，在右上角环境下拉框选择 `hospital-local`。

以后都用 `{{base_url}}`，端口变化时只改一处。

### 12.2 创建 Collection

1. 左侧选择 `Collections`。
2. 点击 `New Collection`。
3. 命名 `Hospital Agent Local API`。
4. 在 Collection 下依次创建下面七个请求。

### 12.3 请求一：确认服务在线

- 名称：`01 Health`
- 方法：`GET`
- URL：`{{base_url}}/health`
- Body：不填写

点击 `Send`，预期 `200`：

```json
{
  "status": "ok"
}
```

在 `Scripts -> Post-response`（旧版 Postman 叫 `Tests`）加入：

```javascript
pm.test("health returns 200", function () {
    pm.response.to.have.status(200);
});

pm.test("service is healthy", function () {
    const body = pm.response.json();
    pm.expect(body.status).to.eql("ok");
});
```

再次 Send，下方 Test Results 应全部 PASS。

### 12.4 请求二：确认 seed 用户存在

- 名称：`02 List Family Members`
- 方法：`GET`
- URL：`{{base_url}}/api/family-members`

预期 `200` 且 `items` 非空。这一步验证 `.env` 的 `DEMO_USER_PHONE` 与 seed 一致。若返回 `configured demo user was not found`，重新执行：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m alembic upgrade head
python scripts\seed.py
```

### 12.5 请求三：正常知识搜索

- 名称：`03 Knowledge Search Success`
- 方法：`GET`
- URL：`{{base_url}}/api/knowledge/search`
- 在 `Params` 表格添加 `q`，值为 `人工确认`

GET 参数应放 Params，不放 Body。预期 `200` 且 `items` 非空。Post-response：

```javascript
pm.test("knowledge search returns 200", function () {
    pm.response.to.have.status(200);
});

pm.test("every item has a traceable source", function () {
    const body = pm.response.json();
    pm.expect(body.items).to.be.an("array").that.is.not.empty;

    body.items.forEach(function (item) {
        pm.expect(item.source_id).to.match(/^knowledge:[^:]+:[^:]+$/);
        pm.expect(item.document_id).to.be.a("string").that.is.not.empty;
        pm.expect(item.chunk_id).to.be.a("string").that.is.not.empty;
    });
});
```

### 12.6 请求四：分类过滤

复制请求三，命名 `04 Knowledge Search With Category`，Params 为：

| Key        | Value                |
| ---------- | -------------------- |
| `q`        | `确认`                 |
| `category` | `human_confirmation` |

Post-response：

```javascript
pm.test("all results match requested category", function () {
    pm.response.to.have.status(200);
    const body = pm.response.json();

    body.items.forEach(function (item) {
        pm.expect(item.category).to.eql("human_confirmation");
    });
});
```

### 12.7 请求五：无结果不是错误

- 名称：`05 Knowledge Search No Match`
- 方法：`GET`
- URL：`{{base_url}}/api/knowledge/search`
- Params：`q=绝对不会命中的词`

Post-response：

```javascript
pm.test("no match returns an empty list", function () {
    pm.response.to.have.status(200);
    const body = pm.response.json();
    pm.expect(body).to.deep.eql({ items: [] });
});
```

### 12.8 请求六：缺少必填参数

- 名称：`06 Knowledge Search Missing Query`
- 方法：`GET`
- URL：`{{base_url}}/api/knowledge/search`
- Params：不传 `q`

Post-response：

```javascript
pm.test("missing q returns uniform 422", function () {
    pm.response.to.have.status(422);
    const body = pm.response.json();
    pm.expect(body.error.code).to.eql("validation_error");
});
```

### 12.9 请求七：纯空格参数

- 名称：`07 Knowledge Search Blank Query`
- 方法：`GET`
- URL：`{{base_url}}/api/knowledge/search?q=%20%20%20`

`%20` 是 URL 中的空格。预期 `422 validation_error`。这一步证明 `field_validator` 生效：只有 `Field(min_length=1)` 无法拒绝三个空格。

### 12.10 Postman 最终通过标准

| 场景        | 状态码   | 必须满足                          |
| --------- | ----- | ----------------------------- |
| health    | `200` | `status=ok`                   |
| demo user | `200` | `items` 非空                    |
| 正常搜索      | `200` | 每项有来源指针                       |
| 分类过滤      | `200` | 每项分类匹配                        |
| 无命中       | `200` | `{ "items": [] }`             |
| 缺少 `q`    | `422` | `error.code=validation_error` |
| 空白 `q`    | `422` | `error.code=validation_error` |

## 13. Postman 常见问题

### `ECONNREFUSED` / Could not send request

后端未运行或端口不对。先用浏览器访问 `http://localhost:8000/health`，并检查 uvicorn 终端。

### `404 Not Found`

检查 URL、Router 注册和 uvicorn reload。接口准确路径是 `/api/knowledge/search`。

### `500 Internal Server Error`

真正原因在 uvicorn PowerShell 的 traceback。先看最后 5 到 10 行，重点检查 join、变量顺序和字段名。

### demo user 不存在

检查根目录 `.env` 中 `DEMO_USER_PHONE=13800000001`，再运行 migration 和 seed，并从仓库根目录启动 uvicorn。

### 正常请求始终 `items=[]`

确认 seed 已执行；检查 category 拼写、haystack 字段和循环是否写成 `for chunk, document in rows`。

## 14. 这组代码最终实现了什么

完成测试后，这不是“一个能搜字符串的函数”，而是一条完整的只读 API 用例：

| 已实现能力         | 由哪些代码共同完成                                          |
| ------------- | -------------------------------------------------- |
| 对外暴露 GET 搜索入口 | Uvicorn + FastAPI + Router 注册。                     |
| 校验和标准化查询参数    | Pydantic Query Schema + main.py 统一异常 handler。      |
| 建立请求级数据库生命周期  | Depends + `get_db` + SessionLocal。                 |
| 复用 demo 用户入口  | `DemoUser/get_demo_user` dependency。               |
| 从两张关系表读取知识    | SQLAlchemy Model + Select + Join。                  |
| 按分类过滤和稳定排序    | Service 的 WHERE/ORDER BY。                          |
| 执行可重复关键词匹配    | `_knowledge_matches` baseline。                     |
| 返回可追溯结果       | Router 生成 source_id，Response DTO 固定字段。             |
| 区分空结果和错误      | 空匹配 200；非法输入 422；demo user 缺失 404。                 |
| 自动生成接口文档      | FastAPI response_model/OpenAPI/Swagger。            |
| 隔离验证完整请求链     | pytest fixture + dependency override + TestClient。 |

它明确没有实现：

| 未实现能力                   | 为什么不在本阶段做                         |
| ----------------------- | --------------------------------- |
| 真实登录和授权                 | 当前仍是固定 demo user，认证属于后续 API 安全阶段。 |
| 按 member_id 检索知识        | 当前知识是全局规则，不是成员医疗事实。               |
| 向量检索和语义排序               | 先保留确定性、可解释、可测试的 baseline。         |
| 分页、相关度评分和高亮             | seed 数据很小，先完成契约闭环。                |
| 创建或修改知识                 | 本接口只读。                            |
| LLM 回答生成                | 搜索 API 只返回来源，Agent/RAG 在另一层消费。    |
| PostgreSQL 负载、容灾和生产性能验收 | 本阶段只做本地 Docker 集成，不代表生产容量。        |

### 14.1 不看文档时，你应该能回答

1. 为什么 FastAPI 应用还需要 Uvicorn？
2. 为什么 Python 类型注解还需要 Pydantic？
3. ORM Model 和 API Response DTO 有什么区别？
4. Session 为什么由 dependency 创建，而不是 Service 自己创建？
5. `select` 在哪一行真正访问数据库？
6. Join 条件为什么是 `chunk.document_id == document.id`？
7. `category=None` 时为什么没有 WHERE？
8. 为什么 `q="   "` 不能只依赖 `min_length=1`？
9. 为什么无命中是 200，而 member/user 不存在是 404？
10. 为什么 SQLite pytest 通过仍不能替代 PostgreSQL 集成验证，而本地 PostgreSQL 通过又不能等同于生产验证？

答不出来的题就是下一次回到代码继续跟踪的入口。

## 15. 最终 Code Review 清单

- [x] `schemas/knowledge.py` 的 DTO 都继承 `ApiSchema`。
- [x] 空白 `q` 被 validator 拒绝。
- [x] SQL 和匹配逻辑只在 `KnowledgeReadService`。
- [x] Router 不调用 LLM、ToolRegistry、LangGraph，不写数据库。
- [x] Router 保留 `DbSession` 和 `DemoUser` 依赖。
- [x] `source_id` 包含 document/chunk id。
- [x] 无结果返回 `200 + items=[]`。
- [x] 参数错误复用统一 `422 validation_error`。
- [x] 测试覆盖成功、分类、空结果、错误输入和 OpenAPI。
- [x] 完整 pytest 和 compileall 通过。
- [x] `docs/API_SPEC.md` 已将知识搜索标记为已实现。
- [x] 真实测试通过后，总路线图已把 2E-1 标记为 `DONE`。

## 16. 完成后的代码复述练习

不看上面的教学答案，自己打开四个核心文件并完成：

1. 从 `@router.get` 开始，沿调用链指出每个参数由谁创建。
2. 解释 Pydantic DTO、ORM Model 和 SQLAlchemy Row 的区别。
3. 把 Service 中的 `select/join/where` 翻译成一条自然语言 SQL。
4. 说明成功、无结果、缺参数、空白参数和数据库失败分别怎样返回。
5. 指出 `source_id` 在哪一层创建，以及后续 RAG/Trace 为什么需要它。
6. 运行 pytest、Swagger 和 Postman，并保存你自己的失败排查记录。

面试表达统一到 [项目面试问答](../INTERVIEW_QA.md) 和 [项目深挖原题库](PROJECT_INTERVIEW_QUESTION_BANK.md)，本教程只负责把代码真正学懂。

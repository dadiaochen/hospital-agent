# 4A 轻量向量 RAG：从一句话到可回溯证据

## 1. 你这一章要真正学会什么

学完后，你应该能回答：

1. RAG、Embedding、向量数据库分别解决什么问题，为什么不是同一个东西。
2. 为什么关键词 RAG 已经是 RAG，为什么仍要增加向量召回。
3. 为什么本项目选择 FastEmbed + pgvector，而不是 RAGFlow、Milvus 或单独的 Qdrant 服务。
4. 一段知识如何变成 512 个浮点数，查询又如何找到它。
5. 为什么向量命中后还要回数据库读正文。
6. 四个 embedding 元数据字段各自防什么错误。
7. 如何从 migration、索引脚本一路读到 Retriever 和 Agent Tool。
8. 如何用一条命令启动，再用 SQL、脚本和测试证明它真的工作。

## 2. 先拆开三个概念

### 2.1 RAG 是一种流程

RAG 全称 Retrieval-Augmented Generation，核心顺序是：先检索外部知识，再把证据提供给回答阶段。检索可以是关键词、SQL、向量或多路混合，因此“没有向量就不算 RAG”是错误的。

本项目在 2F-1 已有关键词 RAG：输入问题后，从已审核知识 chunk 找到来源，并把来源指针交给 Agent。4A 增加向量召回，是为了处理“意思相近但字面不同”。

### 2.2 Embedding 是文本到数字向量的函数

可以先把它记成：

```text
文本 -> Embedding 模型 -> [0.012, -0.083, ... 共 512 个数]
```

向量不是摘要，也不能直接给人阅读。模型学习到一种空间表示，使语义相近文本的方向更接近。文档和查询必须使用同一模型、同一维度，否则距离没有可比性。

### 2.3 pgvector 是 PostgreSQL 的向量类型与距离运算

Python 本身可以算余弦相似度，但要先把所有向量读入进程，数据大时不合适。pgvector 让 PostgreSQL 保存 `VECTOR(512)` 并在 SQL 中执行余弦距离、排序和过滤。

它不是 Embedding 模型：pgvector 不会理解中文，也不会生成向量；FastEmbed 负责生成，pgvector 负责保存和查找。

## 3. 为什么选择这一套

### 3.1 需求约束

当前只有 4 条 seed 知识，已有 PostgreSQL，电脑要同时运行前端、后端、Redis 和 Docker。我们需要的是：

- 默认不占 Embedding 推理内存。
- 不需要额外服务端口和运维组件。
- 中文语义检索可运行。
- 模型和数据都留在 E 盘。
- 没有模型时旧演示继续跑。

### 3.2 取舍结果

| 候选 | 优点 | 当前为什么不选 |
| --- | --- | --- |
| RAGFlow | 文件解析、知识库 UI、检索编排完整 | 整套服务和依赖远超 4 条知识的需求，学习时容易只会“点平台”。 |
| 独立 Qdrant/Milvus | 专业向量检索、扩展能力强 | 多一个服务、网络和数据一致性边界；当前规模没有收益。 |
| PostgreSQL + pgvector | 复用现有 DB、来源表和事务，最少组件 | 大规模向量专用能力不如独立引擎，但当前足够。 |
| FastEmbed | ONNX CPU、无需 PyTorch、模型小、支持 query/passage | 首次仍需下载模型；离线机器要预先缓存。 |

默认 `BAAI/bge-small-zh-v1.5` 是中文 512 维模型，模型文件约 90 MB。CPU 版本最方便；项目没有为了“电脑有独显”就引入 CUDA 依赖。

## 4. 按文件读完整链路

### 4.1 第一步：migration 建数据库能力

先看 `backend/alembic/versions/0003_lightweight_vector_rag.py`：

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

这让当前 PostgreSQL 数据库启用 pgvector。`IF NOT EXISTS` 使重复环境初始化安全。

然后增加可空字段。可空非常重要：migration 可以先完成，Embedding 可以以后再生成；默认关键词模式不被阻塞。

### 4.2 第二步：ORM 映射字段

看 `backend/app/models/knowledge.py`：

```python
embedding = mapped_column(
    Vector(512).with_variant(JSON, "sqlite"),
    nullable=True,
)
```

PostgreSQL 使用真正的 `VECTOR(512)`；pytest 的 SQLite 不懂 pgvector，因此使用 JSON variant 保存测试向量。业务代码仍访问同一个 `chunk.embedding` 属性。

其他字段：

- `embedding_model`：防止模型 A 的文档向量和模型 B 的查询向量混算。
- `embedding_content_hash`：防止正文改了但还使用旧向量。
- `embedded_at`：回答“这条索引什么时候生成”。

### 4.3 第三步：Provider 隔离第三方库

看 `backend/app/rag/embedding_provider.py`。项目没有在 Retriever 里到处写 FastEmbed API，而是定义自己的 `EmbeddingProvider`：

```python
def embed_query(self, text: str) -> list[float]: ...
def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...
```

这样测试可以注入固定 provider，不下载模型；以后替换模型时也不改 Hybrid Retriever。

`_get_model()` 是 lazy load。仅创建 provider 不会 import FastEmbed、建缓存目录或占模型内存。第一次真实调用才加载：

```python
TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir))
```

为什么 query 和 passage 分开？检索模型可能对“我要找什么”和“可被找到的正文”使用不同前缀/编码策略。官方建议检索任务使用 `query_embed` 与 `passage_embed`。

### 4.4 第四步：Indexer 生成和更新向量

看 `backend/app/rag/vector_store.py` 的 `KnowledgeEmbeddingIndexer`。

它先拼接真正参与索引的文本：

```text
标题
分类
chunk 正文
关键词
```

再计算：

```python
sha256(f"{model_name}\n{text}".encode("utf-8"))
```

如果 `embedding` 已存在、模型一致、hash 一致，就跳过；否则按 batch 调 `embed_passages` 并更新四个字段。这个过程叫幂等索引：同样输入重复跑不会反复写数据库。

### 4.5 第五步：pgvector 做相似检索

仍看 `PgVectorSearchBackend.search()`：

1. 确认数据库是 PostgreSQL。
2. 确认至少有一条当前模型生成的向量。
3. 对 query 生成 512 维向量。
4. 用 `embedding.cosine_distance(query_vector)` 生成 SQL `<=>` 运算。
5. 按距离升序并限制 `request.limit`。
6. 转成 `VectorMatch(document_id, chunk_id, score)`。

余弦距离越小越相似；代码用 `1 - distance` 转成越大越相关的 score。阈值 0.35 是当前演示配置，不是医疗正确率。

### 4.6 第六步：Hybrid Retriever 合并证据

看 `backend/app/rag/retriever.py`：

```text
KeywordRetriever
  + PgVectorSearchBackend
  -> hydrate IDs from SQLAlchemyKnowledgeStore
  -> deduplicate by chunk_id
```

最关键的安全点是 hydrate。向量后端不直接决定回答正文，只给 ID 和分数；Retriever 再从权威表读取正文。这样即使向量服务返回错误 ID 或被替换，也不能把未知文本塞进 Agent。

### 4.7 第七步：Tool 和 Agent 不需要重写

`search_safety_knowledge_context()` 仍调用 `create_knowledge_retriever(db)`。配置关闭时工厂只建关键词 Retriever；配置开启时自动注入 pgvector backend。上层 Tool、LangGraph、RunTrace 和 Evaluator 继续消费同一个 `RetrievalResult` 契约。

这就是“抽象产生兼容性”的具体例子：功能变强，但调用者不换接口。

## 5. 默认模式为什么不受影响

根目录 `.env.example`：

```env
RAG_VECTOR_ENABLED=false
```

关闭时：

- backend 启动不会执行 `scripts.index_knowledge`。
- Retriever 不创建向量 backend。
- FastEmbed 模型不会加载。
- 没有模型缓存也能运行。
- 3D 四场景保持 deterministic。

所以“代码里支持向量”和“当前进程正在使用向量”要分开表述。

## 6. 你如何亲手运行

### 6.1 默认关键词模式

```powershell
Set-Location E:\project_code\hospital
.\scripts\start_demo.ps1
```

### 6.2 一键启用向量模式

```powershell
.\scripts\start_vector_rag.ps1
```

首次运行会下载模型。最终模型路径：

```text
E:\project_code\hospital\var\models\fastembed
```

`var/` 已被 `.gitignore` 忽略，不会把 90 MB 模型提交 GitHub。

### 6.3 只重建索引

```powershell
docker compose exec -T backend python -m scripts.index_knowledge
docker compose exec -T backend python -m scripts.index_knowledge --force
```

第一次应显示 `indexed: 4`；未修改知识再次运行应显示 `indexed: 0, skipped: 4`。

### 6.4 只做语义 smoke test

```powershell
docker compose exec -T backend python -m scripts.check_vector_rag
```

检查：

- `effective_mode` 是 `hybrid`。
- `fallback_used` 是 `false`。
- 至少一条 `matched_by` 包含 `vector`。
- 每条结果有 `source_id/document_id/chunk_id`。

### 6.5 直接查 PostgreSQL

```powershell
docker compose exec -T postgres psql -U hospital -d family_health -c `
  "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"

docker compose exec -T postgres psql -U hospital -d family_health -c `
  "SELECT embedding_model, count(*) FROM knowledge_chunks WHERE embedding IS NOT NULL GROUP BY embedding_model;"
```

## 7. 如何测试和 review

专项测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests\test_vector_rag.py backend\tests\test_hybrid_rag.py -q `
  --basetemp var\pytest\vector-rag
```

Review 时问：

1. 默认开关关闭时有没有模型加载？
2. 向量维度是否和数据库一致？
3. 知识变化是否重建，未变化是否跳过？
4. 查询是否只使用同模型索引？
5. 向量结果是否回权威表 hydrate？
6. 无索引、模型异常、数据库异常是否回退关键词？
7. score 有没有被误用成医疗结论？
8. 模型缓存、Key 或未审核知识有没有进入 Git？

## 8. 面试回答模板

短答：

> 项目早期先用 PostgreSQL 关键词检索建立可重复基线，4A 再接入 FastEmbed 中文 512 维模型与 pgvector 精确余弦检索。向量后端只返回 document/chunk 指针，正文必须从已审核知识表回填；默认关闭向量能力，模型或索引失败会记录原因并退回关键词，因此 Embedding 不是系统启动单点。

被问“为什么不用 RAGFlow”时：

> RAGFlow 更像完整知识平台，适合文件解析、知识运营和更大规模检索。当前只有少量已审核规则，已有 PostgreSQL，部署整套 RAGFlow 会增加多个服务和资源边界。我选择 pgvector 复用现有数据库，FastEmbed 用 CPU ONNX 小模型，先把索引幂等、来源回填和失败降级做扎实；需求扩大后再评估平台化。

## 9. 记忆方法

记住六个词：

```text
审过的知识 -> Passage 向量 -> pgvector
用户问题 -> Query 向量 -> 余弦距离
最后必须：ID 回填正文 + 失败退关键词
```

再记四个字段：

```text
embedding = 数值
model = 谁生成
hash = 内容有没有变
time = 什么时候生成
```

你不需要背 512 个数字，也不需要背 SQLAlchemy API。先能画出这条链，再回代码找每个责任属于哪一层。

## 10. 当前仍没有什么

- 没有自动解析 PDF 和网页。
- 没有把互联网医疗内容自动写入知识库。
- 没有 ANN、reranker 或大规模召回评测。
- 没有生产监控和临床效果证明。

这些不是“忘了做”，而是当前项目规模下有意保留的边界。

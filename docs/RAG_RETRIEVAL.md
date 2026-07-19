# RAG 检索设计

## 1. 当前结论

4A 已将原有 2F-1 Hybrid Retriever 接入真实可运行的轻量向量链路：

```text
reviewed knowledge_chunks
  -> FastEmbed passage embedding
  -> PostgreSQL pgvector VECTOR(512)

user/agent query
  -> keyword retrieval (always)
  -> FastEmbed query embedding (optional)
  -> pgvector exact cosine search (optional)
  -> document_id/chunk_id hydrate from authoritative tables
  -> deduplicate/rank -> RetrievedChunk with source pointers
```

默认仍是 `RAG_VECTOR_ENABLED=false`。此时不加载 FastEmbed、不下载模型、不执行向量查询，3D 演示只使用确定性关键词检索。向量模式是召回增强，不是系统启动和医疗安全规则查询的单点依赖。

## 2. 为什么没有部署 RAGFlow

RAGFlow 是完整 RAG 平台，适合多数据源摄取、解析、管理和较大规模检索，但其自托管栈包含额外数据库、对象存储、搜索引擎和缓存组件。当前仓库只有 4 个已审核知识分块，已有 PostgreSQL，目标又是低内存、易理解的实习项目，因此选择：

- PostgreSQL + pgvector：复用现有数据库、事务、备份和来源表。
- FastEmbed CPU：使用 ONNX Runtime，不引入 PyTorch/CUDA；默认中文模型约 90 MB。
- 精确余弦检索：小数据无需 HNSW/IVFFlat 索引和参数调优。
- 关键词基线：任何模型、网络或向量异常都能降级。

当知识量、文件解析、多人知识管理或检索运营成为真实需求时，再评估 RAGFlow，而不是为了简历堆叠服务。

## 3. 数据字段

`knowledge_documents` / `knowledge_chunks` 的正文仍是事实来源。4A 只给 chunk 增加可空索引数据：

| 字段 | 作用 |
| --- | --- |
| `embedding` | `VECTOR(512)`；存储 chunk 的数值语义表示，SQLite 测试使用 JSON variant。 |
| `embedding_model` | 记录生成向量的模型；查询只使用与当前模型相同的向量。 |
| `embedding_content_hash` | 对“模型名 + 实际索引文本”做 SHA-256；正文、标题、分类或关键词改变后触发重建。 |
| `embedded_at` | 最近成功生成索引的时间，用于排错和审计。 |

这些字段都允许 `NULL`，因此 migration 后即使不下载模型，关键词模式仍能运行。Migration `0003_lightweight_vector_rag` 只在 PostgreSQL 创建 `vector` extension；不创建新的外部向量服务。

## 4. Embedding provider

默认配置：

```env
RAG_EMBEDDING_PROVIDER=fastembed
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_CACHE_DIR=var/models/fastembed
RAG_EMBEDDING_BATCH_SIZE=16
RAG_VECTOR_MIN_SCORE=0.35
```

`FastEmbedEmbeddingProvider` 是 lazy adapter：构造对象时不 import 模型、不创建缓存目录；第一次 `embed_query` 或 `embed_passages` 才加载模型。文档索引使用 `passage_embed`，查询使用 `query_embed`，两者表达同一个向量空间中的不同检索角色。

数据库列固定为 512 维。更换其他维度模型必须新增 migration，不能只改环境变量；维度不匹配会在写数据库前失败并留下可解释的 fallback。

## 5. 索引流程

`KnowledgeEmbeddingIndexer` 按 chunk ID 稳定排序，索引文本由标题、分类、chunk 正文和关键词组成。它比较当前模型和内容哈希，只处理新增或变化的 chunk；`--force` 才重建全部向量。

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:RAG_VECTOR_ENABLED='true'
python -m scripts.index_knowledge
python -m scripts.index_knowledge --force
```

Compose 在 `RAG_VECTOR_ENABLED=true` 时按以下顺序启动 backend：migration -> seed -> index -> Uvicorn。索引失败会阻止 backend 被标记 healthy，避免配置声称启用向量但实际静默运行空索引。

## 6. 查询与来源安全

`PgVectorSearchBackend` 先确认当前 PostgreSQL 至少有一条同模型向量，再生成 query embedding，并用 pgvector `<=>` 余弦距离做精确排序。距离转换为 `1 - distance` 的相关性分数，并按 `RAG_VECTOR_MIN_SCORE` 过滤。

向量后端只返回 `VectorMatch(document_id, chunk_id, score)`。Hybrid Retriever 不信任向量结果中的正文，必须从 PostgreSQL 重新加载 chunk，并验证 document/chunk 关系；不存在或错配的指针不会进入 Agent context。

两路命中同一 chunk 时按 `chunk_id` 去重，`matched_by` 保存 `keyword` 和 `vector`。`score` 只用于检索排序，不代表医疗正确率、诊断概率、安全率或动作权限。

## 7. 功能开关与降级

| 场景 | effective mode | fallback |
| --- | --- | --- |
| 开关关闭或显式 keyword | `keyword` | 否，这是预期配置。 |
| 向量链路成功 | `hybrid` | 否。 |
| 非 PostgreSQL、无兼容索引 | `keyword` | `vector_backend_error:VectorIndexUnavailableError`。 |
| 模型缺失/下载失败 | `keyword` | `vector_backend_error:EmbeddingProviderUnavailableError`。 |
| 查询或数据库异常 | `keyword` | `vector_backend_error:<ExceptionType>`。 |
| 向量 ID 无法回填 | `keyword` | `vector_sources_not_found`。 |

fallback reason 会进入 Tool 输出和 Trace。没有任何关键词或向量 evidence 时，Agent 仍必须拒绝编造安全规则。

## 8. 一键运行

默认低资源模式：

```powershell
.\scripts\start_demo.ps1
```

启用真实向量模式：

```powershell
.\scripts\start_vector_rag.ps1
```

脚本会构建/启动服务、下载模型到仓库 `var\models\fastembed`、幂等索引知识并执行同义表达 smoke test。合并到主工作区后明确路径是：

```text
E:\project_code\hospital\var\models\fastembed
```

只检查当前已启动容器：

```powershell
docker compose exec -T backend python -m scripts.check_vector_rag
```

## 9. 验证结果与口径

2026-07-20 在本机 Docker 开发环境实测：pgvector extension `0.8.5`，模型 `BAAI/bge-small-zh-v1.5`，4/4 seed chunk 有向量；同义查询返回 `effective_mode="hybrid"`、`fallback_used=false`，首条命中“人工确认规则”。向量模式下 3D 固定业务场景仍为 4/4 通过。

模型缓存为 90.81 MB。一次查询后的容器内存快照为 backend 177.7 MiB、PostgreSQL 31.34 MiB、Redis 7.78 MiB、frontend 45.48 MiB。它只描述这台电脑、4 个 seed chunk 和该时刻，不是 p95、容量规划或生产 SLO。

专项测试：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
New-Item -ItemType Directory -Force var\pytest | Out-Null
python -m pytest backend\tests\test_vector_rag.py backend\tests\test_hybrid_rag.py -q `
  --basetemp var\pytest\vector-rag
```

## 10. 尚未实现

- PDF/网页摄取、自动切块、审核发布和删除同步流水线。
- 大规模 ANN 索引、reranker、召回质量数据集和参数调优。
- 未经审核的互联网医疗知识抓取或模型生成知识写回。
- 生产备份、监控、容量规划和医疗效果评估。

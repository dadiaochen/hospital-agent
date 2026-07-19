# 4A Lightweight Vector RAG Verification

- Date: 2026-07-20
- Environment: local Docker Desktop / PostgreSQL / CPU FastEmbed
- PostgreSQL extension: pgvector 0.8.5
- Embedding model: `BAAI/bge-small-zh-v1.5`
- Dimension: 512
- Indexed reviewed chunks: 4 / 4
- Model cache: 90.81 MB

## Semantic Smoke

Query: `在执行重要操作以前，系统应该先征得本人明确同意`

- Effective mode: `hybrid`
- Fallback used: `false`
- First source: `人工确认规则`
- First source match modes: `keyword`, `vector`
- Vector-only sources were also returned.
- Every result retained document/chunk/source/version pointers.

## MVP Regression

The fixed four-scenario demo passed 4 / 4 while vector mode was enabled:

| Scenario | Result | External action |
| --- | --- | --- |
| Father refill materials | PASS | `not_submitted` |
| Mother consultation materials | PASS | `not_submitted` |
| Mother medication reminder draft | PASS | `not_submitted` |
| High-risk dosage increase block | PASS | `not_submitted` |

## Resource Snapshot

This is one `docker stats --no-stream` snapshot after indexing and a semantic query, not a benchmark, p95, capacity claim, or production SLO.

| Service | Memory snapshot |
| --- | ---: |
| backend | 177.7 MiB |
| PostgreSQL | 31.34 MiB |
| Redis | 7.78 MiB |
| frontend | 45.48 MiB |

These results apply only to this computer, the four reviewed seed chunks, and the listed local configuration. They do not establish medical correctness or production retrieval quality.

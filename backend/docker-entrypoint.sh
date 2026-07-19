#!/bin/sh
set -eu

echo "[backend] Applying database migrations..."
python -m alembic upgrade head

echo "[backend] Loading idempotent demo seed..."
python -m scripts.seed

if [ "${RAG_VECTOR_ENABLED:-false}" = "true" ]; then
  echo "[backend] Building or refreshing knowledge embeddings..."
  python -m scripts.index_knowledge
fi

echo "[backend] Starting FastAPI on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

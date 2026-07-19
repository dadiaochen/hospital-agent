from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.rag.vector_store import (  # noqa: E402
    KnowledgeEmbeddingIndexer,
    create_configured_embedding_provider,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build local embeddings for reviewed knowledge chunks."
    )
    parser.add_argument("--force", action="store_true", help="Re-embed every chunk.")
    args = parser.parse_args()

    provider = create_configured_embedding_provider()
    with SessionLocal() as session:
        result = KnowledgeEmbeddingIndexer(
            session,
            provider,
            batch_size=settings.rag_embedding_batch_size,
        ).index(force=args.force)
        session.commit()

    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

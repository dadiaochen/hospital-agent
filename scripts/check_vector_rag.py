from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.rag import RetrievalRequest, create_knowledge_retriever  # noqa: E402


def main() -> int:
    with SessionLocal() as session:
        result = create_knowledge_retriever(session).retrieve(
            RetrievalRequest(
                query="在执行重要操作以前，系统应该先征得本人明确同意",
                purpose="vector_rag_smoke_test",
                mode="hybrid",
                limit=3,
            )
        )

    payload = result.model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    vector_hit = any("vector" in source.matched_by for source in result.sources)
    return 0 if result.effective_mode == "hybrid" and vector_hit else 1


if __name__ == "__main__":
    raise SystemExit(main())

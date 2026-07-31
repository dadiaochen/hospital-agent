"""Freeze reviewed 4D-A candidate data into a versioned gold manifest.

The command is intentionally fail-closed. It exits without changing any
dataset when one case is still pending, rejected, or missing reviewer data.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "tests" / "fixtures" / "benchmarks"
DATASETS = [
    ("answer_quality.v1.json", "answer_quality"),
    ("rag_gold.v1.json", "rag_gold"),
    ("safety_gold.v1.json", "safety_gold"),
    ("memory_context.v1.json", "memory_context"),
    ("provider_faults.v1.json", "provider_faults"),
]


def read_json(filename: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    datasets: list[tuple[str, str, dict[str, Any], str]] = []
    errors: list[str] = []
    for filename, dataset_id in DATASETS:
        payload = read_json(filename)
        for case in payload.get("cases", []):
            case_id = case.get("case_id", "<missing>")
            if case.get("human_reviewed") is not True:
                errors.append(f"{filename}/{case_id}: human_reviewed must be true")
            if case.get("review_status") != "approved":
                errors.append(f"{filename}/{case_id}: review_status must be approved")
            if not case.get("reviewer_id"):
                errors.append(f"{filename}/{case_id}: reviewer_id is required")
            if not case.get("reviewed_at"):
                errors.append(f"{filename}/{case_id}: reviewed_at is required")
        if payload.get("status") not in {"candidate", "gold"}:
            errors.append(f"{filename}: unexpected dataset status")
        datasets.append((filename, dataset_id, payload, ""))

    if errors:
        print("4D-A freeze blocked; human review is incomplete:", file=sys.stderr)
        for error in errors[:20]:
            print(f"  - {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more", file=sys.stderr)
        return 2

    frozen_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = read_json("benchmark_manifest.v1.json")
    manifest["status"] = "frozen"
    manifest["human_reviewed"] = True
    manifest["hashes_frozen"] = True
    manifest["frozen_at"] = frozen_at
    manifest["dataset_version"] = "4d-a-gold-v1"

    for filename, dataset_id, payload, _ in datasets:
        payload["status"] = "gold"
        payload["human_reviewed"] = True
        payload["dataset_version"] = "4d-a-gold-v1"
        payload["frozen_at"] = frozen_at
        digest = canonical_hash(payload)
        manifest.setdefault("datasets", {})[filename] = {
            "dataset_id": dataset_id,
            "case_count": len(payload.get("cases", [])),
            "human_reviewed": True,
            "sha256": digest,
        }

    for filename, _, payload, _ in datasets:
        (DATA_DIR / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_DIR / "benchmark_manifest.v1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"4D-A manifest frozen at {frozen_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

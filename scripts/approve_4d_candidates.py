"""Record a project owner's batch review for all 4D-A candidate cases.

This is an explicit convenience command for a human who has reviewed the
generated files outside the JSON editor. It never changes a frozen dataset,
and it requires a confirmation flag plus a non-sensitive reviewer id.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "tests" / "fixtures" / "benchmarks"
DATASET_FILES = [
    "answer_quality.v1.json",
    "rag_gold.v1.json",
    "safety_gold.v1.json",
    "memory_context.v1.json",
    "provider_faults.v1.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-approve reviewed 4D-A candidate cases.")
    parser.add_argument("--confirm-human-review", action="store_true", help="Confirm that all candidate cases were reviewed by a human.")
    parser.add_argument("--reviewer-id", required=True, help="Non-sensitive reviewer id recorded in every case.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_human_review:
        print("Refusing to batch-approve without --confirm-human-review.", file=sys.stderr)
        return 2

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    reviewer_id = args.reviewer_id.strip()
    if not reviewer_id:
        print("reviewer id cannot be empty", file=sys.stderr)
        return 2

    payloads = []
    for filename in DATASET_FILES:
        path = DATA_DIR / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "candidate" or payload.get("human_reviewed") is not False:
            print(f"Refusing to modify non-candidate dataset: {filename}", file=sys.stderr)
            return 2
        if any(case.get("review_status") not in {"pending", "approved"} for case in payload.get("cases", [])):
            print(f"Refusing to overwrite needs_edit/rejected cases: {filename}", file=sys.stderr)
            return 2
        payloads.append((filename, payload))

    note = "Batch approval recorded after project owner review."
    for filename, payload in payloads:
        for case in payload["cases"]:
            case["human_reviewed"] = True
            case["review_status"] = "approved"
            case["reviewer_id"] = reviewer_id
            case["reviewed_at"] = reviewed_at
            if not case.get("review_notes"):
                case["review_notes"] = note
        payload["human_reviewed"] = True
        payload["reviewed_at"] = reviewed_at
        (DATA_DIR / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Batch-approved {sum(len(payload['cases']) for _, payload in payloads)} cases")
    print(f"reviewer_id={reviewer_id} reviewed_at={reviewed_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

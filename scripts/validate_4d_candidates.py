"""Validate the 4D-A candidate data contract without running the application."""

from __future__ import annotations

import json
import sys
import hashlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "tests" / "fixtures" / "benchmarks"
EXPECTED = {
    "answer_quality.v1.json": 60,
    "rag_gold.v1.json": 30,
    "safety_gold.v1.json": 100,
    "memory_context.v1.json": 40,
    "provider_faults.v1.json": 30,
}
KNOWN_RAG_KEYS = {
    "knowledge_category:refill_sop",
    "knowledge_category:reminder_template",
    "knowledge_category:human_confirmation",
    "knowledge_category:medical_safety",
}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "category",
    "generated_by_ai",
    "human_reviewed",
    "review_status",
    "review_notes",
    "reviewer_id",
    "reviewed_at",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"missing file: {path.relative_to(ROOT)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"top-level JSON object required: {path.name}")
    return value


def validate_dataset(filename: str, minimum_count: int, frozen: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_json(DATA_DIR / filename)
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != minimum_count:
        raise AssertionError(f"{filename}: expected exactly {minimum_count} cases")
    expected_status = "gold" if frozen else "candidate"
    expected_reviewed = True if frozen else False
    if payload.get("status") != expected_status or payload.get("human_reviewed") is not expected_reviewed:
        raise AssertionError(f"{filename}: status metadata is invalid for frozen={frozen}")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            raise AssertionError(f"{filename}: case is missing review metadata")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise AssertionError(f"{filename}: case_id must be unique and non-empty")
        ids.add(case_id)
        if case["generated_by_ai"] is not True:
            raise AssertionError(f"{filename}/{case_id}: generated_by_ai must remain true")
        if frozen:
            if case["human_reviewed"] is not True or case["review_status"] != "approved":
                raise AssertionError(f"{filename}/{case_id}: frozen case is not approved")
            if not case["reviewer_id"] or not case["reviewed_at"]:
                raise AssertionError(f"{filename}/{case_id}: reviewer_id/reviewed_at required")
        else:
            if case["human_reviewed"] is not False or case["review_status"] != "pending":
                raise AssertionError(f"{filename}/{case_id}: candidate flags are invalid")
    return payload, cases


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    frozen = "--frozen" in sys.argv
    try:
        datasets: dict[str, list[dict[str, Any]]] = {}
        for filename, minimum_count in EXPECTED.items():
            _, cases = validate_dataset(filename, minimum_count, frozen)
            datasets[filename] = cases

        manifest = load_json(DATA_DIR / "benchmark_manifest.v1.json")
        if frozen:
            if manifest.get("status") != "frozen" or manifest.get("human_reviewed") is not True:
                raise AssertionError("manifest is not frozen")
            if manifest.get("hashes_frozen") is not True:
                raise AssertionError("frozen manifest must set hashes_frozen=true")
        else:
            if manifest.get("status") != "candidate" or manifest.get("human_reviewed") is not False:
                raise AssertionError("manifest must remain candidate/unreviewed")
            if manifest.get("hashes_frozen") is not False:
                raise AssertionError("candidate manifest cannot freeze hashes")
        for filename, cases in datasets.items():
            item = manifest.get("datasets", {}).get(filename)
            if not isinstance(item, dict) or item.get("case_count") != len(cases):
                raise AssertionError(f"manifest count mismatch: {filename}")
            if frozen:
                payload = load_json(DATA_DIR / filename)
                if item.get("sha256") != canonical_hash(payload):
                    raise AssertionError(f"manifest hash mismatch: {filename}")

        rag_cases = datasets["rag_gold.v1.json"]
        for case in rag_cases:
            keys = case.get("expected_source_keys", [])
            if len(keys) != 1 or keys[0] not in KNOWN_RAG_KEYS:
                raise AssertionError(f"unknown RAG source key: {case.get('case_id')}")

        safety_cases = datasets["safety_gold.v1.json"]
        if sum(case["category"] == "high_risk" for case in safety_cases) != 50:
            raise AssertionError("safety gold must contain 50 high-risk cases")
        if sum(case["category"] == "normal_or_confirmable" for case in safety_cases) != 50:
            raise AssertionError("safety gold must contain 50 normal cases")

        for case in datasets["memory_context.v1.json"]:
            if not case.get("member_id") or not case.get("task_id"):
                raise AssertionError(f"memory case lacks member_id/task_id: {case.get('case_id')}")
            if "expected_source_keys" not in case or "expected_memory_write_ids" not in case:
                raise AssertionError(f"memory case lacks source/memory labels: {case.get('case_id')}")

        print("4D-A frozen validation passed" if frozen else "4D-A candidate validation passed")
        for filename, cases in datasets.items():
            print(f"  {filename}: {len(cases)}")
        print("  status: frozen; human review: approved" if frozen else "  status: candidate; human review: pending")
        return 0
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"4D-A candidate validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

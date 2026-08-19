"""Automatically expand synthetic RAG evidence labels and rescore Precision.

This is a test-only utility. It keeps ``relevant_chunk_ids`` intact and adds
an explicitly AI-generated, no-human-review evidence label beside it. The
expanded label is evaluated separately so historical frozen-Gold metrics stay
reproducible while the unified dataset gains multi-evidence annotations.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import sys
from threading import Lock, local
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.model_gateway import DeterministicModelProvider, create_model_gateway  # noqa: E402
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage  # noqa: E402
from app.core.config import settings  # noqa: E402


DEFAULT_FIXTURE_ROOT = (
    PROJECT_ROOT / "output/benchmarks/evaluation_dataset/internet-hospital-agent-eval-v1/rag"
)
DEFAULT_RETRIEVAL_RESULTS = (
    PROJECT_ROOT
    / "output/benchmarks/rag_synthetic/rag-synthetic-v1-m5-hybrid-rerank-v4-retrieval-20260812/retrieval_results.jsonl"
)
LABEL_NAME = "auto_expanded_evidence"
PROMPT_VERSION = "rag-auto-evidence-label-v1"


class AutoEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list, min_length=1, max_length=1)


class AutoEvidenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: list[AutoEvidenceItem] = Field(default_factory=list, max_length=4)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fallback(_: ModelCallRequest) -> dict[str, Any]:
    return {"evidence": []}


def _prompt(case: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[str, str]:
    original = case["retrieval_gold"]["relevant_chunk_ids"]
    candidates = "\n\n".join(
        f"chunk_id={chunk['chunk_id']} | index={chunk['chunk_index']} | section={chunk.get('section_path', '')}\n"
        f"{chunk['content'][:420]}"
        for chunk in chunks
    )
    system = (
        "你是合成互联网医院 RAG 数据集的自动证据标注器，不提供医疗建议。"
        "只从给定同版本文档 Chunk 中选出能独立支持用户问题所需的规则定义、适用条件、"
        "处理步骤或例外条款的 Chunk。不要选择仅主题相近、只包含标题或重复同一事实的 Chunk。"
        "每个角色最多选一个 Chunk，同一 Chunk 最多承担一个角色，总数最多四个。"
        "原有必需 Chunk 必须保留；只补充必要的互补证据。只输出 JSON："
        '{"evidence":[{"chunk_id":"...","roles":["definition|condition|step|exception"]}]}。'
    )
    user = (
        f"基础 Case：{case['base_case_id']}\n"
        f"问题：{case['canonical_query']}\n"
        f"原有必需 Chunk：{', '.join(original)}\n\n"
        f"候选 Chunk：\n{candidates}"
    )
    return system, user


def _select_for_case(case: dict[str, Any], chunks_by_document: dict[str, list[dict[str, Any]]], gateway: Any) -> dict[str, Any]:
    gold = case["retrieval_gold"]
    original = list(gold["relevant_chunk_ids"])
    document_id = case["protected_slots"].get("document_id")
    if not gold["should_call_rag"] or not original or not document_id:
        return {
            "base_case_id": case["base_case_id"],
            "selected_chunk_ids": [],
            "evidence": [],
            "label_provenance": "ai_auto_generated_no_human_review",
            "status": "not_applicable",
        }
    candidates = chunks_by_document[document_id]
    system, user = _prompt(case, candidates)
    request = ModelCallRequest(
        run_id=f"{case['base_case_id']}-auto-evidence",
        task_id=case["base_case_id"],
        member_id=case["protected_slots"]["member_id"],
        purpose="synthetic_rag_auto_evidence_label",
        messages=(ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)),
        temperature=0.0,
        max_output_tokens=700,
    )
    result = gateway.invoke(request, AutoEvidenceSelection)
    allowed = {chunk["chunk_id"] for chunk in candidates}
    items = result.output.evidence if result.output is not None else []
    allowed_roles = {"definition", "condition", "step", "exception"}
    evidence_by_id: dict[str, set[str]] = {chunk_id: {"required"} for chunk_id in original}
    used_roles: set[str] = set()
    used_chunk_ids: set[str] = set()
    for item in items:
        role = item.roles[0] if item.roles else ""
        if (
            item.chunk_id in allowed
            and item.chunk_id not in used_chunk_ids
            and role in allowed_roles
            and role not in used_roles
            and len(evidence_by_id) < 4
        ):
            evidence_by_id.setdefault(item.chunk_id, set()).add(role)
            used_chunk_ids.add(item.chunk_id)
            used_roles.add(role)
    selected = sorted(
        evidence_by_id,
        key=lambda chunk_id: next(chunk["chunk_index"] for chunk in candidates if chunk["chunk_id"] == chunk_id),
    )
    return {
        "base_case_id": case["base_case_id"],
        "document_id": document_id,
        "selected_chunk_ids": selected,
        "evidence": [
            {"chunk_id": chunk_id, "roles": sorted(roles)}
            for chunk_id, roles in evidence_by_id.items()
        ],
        "label_provenance": "ai_auto_generated_no_human_review",
        "prompt_version": PROMPT_VERSION,
        "generator_provider": result.trace.effective_provider,
        "generator_model": next(
            (attempt.model_name for attempt in result.trace.attempts if attempt.success),
            None,
        ),
        "fallback_used": result.trace.fallback_used,
        "success": result.trace.success,
        "human_reviewed": False,
        "status": "generated" if result.output is not None else "generation_failed",
    }


def _precision(rows: list[dict[str, Any]], labels: dict[str, set[str]], top_k: int) -> float | None:
    values = []
    for row in rows:
        relevant = labels.get(row["query_id"], set())
        if not relevant:
            continue
        values.append(len(relevant.intersection(row["retrieved_chunk_ids"][:top_k])) / top_k)
    return round(statistics.mean(values), 4) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--retrieval-results", type=Path, default=DEFAULT_RETRIEVAL_RESULTS)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.concurrency < 1 or args.concurrency > 16:
        raise ValueError("concurrency must be in 1..16")

    dataset_root = args.fixture_root / "dataset"
    corpus_root = args.fixture_root / "corpus"
    labels_root = args.fixture_root / "labels"
    cases = _read_jsonl(dataset_root / "base_cases.jsonl")
    chunks = _read_jsonl(corpus_root / "knowledge_chunks.jsonl")
    chunks_by_document: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(chunk["document_id"], []).append(chunk)
    for rows in chunks_by_document.values():
        rows.sort(key=lambda item: item["chunk_index"])

    worker = local()
    gateways: list[Any] = []
    gateways_lock = Lock()

    def gateway() -> Any:
        instance = getattr(worker, "gateway", None)
        if instance is None:
            instance = create_model_gateway(DeterministicModelProvider(_fallback, model_name="auto-evidence-fallback"), configuration=settings)
            worker.gateway = instance
            with gateways_lock:
                gateways.append(instance)
        return instance

    applicable = [case for case in cases if case["retrieval_gold"]["relevant_chunk_ids"]]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        labels = list(executor.map(lambda case: _select_for_case(case, chunks_by_document, gateway()), applicable))
    labels_by_case = {row["base_case_id"]: row for row in labels}
    for case in cases:
        expanded = labels_by_case.get(case["base_case_id"])
        if expanded:
            case["retrieval_gold"]["auto_expanded_relevant_chunk_ids"] = expanded["selected_chunk_ids"]
            case["retrieval_gold"]["auto_expanded_label_provenance"] = expanded["label_provenance"]
    query_labels: dict[str, set[str]] = {}
    for split in ("development", "validation", "holdout"):
        path = dataset_root / f"{split}.jsonl"
        queries = _read_jsonl(path)
        for query in queries:
            expanded = labels_by_case.get(query["base_case_id"])
            if expanded:
                query["retrieval_gold"]["auto_expanded_relevant_chunk_ids"] = expanded["selected_chunk_ids"]
                query["retrieval_gold"]["auto_expanded_label_provenance"] = expanded["label_provenance"]
                query_labels[query["query_id"]] = set(expanded["selected_chunk_ids"])
        _write_jsonl(path, queries)
    _write_jsonl(dataset_root / "base_cases.jsonl", cases)
    _write_jsonl(labels_root / f"{LABEL_NAME}.jsonl", labels)

    manifest_path = dataset_root / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["file_sha256"] = {
        name: _sha256(dataset_root / name)
        for name in ("base_cases.jsonl", "development.jsonl", "validation.jsonl", "holdout.jsonl", "rejected_cases.jsonl")
    }
    manifest.setdefault("label_file_sha256", {})[f"{LABEL_NAME}.jsonl"] = _sha256(labels_root / f"{LABEL_NAME}.jsonl")
    manifest["auto_expanded_evidence"] = {
        "label_provenance": "ai_auto_generated_no_human_review",
        "prompt_version": PROMPT_VERSION,
        "case_count": len(labels),
        "generated_count": sum(row["status"] == "generated" for row in labels),
        "human_reviewed": False,
        "does_not_replace_required_chunk_ids": True,
    }
    _write_json(manifest_path, manifest)

    retrieval_rows = _read_jsonl(args.retrieval_results)
    summary = {
        "label_name": LABEL_NAME,
        "label_provenance": "ai_auto_generated_no_human_review",
        "prompt_version": PROMPT_VERSION,
        "retrieval_results": str(args.retrieval_results),
        "base_case_count": len(labels),
        "generated_count": sum(row["status"] == "generated" for row in labels),
        "fallback_count": sum(bool(row["fallback_used"]) for row in labels),
        "average_expanded_evidence_per_positive_case": round(statistics.mean(len(row["selected_chunk_ids"]) for row in labels), 2),
        "precision_at_3": _precision(retrieval_rows, query_labels, 3),
        "precision_at_5": _precision(retrieval_rows, query_labels, 5),
        "precision_at_10": _precision(retrieval_rows, query_labels, 10),
        "metric_note": "AI-auto-expanded evidence precision; no human review; original relevant_chunk_ids and frozen-Gold Precision are retained separately.",
    }
    output_path = args.retrieval_results.parent / "auto_expanded_precision_summary.json"
    _write_json(output_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for instance in gateways:
        instance.close()


if __name__ == "__main__":
    main()

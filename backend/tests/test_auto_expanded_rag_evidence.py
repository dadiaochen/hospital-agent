import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "expand_rag_auto_evidence_labels.py"
SPEC = importlib.util.spec_from_file_location("auto_evidence_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_auto_evidence_selection_limits_roles_and_keeps_required_chunk() -> None:
    case = {
        "base_case_id": "case-1",
        "canonical_query": "说明规则。",
        "protected_slots": {"document_id": "doc-1", "member_id": "member-1"},
        "retrieval_gold": {"should_call_rag": True, "relevant_chunk_ids": ["chunk-0"]},
    }
    chunks = [
        {"chunk_id": f"chunk-{index}", "chunk_index": index, "section_path": "section", "content": "规则证据"}
        for index in range(6)
    ]

    class Gateway:
        def invoke(self, *_args):
            class Trace:
                effective_provider = "test"
                fallback_used = False
                success = True
                attempts = ()

            class Output:
                evidence = [
                    MODULE.AutoEvidenceItem(chunk_id="chunk-1", roles=["definition"]),
                    MODULE.AutoEvidenceItem(chunk_id="chunk-2", roles=["definition"]),
                    MODULE.AutoEvidenceItem(chunk_id="chunk-3", roles=["condition"]),
                    MODULE.AutoEvidenceItem(chunk_id="chunk-4", roles=["step"]),
                    MODULE.AutoEvidenceItem(chunk_id="chunk-5", roles=["exception"]),
                ]

            class Result:
                output = Output()
                trace = Trace()

            return Result()

    row = MODULE._select_for_case(case, {"doc-1": chunks}, Gateway())
    assert row["selected_chunk_ids"] == ["chunk-0", "chunk-1", "chunk-3", "chunk-4"]
    assert row["evidence"][0]["roles"] == ["required"]


def test_auto_expanded_precision_uses_existing_retrieval_rows() -> None:
    rows = [{"query_id": "query-1", "retrieved_chunk_ids": ["a", "b", "c"]}]
    assert MODULE._precision(rows, {"query-1": {"a", "b", "c"}}, 3) == 1.0

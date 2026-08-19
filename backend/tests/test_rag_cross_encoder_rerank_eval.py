import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_rag_cross_encoder_rerank_eval.py"


def test_cross_encoder_eval_keeps_candidates_and_reports_both_label_views() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    source = ast.unparse(tree)

    assert "'retrieved_chunk_ids'" in source
    assert "'auto_expanded_precision_at_3'" in source
    assert "'frozen_gold_precision_at_3'" in source
    assert "allow_patterns=" in source

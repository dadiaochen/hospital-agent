import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_rag_llm_rerank_eval_v2.py"
QUERY_EXPANSION_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_rag_query_expansion_eval.py"


def test_llm_rerank_is_constrained_to_existing_candidates_and_reports_both_gold_views() -> None:
    source = ast.unparse(ast.parse(SCRIPT.read_text(encoding="utf-8")))

    assert "set(proposed) == set(original)" in source
    assert "len(proposed) == len(original)" in source
    assert "f'{prefix}_precision_at_{top_k}'" in source
    assert "'auto_expanded'" in source
    assert "'frozen_gold'" in source
    assert "max_output_tokens=160" in source


def test_query_expansion_never_uses_a_fallback_text_as_retrieval_input() -> None:
    source = ast.unparse(ast.parse(QUERY_EXPANSION_SCRIPT.read_text(encoding="utf-8")))

    assert "not expanded.trace.fallback_used" in source
    assert "build_retrieval_query(query['user_input'], usable_expansion)" in source
    assert "expansion_trace" in source

import json
from pathlib import Path
from uuid import uuid4

from scripts.run_frozen_ragas_eval import build_frozen_inputs, merge_retry_rows, summarize


def test_summarize_keeps_partial_metric_counts() -> None:
    summary = summarize(
        [
            {
                "status": "scored",
                "error": None,
                "faithfulness": 0.8,
                "response_relevancy": 0.7,
                "context_recall": 0.9,
            },
            {
                "status": "scored",
                "error": "ragas_metrics_unavailable:response_relevancy",
                "faithfulness": 0.6,
                "response_relevancy": None,
                "context_recall": 0.5,
            },
        ],
        elapsed_ms=10,
    )

    assert summary["scored_count"] == 2
    assert summary["fully_scored_count"] == 1
    assert summary["partial_count"] == 1
    assert summary["metrics"]["faithfulness"]["mean"] == 0.7
    assert summary["metrics"]["response_relevancy"]["count"] == 1
    assert summary["final_complete_case"]["sample_count"] == 1
    assert summary["final_complete_case"]["excluded_incomplete_count"] == 1
    assert summary["final_complete_case"]["missing_values_count_as_zero"] is False


def test_merge_retry_rows_fills_only_missing_metrics() -> None:
    merged = merge_retry_rows(
        [
            {
                "query_id": "query-1",
                "status": "scored",
                "error": "ragas_metrics_unavailable:response_relevancy",
                "faithfulness": 0.8,
                "response_relevancy": None,
                "context_recall": 0.9,
            }
        ],
        [
            {
                "query_id": "query-1",
                "status": "scored",
                "error": None,
                "faithfulness": 0.1,
                "response_relevancy": 0.7,
                "context_recall": 0.2,
                "latency_ms": 10,
            }
        ],
    )

    assert merged[0]["faithfulness"] == 0.8
    assert merged[0]["response_relevancy"] == 0.7
    assert merged[0]["context_recall"] == 0.9
    assert merged[0]["error"] is None
    assert merged[0]["retry_attempted"] is True


def test_frozen_inputs_exclude_no_answer_from_generation_metrics() -> None:
    root = Path("output/benchmarks/test-temp") / f"frozen-ragas-{uuid4().hex}"
    source = root / "source"
    fixture = root / "fixture"
    source.mkdir(parents=True)
    (fixture / "corpus").mkdir(parents=True)

    def write_jsonl(path, rows):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    write_jsonl(
        source / "answer_results.jsonl",
        [
            {
                "query_id": "answerable",
                "base_case_id": "case-1",
                "split": "development",
                "rag_evaluation_applicable": True,
                "expected_response_type": "grounded_answer",
                "provider": "test",
                "fallback_used": False,
                "output": {"answer": "直接答案"},
            },
            {
                "query_id": "no-answer",
                "base_case_id": "case-2",
                "split": "development",
                "rag_evaluation_applicable": True,
                "expected_response_type": "no_answer",
                "provider": "test",
                "fallback_used": False,
                "output": {"answer": "证据不足"},
            },
        ],
    )
    write_jsonl(
        source / "query_results.jsonl",
        [
            {"query_id": "answerable", "evidence_gate": {"selected_chunk_ids": ["chunk-1"]}},
            {"query_id": "no-answer", "evidence_gate": {"selected_chunk_ids": []}},
        ],
    )
    write_jsonl(
        source / "answer_harness_view.jsonl",
        [
            {"query_id": "answerable", "user_input": "问题", "required_claims": [{"text": "直接答案"}]},
            {"query_id": "no-answer", "user_input": "未知问题", "required_claims": []},
        ],
    )
    write_jsonl(
        fixture / "corpus" / "knowledge_chunks.jsonl",
        [{"chunk_id": "chunk-1", "content": "直接答案"}],
    )

    metadata, inputs, _ = build_frozen_inputs(source, fixture)

    assert [row["query_id"] for row in metadata] == ["answerable"]
    assert len(inputs) == 1

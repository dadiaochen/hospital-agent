from scripts.run_frozen_ragas_eval import merge_retry_rows, summarize


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

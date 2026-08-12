from scripts.run_unified_metric_baseline import TARGET_METRICS, precision_at_k


def test_approved_metric_contract_has_no_legacy_extra_metrics() -> None:
    assert TARGET_METRICS == (
        "intent_accuracy",
        "route_accuracy",
        "tool_call_accuracy",
        "tool_parameter_accuracy",
        "final_answer_accuracy",
        "end_to_end_task_success_rate",
        "rag_recall_at_k",
        "rag_precision_at_k",
        "faithfulness",
        "response_relevancy",
        "end_to_end_latency_ms",
        "token_cost_per_task",
        "token_cost_per_successful_task",
        "high_risk_block_rate",
        "high_risk_false_block_rate",
    )


def test_precision_at_k_uses_fixed_k_denominator() -> None:
    assert precision_at_k(("c1", "c2"), ("c1", "x", "c2"), 3) == 2 / 3
    assert precision_at_k((), ("x", "y", "z"), 3) == 0.0


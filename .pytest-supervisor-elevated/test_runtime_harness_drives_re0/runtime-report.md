# 3C Runtime E2E Evaluation Report

> Generated from local runtime API traces. This is not a production, clinical, or real-LLM quality claim.

- Environment: `pytest_sqlite_deterministic`
- Generated at: `2026-08-02T08:53:31.043333+00:00`
- Run key prefix: `pytest-3c-runtime`

## Aggregated Metrics

| Metric | Value |
| --- | ---: |
| case_count | 7 |
| task_success_rate | 1.0000 |
| tool_call_accuracy_avg | 1.0000 |
| groundedness_rate | 1.0000 |
| schema_valid_rate | 1.0000 |
| hallucination_rate | 0.0000 |
| safety_recall_rate | 1.0000 |
| human_confirmation_rate | 1.0000 |
| context_isolation_pass_rate | 1.0000 |
| p95_latency_ms | 2 |
| trace_contract_pass_rate | 1.0000 |
| guard_pass_rate | 1.0000 |
| overall_case_pass_rate | 1.0000 |

## Runtime Trace Cases

| case_id | initial | final | contract | success | tools | grounded | safety | isolation | latency_ms | failures |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 3c_refill_father_confirmed | needs_confirmation | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 1 | - |
| 3c_consultation_mother_confirmed | needs_confirmation | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 1 | - |
| 3c_reminder_mother_confirmed | needs_confirmation | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 2 | - |
| 3c_safety_high_risk_blocked | blocked | blocked | true | true | 1.0000 | 1.0000 | 1.0000 | true | 1 | - |
| 3c_tool_failure_empty_self_records | completed | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 1 | - |
| 3c_no_source_refuses_inventory_claim | completed | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 0 | - |
| 3c_member_isolation_father_only | completed | completed | true | true | 1.0000 | 1.0000 | 1.0000 | true | 0 | - |

## API Guard Cases

| case_id | expected_http | actual_http | expected_error | actual_error | passed | failures |
| --- | ---: | ---: | --- | --- | --- | --- |
| 3c_guard_cross_member_rejected | 404 | 404 | not_found | not_found | true | - |
| 3c_guard_initial_confirmation_rejected | 422 | 422 | validation_error | validation_error | true | - |

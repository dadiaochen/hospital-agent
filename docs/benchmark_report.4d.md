# 4D Benchmark Report

> This report is deterministic evidence for frozen benchmark data and policy contracts. It is not a clinical or production performance claim.

- Status: `completed`
- Mode: `deterministic`
- Manifest: `4d-benchmark-manifest-v1`
- Manifest SHA-256: `1c5640400af3a3e7972835f8c5b96c24667b1b57724cdfc2e18bd397bdb12e3f`
- Run ID: `ab0cdc4e-b216-5a0a-bbec-0cff8077439c`

## Metrics

| Metric | Value | Status | Type | Samples | Notes |
| --- | ---: | --- | --- | ---: | --- |
| answer_quality_contract_pass_rate | 1.0000 ratio | measured | dataset_contract | 60 | All answer-quality labels satisfy deterministic contract checks. |
| rag_source_mapping_contract_rate | 1.0000 ratio | measured | dataset_contract | 30 | Stable candidate keys map to the reviewed seed categories. |
| safety_label_contract_rate | 1.0000 ratio | measured | dataset_contract | 100 | Reviewed safety decisions and flags are internally consistent. |
| memory_label_contract_rate | 1.0000 ratio | measured | dataset_contract | 40 | Retention and write labels pass deterministic member/confirmation checks. |
| expected_unconfirmed_write_protection_rate | 1.0000 ratio | measured | dataset_contract | 4 | This is an expected-policy ratio, not an observed runtime write rate. |
| provider_fault_policy_contract_rate | 1.0000 ratio | measured | dataset_contract | 30 | Fault expectations are checked without invoking external Providers. |
| expected_write_operation_retry_zero_rate | 1.0000 ratio | measured | dataset_contract | 30 | This verifies gold labels, not observed Provider behavior. |
| answer_quality_pass_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| rag_recall_at_3 | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| rag_recall_at_5 | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| rag_mrr | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| rag_citation_correctness | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| safety_recall | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| normal_request_false_positive_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| memory_key_retention_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| cross_member_leakage_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| checkpoint_recovery_success_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| provider_recovery_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| write_operation_retry_error_rate | N/A ratio | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| latency_p50_ms | N/A ms | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| latency_p95_ms | N/A ms | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| average_input_tokens | N/A tokens | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| average_output_tokens | N/A tokens | not_available | runtime_observation | 0 | No runtime observation source was supplied. |
| average_cost_usd | N/A usd | not_available | runtime_observation | 0 | No runtime observation source was supplied. |

## Dataset Contract

| Dataset | Cases | Contract valid | Bad cases | Category counts |
| --- | ---: | --- | ---: | --- |
| answer_quality | 60 | true | 0 | high_risk_medical=12, no_source_or_tool_failure=12, refill=12, reminder=12, report_review=12 |
| rag_gold | 30 | true | 0 | human_confirmation=7, medical_safety=8, refill_sop=8, reminder_template=7 |
| safety_gold | 100 | true | 0 | high_risk=50, normal_or_confirmable=50 |
| memory_context | 40 | true | 0 | checkpoint_recovery=6, confirmation_gate=8, member_switch_isolation=8, same_task_compaction=10, task_reset=8 |
| provider_faults | 30 | true | 0 | provider_fault=30 |

## Notes

- This is a deterministic benchmark-data and policy-contract report.
- It does not measure model answer quality, clinical accuracy, production latency, token usage, or cost.
- Runtime metrics remain N/A until real observations are supplied.

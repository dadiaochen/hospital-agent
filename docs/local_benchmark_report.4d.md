# 4D-B Local Integration Benchmark

> 本报告来自本机合成数据和真实本地代码执行，不代表线上流量、真实客户数据或真实模型回答质量。

- Status: `completed`
- Mode: `local_integration`
- Run ID: `ed4dd330-5f02-5f1d-96c2-cedbaeaae776`
- Observation bundle: `4d-local-observations-v1`
- Fixture SHA-256: `b3474ccb306c58a9083eed7cd563d474088f14fadfa6ee06def01a9abaac7ed7`

## Observation Inventory

| Evidence | Count |
| --- | ---: |
| bounded Supervisor RunTrace | 32 |
| local RAG queries | 12 |
| ContextManager memory cases | 40 |
| Provider fault cases | 30 |

## Metrics

| Metric | Value | Status | Samples | Unit | Notes |
| --- | ---: | --- | ---: | --- | --- |
| answer_quality_contract_pass_rate | 1.0000 | measured | 60 | ratio | All answer-quality labels satisfy deterministic contract checks. |
| rag_source_mapping_contract_rate | 1.0000 | measured | 30 | ratio | Stable candidate keys map to the reviewed seed categories. |
| safety_label_contract_rate | 1.0000 | measured | 100 | ratio | Reviewed safety decisions and flags are internally consistent. |
| memory_label_contract_rate | 1.0000 | measured | 40 | ratio | Retention and write labels pass deterministic member/confirmation checks. |
| expected_unconfirmed_write_protection_rate | 1.0000 | measured | 4 | ratio | This is an expected-policy ratio, not an observed runtime write rate. |
| provider_fault_policy_contract_rate | 1.0000 | measured | 30 | ratio | Fault expectations are checked without invoking external Providers. |
| expected_write_operation_retry_zero_rate | 1.0000 | measured | 30 | ratio | This verifies gold labels, not observed Provider behavior. |
| local_task_success_rate | 1.0000 | measured | 32 | ratio | Bounded Supervisor deterministic task policy pass rate on 32 synthetic cases. |
| context_isolation_pass_rate | 1.0000 | measured | 32 | ratio | RunTrace member-scope checks on the local synthetic business suite. |
| safety_recall | 1.0000 | measured | 18 | ratio | Deterministic SafetyAgent policy recall on cases that declare safety flags. |
| normal_request_false_positive_rate | 0.0000 | measured | 6 | ratio | Normal-case safety flags divided by normal synthetic cases; lower is better. |
| rag_recall_at_3 | 1.0000 | measured | 12 | ratio | Expected source recall in the top 3 local KeywordRetriever results. |
| rag_recall_at_5 | 1.0000 | measured | 12 | ratio | Expected source recall in the top 5 local KeywordRetriever results. |
| rag_mrr | 1.0000 | measured | 12 | ratio | Mean reciprocal rank of the expected source in the local KeywordRetriever result. |
| rag_citation_correctness | 1.0000 | measured | 12 | ratio | Citation pointer correctness using the top local retrieved source. |
| memory_key_retention_rate | 1.0000 | measured | 28 | ratio | Confirmed fact keys retained after ContextManager.compact. |
| unconfirmed_memory_write_rate | 0.0000 | measured | 40 | ratio | Cases that wrote an unconfirmed memory item; lower is better. |
| cross_member_leakage_rate | 0.0000 | measured | 40 | ratio | Memory observations exposing a reference for a different member; lower is better. |
| memory_source_pointer_retention_rate | 1.0000 | measured | 40 | ratio | Expected source pointers preserved through local compaction/reset. |
| checkpoint_recovery_success_rate | N/A | not_available | 0 | ratio | N/A locally: PostgreSQL/Redis checkpoint recovery was not started by this offline run. |
| provider_recovery_rate | 1.0000 | measured | 8 | ratio | Retryable read-only synthetic faults recovered on the final registry attempt. |
| provider_safe_degrade_rate | 1.0000 | measured | 22 | ratio | Non-recovered synthetic faults returned structured degraded responses without evidence. |
| write_operation_retry_error_rate | 0.0000 | measured | 10 | ratio | Write fault cases with an unintended retry; lower is better. |
| latency_p50_ms | 0.1447 | measured | 32 | ms | Local wall-clock measurement around deterministic bounded Supervisor execution. |
| latency_p95_ms | 0.3226 | measured | 32 | ms | Local wall-clock p95; not a production latency SLO. |
| average_input_tokens | N/A | not_available | 0 | tokens | N/A because deterministic provider emitted no model usage. |
| average_output_tokens | N/A | not_available | 0 | tokens | N/A because deterministic provider emitted no model usage. |
| average_cost_usd | N/A | not_available | 0 | usd | N/A because no billable model call or pricing table was used. |
| answer_quality_pass_rate | N/A | not_available | 0 | ratio | N/A: deterministic policy success is reported separately and is not human/model answer quality. |

## Evidence Boundary

- RAG recall is measured by executing `KeywordRetriever` against an in-memory SQLite knowledge fixture.
- Memory retention is measured by executing `ContextManager.compact` and `reset_after_run`.
- Provider recovery is measured by executing `ProviderRegistry` with deterministic injected faults.
- The latency values are local wall-clock observations and should be rerun on the same machine before comparison.
- Answer quality, model token usage and model cost remain `N/A` until a real model response with usage and a human-reviewed answer set are supplied.

# 4B Task 11 Deterministic Harness and Ablation Report

> This report uses frozen deterministic fixtures and modeled fixture latency. It is not a production, clinical, real-provider latency, token, or billing claim.

## Fairness Contract

| Field | Shared value |
| --- | --- |
| config_id | 4b-task11-shared-v1 |
| model | deterministic/deterministic-product-answer-v1 |
| tool_catalog_version | tool-registry-4b-task10 |
| rag_index_version | knowledge-rag-4b-task10 |
| safety_policy_version | three-layer-safety-4b-task7 |
| confirmation_policy_version | confirmation-state-machine-4b-task7 |
| context_token_limit | 4096 |
| max_output_tokens | 512 |

## Strategy Metrics

| Strategy | cases | success | tool set exact | tool params exact | route order | dup tools avg | safety recall | isolation | R@3 | R@5 | citation | p50 ms* | p95 ms* | token usage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single_agent | 32 | 1.0000 | 0.3750 | 0.3750 | N/A | 0.1562 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 1.0000 | 62 | 80 | 0.0000 |
| fixed_router | 32 | 0.8125 | 0.8125 | 0.8125 | 0.8125 | 0.0000 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 1.0000 | 48 | 60 | 0.0000 |
| bounded_supervisor | 32 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 1.0000 | 52 | 99 | 0.0000 |

*Latency is a frozen fixture field for repeatable regression comparison; task 12 owns real wall-clock validation.*

## Governance and Orchestration Attribution

| Strategy | role coverage | unnecessary handoffs avg | safety precision | governance coverage | token count | billed cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single_agent | 1.0000 | 0.0000 | 1.0000 | 1.0000 | N/A | N/A |
| fixed_router | 0.8958 | 0.0000 | 1.0000 | 1.0000 | N/A | N/A |
| bounded_supervisor | 1.0000 | 0.0000 | 1.0000 | 1.0000 | N/A | N/A |

## Case Inventory

| Category | Cases |
| --- | ---: |
| normal_single_domain | 6 |
| complex_cross_domain | 6 |
| missing_information | 3 |
| high_risk_medical | 5 |
| rag_and_source | 4 |
| provider_or_tool_failure | 3 |
| member_isolation_attack | 3 |
| confirmation_idempotency | 2 |

## Simple vs Complex

| Strategy | simple cases | simple success | complex cases | complex success |
| --- | ---: | ---: | ---: | ---: |
| single_agent | 26 | 1.0000 | 6 | 1.0000 |
| fixed_router | 26 | 1.0000 | 6 | 0.0000 |
| bounded_supervisor | 26 | 1.0000 | 6 | 1.0000 |

## Interpretation Boundary

- Safety, member isolation, RAG ranking, citations, confirmation policy, model identity and token limits are shared controls.
- Their pass rates must not be attributed to the bounded Supervisor.
- Token and billed cost remain `N/A` because the deterministic provider returned no usage; the harness does not estimate them.
- A/B/C differences only support claims about orchestration regression behavior in this fixed suite.

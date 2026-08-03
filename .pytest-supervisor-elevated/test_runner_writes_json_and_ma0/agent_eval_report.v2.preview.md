# 4D-B2.5 v2 Evaluation Report

- Status: `preview`
- Runner: `synthetic_projection`
- Dataset: `4d-b2.4`
- Split: `all`
- Samples: `2`

## Metrics

| Metric | Value | Samples | Status |
|---|---:|---:|---|
| task_success_rate | 1.0000 | 2 | preview |
| avg_latency_ms | 22.0000 | 2 | preview |
| p95_latency_ms | 22.0000 | 2 | preview |
| route_pass_rate | 1.0000 | 2 | preview |
| plan_pass_rate | 1.0000 | 2 | preview |
| tool_pass_rate | 1.0000 | 2 | preview |
| claim_pass_rate | 1.0000 | 2 | preview |
| rag_pass_rate | 1.0000 | 2 | preview |
| safety_pass_rate | 1.0000 | 2 | preview |
| context_pass_rate | 1.0000 | 2 | preview |
| reliability_pass_rate | 1.0000 | 2 | preview |
| database_state_pass_rate | 1.0000 | 2 | preview |

## Failure Reasons

- None

## Notes

- synthetic_projection does not call PostgreSQL, Provider, RAG or LLM
- preview metrics are pipeline checks, not final resume metrics

This is a local preview generated from deterministic Gold projection. It is not evidence of real application quality.

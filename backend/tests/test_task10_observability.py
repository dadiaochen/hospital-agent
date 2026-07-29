from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agent.observability import build_observation_traces
from app.agent.run_trace_schemas import ObservationTrace
from app.agent.runtime_trace_adapter import _redact_sensitive_values


def _completed_state() -> dict[str, object]:
    return {
        "run_id": "run-observation-1",
        "task_id": "task-observation-1",
        "user_id": "user-private",
        "member_id": "member-1",
        "user_input": "PRIVATE USER QUESTION",
        "input_payload": {"medical_text": "PRIVATE INPUT PAYLOAD"},
        "status": "completed",
        "latency_ms": 123,
        "visited_nodes": ["safety_entry", "chronic_care", "finalize"],
        "tool_calls": [
            {
                "tool_name": "query_prescriptions",
                "agent_role": "RefillAgent",
                "success": True,
                "latency_ms": 12,
                "attempts": [{"attempt_no": 1, "success": True}],
                "tool_input": {"secret": "PRIVATE TOOL INPUT"},
                "output": {"medical_fact": "PRIVATE TOOL OUTPUT"},
                "evidence_refs": [
                    {"source_id": "prescriptions:member-1"}
                ],
            }
        ],
        "provider_calls": [
            {
                "provider_name": "hospital",
                "operation": "department_search",
                "success": False,
                "latency_ms": 50,
                "fallback_reason": "provider_timeout",
                "attempts": [
                    {"attempt_no": 1, "success": False},
                    {"attempt_no": 2, "success": False},
                ],
                "request_payload": {"authorization": "PRIVATE API KEY"},
                "response_payload": {
                    "provider_raw_response": "PRIVATE PROVIDER RESPONSE",
                    "source_refs": [],
                },
            }
        ],
        "source_refs": [
            {
                "source_id": "knowledge:doc-1:chunk-1",
                "source_type": "knowledge_base",
                "provider": "keyword+pgvector",
                "source_metadata": {"content": "PRIVATE RAG CONTENT"},
            }
        ],
        "model_call_trace": {
            "effective_provider": "openai_compatible",
            "success": True,
            "latency_ms": 61,
            "fallback_reason": None,
            "input_tokens": 20,
            "output_tokens": 8,
            "total_tokens": 28,
            "token_usage_available": True,
            "attempts": [
                {
                    "provider_name": "openai_compatible",
                    "model_name": "example-model",
                    "success": True,
                }
            ],
        },
        "final_answer": "PRIVATE FINAL ANSWER",
    }


def test_observation_trace_covers_runtime_dimensions_without_payload_text() -> None:
    observations = build_observation_traces(_completed_state())
    event_types = {item.event_type for item in observations}

    assert {
        "request",
        "node",
        "tool",
        "provider",
        "source",
        "model",
        "final",
    } <= event_types
    assert all(item.task_id == "task-observation-1" for item in observations)
    assert all(item.run_id == "run-observation-1" for item in observations)
    assert all(item.request_id for item in observations)
    assert [item.sequence_no for item in observations] == list(
        range(1, len(observations) + 1)
    )

    provider = next(item for item in observations if item.event_type == "provider")
    assert provider.retry_count == 1
    assert provider.fallback_reason == "provider_timeout"
    model = next(item for item in observations if item.event_type == "model")
    assert model.model_name == "example-model"
    assert model.total_tokens == 28
    assert model.token_usage_available is True
    source = next(item for item in observations if item.event_type == "source")
    assert source.source_ids == ("knowledge:doc-1:chunk-1",)

    serialized = json.dumps(
        [item.model_dump(mode="json") for item in observations],
        ensure_ascii=False,
    )
    for secret in (
        "PRIVATE USER QUESTION",
        "PRIVATE INPUT PAYLOAD",
        "PRIVATE TOOL INPUT",
        "PRIVATE TOOL OUTPUT",
        "PRIVATE API KEY",
        "PRIVATE PROVIDER RESPONSE",
        "PRIVATE RAG CONTENT",
        "PRIVATE FINAL ANSWER",
        "user-private",
    ):
        assert secret not in serialized
    assert any(item.redaction_applied for item in observations)


def test_observation_contract_is_frozen_and_forbids_debug_payloads() -> None:
    observation = build_observation_traces(_completed_state())[0]
    with pytest.raises(ValidationError):
        observation.node_name = "mutated"
    with pytest.raises(ValidationError):
        ObservationTrace.model_validate(
            {
                **observation.model_dump(mode="json"),
                "raw_conversation": "must not enter observation",
            }
        )


def test_redaction_keeps_token_counts_but_removes_token_credentials() -> None:
    sanitized, paths = _redact_sensitive_values(
        {
            "input_tokens": 12,
            "output_tokens": 3,
            "total_tokens": 15,
            "token_usage_available": True,
            "token": "secret-token",
            "access_token": "secret-access-token",
        }
    )

    assert sanitized["input_tokens"] == 12
    assert sanitized["total_tokens"] == 15
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["access_token"] == "[REDACTED]"
    assert set(paths) == {"token", "access_token"}

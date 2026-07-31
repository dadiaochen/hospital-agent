"""Build privacy-safe observations from a completed product workflow state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid5

from app.agent.run_trace_schemas import ObservationTrace


_OBSERVATION_NAMESPACE = UUID("1b3dc0de-8a68-4f15-88ee-fcde1f3df643")


def build_observation_traces(state: Mapping[str, Any]) -> tuple[ObservationTrace, ...]:
    """Project only allow-listed identifiers, timings, outcomes, and counters."""

    run_id = str(state["run_id"])
    task_id = str(state["task_id"])
    member_id = str(state["member_id"])
    request_id = f"request:{task_id}:{run_id}"
    observations: list[ObservationTrace] = []

    def append(event_type: str, node_name: str, **values: Any) -> None:
        sequence_no = len(observations) + 1
        redacted_fields = tuple(
            dict.fromkeys(str(item) for item in values.pop("redacted_fields", ()))
        )
        observations.append(
            ObservationTrace(
                observation_id=str(
                    uuid5(
                        _OBSERVATION_NAMESPACE,
                        f"{run_id}:{sequence_no}:{event_type}:{node_name}",
                    )
                ),
                request_id=request_id,
                task_id=task_id,
                run_id=run_id,
                member_id=member_id,
                event_type=event_type,  # type: ignore[arg-type]
                node_name=node_name,
                sequence_no=sequence_no,
                redaction_applied=bool(redacted_fields),
                redacted_fields=redacted_fields,
                **values,
            )
        )

    append(
        "request",
        "request",
        success=True,
        redacted_fields=("user_input", "input_payload"),
    )

    for node_name in _string_sequence(state.get("visited_nodes")):
        append("node", node_name, success=True)

    for item in _mapping_sequence(state.get("tool_calls")):
        attempts = _mapping_sequence(item.get("attempts"))
        append(
            "tool",
            str(item.get("agent_role") or "tool_registry"),
            agent_role=_optional_text(item.get("agent_role")),
            tool_name=_optional_text(item.get("tool_name")),
            success=_optional_bool(item.get("success")),
            latency_ms=_non_negative_int(item.get("latency_ms")),
            retry_count=max(0, len(attempts) - 1),
            fallback_reason=(
                _optional_text(item.get("fallback_action"))
                if not bool(item.get("success"))
                else None
            ),
            source_ids=_source_ids(item.get("evidence_refs")),
            redacted_fields=("tool_input", "output"),
        )

    for item in _mapping_sequence(state.get("provider_calls")):
        attempts = _mapping_sequence(item.get("attempts"))
        response_payload = item.get("response_payload")
        response = response_payload if isinstance(response_payload, Mapping) else {}
        append(
            "provider",
            f"provider:{item.get('operation') or 'call'}",
            provider_name=_optional_text(item.get("provider_name")),
            success=_optional_bool(item.get("success")),
            latency_ms=_non_negative_int(item.get("latency_ms")),
            retry_count=max(0, len(attempts) - 1),
            fallback_reason=_optional_text(item.get("fallback_reason")),
            source_ids=_source_ids(response.get("source_refs")),
            redacted_fields=("request_payload", "response_payload"),
        )

    knowledge_sources = [
        item
        for item in _mapping_sequence(state.get("source_refs"))
        if item.get("source_type") == "knowledge_base"
    ]
    if knowledge_sources:
        append(
            "source",
            "rag_retrieval",
            provider_name=_first_text(knowledge_sources, "provider"),
            success=True,
            source_ids=_source_ids(knowledge_sources),
        )

    model = state.get("model_call_trace")
    if isinstance(model, Mapping) and model:
        attempts = _mapping_sequence(model.get("attempts"))
        effective = next(
            (
                item
                for item in reversed(attempts)
                if item.get("provider_name") == model.get("effective_provider")
            ),
            attempts[-1] if attempts else {},
        )
        token_usage_available = bool(model.get("token_usage_available", False))
        append(
            "model",
            "finalize",
            provider_name=_optional_text(model.get("effective_provider")),
            model_name=_optional_text(effective.get("model_name")),
            success=_optional_bool(model.get("success")),
            latency_ms=_non_negative_int(model.get("latency_ms")),
            retry_count=max(0, len(attempts) - 1),
            fallback_reason=_optional_text(model.get("fallback_reason")),
            input_tokens=(
                _non_negative_int(model.get("input_tokens"))
                if token_usage_available
                else None
            ),
            output_tokens=(
                _non_negative_int(model.get("output_tokens"))
                if token_usage_available
                else None
            ),
            total_tokens=(
                _non_negative_int(model.get("total_tokens"))
                if token_usage_available
                else None
            ),
            token_usage_available=token_usage_available,
            redacted_fields=("messages", "provider_raw_response"),
        )

    append(
        "final",
        "finalize",
        success=str(state.get("status")) in {"completed", "needs_confirmation"},
        latency_ms=_non_negative_int(state.get("latency_ms")),
        source_ids=_source_ids(state.get("source_refs")),
        redacted_fields=("final_answer",),
    )
    return tuple(observations)


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_sequence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in value if str(item))


def _source_ids(value: Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(item["source_id"])
            for item in _mapping_sequence(value)
            if item.get("source_id")
        )
    )


def _first_text(items: Sequence[Mapping[str, Any]], key: str) -> str | None:
    return next((_optional_text(item.get(key)) for item in items if item.get(key)), None)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = ["build_observation_traces"]

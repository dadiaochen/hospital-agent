from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field

from app.agent.context_schemas import (
    ContractModel,
    RAGSourceRef,
    RunSummary,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import ExpectedCase
from app.agent.run_trace_schemas import RunTrace, SafetyTrace


REDACTED_VALUE = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "password",
    "prompt",
    "provider_raw_response",
    "raw_conversation",
    "request_fingerprint",
    "scratchpad",
    "secret",
    "token",
    "access_token",
    "bearer_token",
    "refresh_token",
)
SAFE_TOKEN_COUNT_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "token_usage_available",
}


class RuntimeTraceAdapterError(ValueError):
    """Raised when a runtime artifact payload is not internally consistent."""


class AdaptedRuntimeTrace(ContractModel):
    trace: RunTrace
    source_run_id: str = Field(min_length=1)
    source_task_id: str = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(default_factory=tuple)
    redacted_paths: tuple[str, ...] = Field(default_factory=tuple)


class RuntimeTraceAdapter:
    """Project untrusted runtime artifacts into the evaluator's frozen RunTrace."""

    def adapt(
        self,
        expected_case: ExpectedCase,
        artifacts_payload: Mapping[str, Any],
    ) -> AdaptedRuntimeTrace:
        sanitized, redacted_paths = _redact_sensitive_values(artifacts_payload)
        artifacts = _as_mapping(sanitized, "artifacts")

        trace = RunTrace.model_validate(_required(artifacts, "run_trace"))
        summary = RunSummary.model_validate(_required(artifacts, "run_summary"))
        safety = SafetyTrace.model_validate(_required(artifacts, "safety_trace"))
        tool_refs = tuple(
            ToolEvidenceRef.model_validate(item)
            for item in _as_sequence(artifacts.get("tool_evidence_refs", ()))
        )
        rag_refs = tuple(
            RAGSourceRef.model_validate(item)
            for item in _as_sequence(artifacts.get("rag_source_refs", ()))
        )

        source_run_id = _required_text(artifacts, "run_id")
        source_task_id = _required_text(artifacts, "task_id")
        self._validate_scope(
            trace=trace,
            summary=summary,
            safety=safety,
            tool_refs=tool_refs,
            rag_refs=rag_refs,
            source_run_id=source_run_id,
            source_task_id=source_task_id,
        )

        evaluation_trace = trace.model_copy(update={"case_id": expected_case.case_id})
        source_ids = tuple(
            dict.fromkeys(
                [ref.source_id for ref in tool_refs]
                + [ref.source_id for ref in rag_refs]
            )
        )
        return AdaptedRuntimeTrace(
            trace=evaluation_trace,
            source_run_id=source_run_id,
            source_task_id=source_task_id,
            source_ids=source_ids,
            redacted_paths=tuple(redacted_paths),
        )

    @staticmethod
    def _validate_scope(
        *,
        trace: RunTrace,
        summary: RunSummary,
        safety: SafetyTrace,
        tool_refs: tuple[ToolEvidenceRef, ...],
        rag_refs: tuple[RAGSourceRef, ...],
        source_run_id: str,
        source_task_id: str,
    ) -> None:
        failures: list[str] = []
        if trace.run_id != source_run_id:
            failures.append("run_id_mismatch")
        if trace.task_id != source_task_id:
            failures.append("task_id_mismatch")
        if summary.run_id != source_run_id or summary.task_id != source_task_id:
            failures.append("run_summary_scope_mismatch")
        if summary.member_id != trace.member_id:
            failures.append("run_summary_member_mismatch")
        if summary.intent != trace.intent:
            failures.append("run_summary_intent_mismatch")
        if summary.final_answer_ref != trace.final_answer.answer_id:
            failures.append("run_summary_answer_mismatch")
        if safety != trace.safety_trace:
            failures.append("safety_trace_mismatch")
        if set(summary.safety_flags) != set(safety.flags):
            failures.append("run_summary_safety_mismatch")
        if tuple(summary.tool_evidence_refs) != tool_refs:
            failures.append("run_summary_tool_references_mismatch")
        if tuple(summary.rag_source_refs) != rag_refs:
            failures.append("run_summary_rag_references_mismatch")
        if any(ref.run_id != source_run_id for ref in tool_refs):
            failures.append("tool_reference_run_mismatch")
        if any(ref.member_id != trace.member_id for ref in tool_refs):
            failures.append("tool_reference_member_mismatch")
        if any(
            ref.member_id is not None and ref.member_id != trace.member_id
            for ref in rag_refs
        ):
            failures.append("rag_reference_member_mismatch")
        if failures:
            raise RuntimeTraceAdapterError(
                "runtime artifact scope validation failed: " + ",".join(failures)
            )


def _redact_sensitive_values(value: Any) -> tuple[Any, list[str]]:
    redacted_paths: list[str] = []

    def redact(current: Any, path: str) -> Any:
        if isinstance(current, Mapping):
            output: dict[str, Any] = {}
            for raw_key, item in current.items():
                key = str(raw_key)
                item_path = f"{path}.{key}" if path else key
                if _is_sensitive_key(key):
                    output[key] = REDACTED_VALUE
                    redacted_paths.append(item_path)
                else:
                    output[key] = redact(item, item_path)
            return output
        if isinstance(current, Sequence) and not isinstance(
            current,
            (str, bytes, bytearray),
        ):
            return [
                redact(item, f"{path}[{index}]")
                for index, item in enumerate(current)
            ]
        return current

    return redact(value, ""), redacted_paths


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in SAFE_TOKEN_COUNT_KEYS:
        return False
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _required(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise RuntimeTraceAdapterError(f"runtime artifacts missing {key}")
    return mapping[key]


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = _required(mapping, key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeTraceAdapterError(f"runtime artifact {key} must be non-empty")
    return value


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeTraceAdapterError(f"{name} must be an object")
    return value


def _as_sequence(value: Any) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise RuntimeTraceAdapterError("runtime artifact references must be arrays")
    return value


__all__ = [
    "AdaptedRuntimeTrace",
    "RuntimeTraceAdapter",
    "RuntimeTraceAdapterError",
]

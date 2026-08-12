"""Build frozen audit artifacts for the 4B product workflow.

The business graph owns execution.  This module only projects its completed
state into the existing trace, context-reset and deterministic-evaluation
contracts; it never calls a model, provider, database, or business tool.
"""

from __future__ import annotations

from typing import Any, Mapping, cast
from uuid import uuid5, UUID

from app.agent.context_manager import ContextManager
from app.agent.context_schemas import (
    ContextEnvelope,
    RAGSourceRef,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult, ExpectedCase, ExpectedSource
from app.agent.evaluator import DeterministicEvaluator
from app.agent.final_claim_schemas import (
    AnswerEnvelope,
    FinalClaim,
    build_workflow_claims,
)
from app.agent.run_trace_schemas import (
    FinalAnswerTrace,
    OrchestrationTrace,
    RAGTrace,
    RunTrace,
    SafetyTrace,
    ToolCallTrace,
)
from app.agent.observability import build_observation_traces
from app.agent.orchestration_schemas import OrchestrationRunResult
from app.schemas.business import SourceRef


_ANSWER_NAMESPACE = UUID("8af70a0f-a166-4ba1-a0ca-3be0c21b1c20")


def add_product_artifacts(state: dict[str, Any]) -> dict[str, Any]:
    """Add trace, evaluation and reset summary fields to a product state."""

    trace = build_run_trace(state)
    expected = build_expected_case(state, trace)
    evaluation = DeterministicEvaluator().evaluate(expected, trace)
    evaluation = _normalize_workflow_failure(evaluation, state)
    envelope = build_context_envelope(state, trace)
    run_summary = ContextManager().create_run_summary(
        envelope=envelope,
        run_trace=trace,
        final_answer=trace.final_answer,
        evaluation_result=evaluation,
    )
    state["run_trace"] = trace.model_dump(mode="json")
    state["evaluation_result"] = evaluation.model_dump(mode="json")
    state["run_summary"] = run_summary.model_dump(mode="json")
    state["context_envelope"] = envelope.model_dump(mode="json")
    return state


def build_run_trace(state: Mapping[str, Any]) -> RunTrace:
    member_id = str(state["member_id"])
    tool_calls: list[ToolCallTrace] = []
    for item in state.get("tool_calls", []):
        if not isinstance(item, Mapping):
            continue
        output = item.get("tool_output")
        if not isinstance(output, Mapping):
            output = item.get("output")
        if not isinstance(output, Mapping):
            output = {}
        source_id = output.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            source_id = _first_source_id(output)
        tool_calls.append(
            ToolCallTrace(
                tool_name=str(item.get("tool_name") or "unknown"),
                member_id=str(item.get("member_id") or member_id),
                tool_input=(
                    dict(item["tool_input"])
                    if isinstance(item.get("tool_input"), Mapping)
                    else {}
                ),
                source_id=source_id,
                source_name=(
                    str(item.get("source_name"))
                    if item.get("source_name")
                    else str(output.get("source_name"))
                    if output.get("source_name")
                    else None
                ),
                success=bool(item.get("success", False)),
                schema_valid=bool(item.get("schema_valid", False)),
                evidence_present=bool(item.get("evidence_present", False)),
            )
        )

    rag_traces: list[RAGTrace] = []
    for source in _source_refs(state):
        if source.source_type != "knowledge_base":
            continue
        if not source.document_id or not source.chunk_id:
            continue
        rag_traces.append(
            RAGTrace(
                source_id=source.source_id,
                source_name=source.provider or source.source_id,
                member_id=source.member_id or member_id,
                retrieved=True,
                schema_valid=True,
            )
        )

    status = str(state.get("status") or "failed")
    confirmation_state = str(state.get("confirmation_state") or "NONE")
    answer = str(state.get("final_answer") or "")
    display_content = answer or "当前没有生成可展示的回答。"
    waiting = status == "needs_confirmation" or bool(
        state.get("need_human_confirmation", False)
    )
    confirmation_present = bool(
        state.get("human_confirmation_granted") or state.get("confirmation_result")
    )
    if waiting:
        # A blocked high-risk request may still require human review.  Keep
        # that distinction in the frozen answer contract: it is not an
        # executable action, but the answer is waiting for a human decision.
        action_status = "awaiting_confirmation"
    elif confirmation_state == "DRAFT" or status == "needs_confirmation":
        action_status = "awaiting_confirmation"
    elif confirmation_state == "EXECUTED" or state.get("confirmation_result"):
        action_status = "executed"
    elif status == "blocked":
        action_status = "none"
    else:
        action_status = "none"

    orchestration = _orchestration_trace(state)
    context_source_ids = tuple(
        dict.fromkeys(
            [
                *(
                    call.source_id
                    for call in tool_calls
                    if call.success and call.evidence_present and call.source_id
                ),
                *(rag.source_id for rag in rag_traces if rag.retrieved),
                *(source.source_id for source in _source_refs(state)),
            ]
        )
    )
    dependency_result_ids = tuple(
        result.step_id
        for result in orchestration.domain_agent_results
        if result.step_id
    ) if orchestration is not None else ()
    claims = tuple(
        FinalClaim.model_validate(item)
        for item in state.get("final_claims", [])
        if isinstance(item, Mapping)
    )
    # Failed/blocked/clarification runs may still have read structured data
    # before a later source or provider failure.  Those pointers remain useful
    # for audit, but they must not be converted into user-visible factual
    # claims after the run has failed closed.
    if not claims and status not in {"failed", "blocked", "needs_clarification"}:
        claims = build_workflow_claims(
            run_id=str(state["run_id"]),
            member_id=member_id,
            status=status,
            confirmation_state=confirmation_state,
            source_ids=context_source_ids,
        )
    answer_id = str(uuid5(_ANSWER_NAMESPACE, str(state["run_id"])))
    answer_envelope = AnswerEnvelope(
        answer_id=answer_id,
        run_id=str(state["run_id"]),
        task_id=str(state["task_id"]),
        member_id=member_id,
        display_text=display_content,
        claims=claims,
        waiting_for_user_confirmation=waiting,
        human_confirmation_present=confirmation_present,
        action_status=action_status,
        context_source_ids=context_source_ids,
        dependency_result_ids=dependency_result_ids,
    )
    model_trace = state.get("model_call_trace")
    model_trace = model_trace if isinstance(model_trace, Mapping) else {}
    token_usage_available = bool(model_trace.get("token_usage_available", False))

    return RunTrace(
        trace_schema_version="4d-b2.3",
        case_id=f"business-task:{state['task_id']}",
        run_id=str(state["run_id"]),
        task_id=str(state["task_id"]),
        user_id=str(state["user_id"]),
        member_id=member_id,
        intent=cast(Any, str(state.get("intent") or state["business_domain"])),
        tool_calls=tuple(tool_calls),
        rag_traces=tuple(rag_traces),
        safety_trace=SafetyTrace(
            member_id=member_id,
            flags=tuple(str(flag) for flag in state.get("safety_flags", [])),
            blocked=status == "blocked",
            requires_human_confirmation=(
                bool(state.get("need_human_confirmation", False))
                or confirmation_state == "DRAFT"
            ),
        ),
        final_answer=FinalAnswerTrace(
            answer_id=answer_id,
            content=display_content,
            contains_factual_claims=(
                status not in {"failed", "blocked", "needs_clarification"}
                and (bool(_source_refs(state)) or bool(claims))
            ),
            waiting_for_user_confirmation=waiting,
            human_confirmation_present=confirmation_present,
            action_status=action_status,
            answer_envelope=answer_envelope,
        ),
        observations=build_observation_traces(state),
        orchestration=orchestration,
        context_source_ids=context_source_ids,
        dependency_result_ids=dependency_result_ids,
        input_tokens=(
            int(model_trace["input_tokens"])
            if token_usage_available and model_trace.get("input_tokens") is not None
            else None
        ),
        output_tokens=(
            int(model_trace["output_tokens"])
            if token_usage_available and model_trace.get("output_tokens") is not None
            else None
        ),
        total_tokens=(
            int(model_trace["total_tokens"])
            if token_usage_available and model_trace.get("total_tokens") is not None
            else None
        ),
        token_usage_available=token_usage_available,
        latency_ms=max(0, int(state.get("latency_ms") or 0)),
        schema_valid=all(call.schema_valid for call in tool_calls),
    )


def _orchestration_trace(
    state: Mapping[str, Any],
) -> OrchestrationTrace | None:
    """Project the unified graph result without retaining its raw request text."""

    raw = state.get("orchestration_run")
    if not isinstance(raw, Mapping):
        return None
    result = OrchestrationRunResult.model_validate(raw)
    return OrchestrationTrace(
        route=result.route,
        plan=result.plan,
        supervisor_decisions=result.decisions,
        domain_agent_results=result.results,
        completed=result.completed,
        termination_reason=result.termination_reason,
        steps_executed=result.steps_executed,
        used_planner=result.used_planner,
        used_supervisor=result.used_supervisor,
        execution_mode=result.execution_mode,
        context_mode=result.context_mode,
        parallel_batches=result.parallel_batches,
    )


def build_expected_case(state: Mapping[str, Any], trace: RunTrace) -> ExpectedCase:
    category = {
        "preconsultation": "consultation",
        "chronic_care": "refill",
        "health_record": "consultation",
    }.get(str(state.get("business_domain")), "refill")
    successful_tools = [call.tool_name for call in trace.tool_calls if call.success]
    expected_sources: list[ExpectedSource] = []
    for call in trace.tool_calls:
        if call.success and call.evidence_present:
            expected_sources.append(
                ExpectedSource(
                    source_type="tool_evidence",
                    source_name=call.source_name or call.tool_name,
                )
            )
    for rag in trace.rag_traces:
        expected_sources.append(
            ExpectedSource(source_type="rag_source", source_name=rag.source_name)
        )

    unique_sources: list[ExpectedSource] = []
    seen_sources: set[tuple[str, str]] = set()
    for source in expected_sources:
        key = (source.source_type, source.source_name)
        if key not in seen_sources:
            seen_sources.add(key)
            unique_sources.append(source)

    return ExpectedCase(
        case_id=trace.case_id,
        input_category=cast(Any, category),
        user_input=str(state.get("user_input") or state.get("user_goal") or "task"),
        expected_intent=trace.intent,
        expected_member_id=trace.member_id,
        expected_required_tools=successful_tools,
        expected_safety_flags=list(trace.safety_trace.flags),
        expected_human_confirmation_required=(
            trace.final_answer.waiting_for_user_confirmation
            and not trace.safety_trace.blocked
        ),
        forbidden_phrases=[],
        expected_sources=unique_sources,
    )


def build_context_envelope(
    state: Mapping[str, Any],
    trace: RunTrace,
) -> ContextEnvelope:
    tool_refs: list[ToolEvidenceRef] = []
    allowed_tools: list[str] = []
    for index, call in enumerate(trace.tool_calls):
        allowed_tools.append(call.tool_name)
        if not call.evidence_present or not call.source_id:
            continue
        tool_refs.append(
            ToolEvidenceRef(
                source_id=call.source_id,
                run_id=trace.run_id,
                member_id=trace.member_id,
                tool_name=call.tool_name,
                tool_call_id=f"{trace.run_id}:tool:{index}",
                success=call.success,
                schema_valid=call.schema_valid,
            )
        )
    rag_refs = [
        RAGSourceRef(
            source_id=source.source_id,
            document_id=source.document_id,
            chunk_id=source.chunk_id,
            member_id=source.member_id,
            version=source.document_version,
            purpose=str(state.get("business_domain") or "business_task"),
        )
        for source in _source_refs(state)
        if source.source_type == "knowledge_base"
        and source.document_id
        and source.chunk_id
    ]
    request = state.get("confirmation_request")
    pending = []
    if (
        state.get("need_human_confirmation")
        and isinstance(request, Mapping)
        and request.get("tool_name")
    ):
        pending.append(str(request["tool_name"]))
    action_type = (
        "draft"
        if request
        else "safety_review"
        if trace.safety_trace.flags
        else "query"
    )
    return ContextManager().build_envelope(
        user_input=str(state.get("user_input") or "business task"),
        run_id=trace.run_id,
        task_id=trace.task_id,
        user_id=trace.user_id,
        member_id=trace.member_id,
        intent=trace.intent,
        action_type=action_type,
        pending_confirmations=pending,
        tool_evidence_refs=tool_refs,
        rag_source_refs=rag_refs,
        safety_flags=list(trace.safety_trace.flags),
        allowed_tools=list(dict.fromkeys(allowed_tools)),
    )


def _source_refs(state: Mapping[str, Any]) -> list[SourceRef]:
    return [
        SourceRef.model_validate(item)
        for item in state.get("source_refs", [])
        if isinstance(item, Mapping)
    ]


def _first_source_id(output: Mapping[str, Any]) -> str | None:
    refs = output.get("source_refs")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if isinstance(ref, Mapping) and ref.get("source_id"):
            return str(ref["source_id"])
    return None


def _normalize_workflow_failure(
    evaluation: EvaluationResult,
    state: Mapping[str, Any],
) -> EvaluationResult:
    status = str(state.get("status") or "failed")
    if status not in {"failed", "needs_clarification"} or not evaluation.task_success:
        return evaluation
    reason = "execution_failed" if status == "failed" else "needs_clarification"
    return evaluation.model_copy(
        update={
            "task_success": False,
            "failure_reasons": list(dict.fromkeys([*evaluation.failure_reasons, reason])),
        }
    )


__all__ = [
    "add_product_artifacts",
    "build_context_envelope",
    "build_expected_case",
    "build_run_trace",
]

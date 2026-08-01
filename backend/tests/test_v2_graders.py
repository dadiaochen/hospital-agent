from pathlib import Path

from app.agent.final_claim_schemas import FinalClaim
from app.agent.run_trace_schemas import RAGTrace
from app.agent.v2_benchmark_generator import load_v2_benchmark
from app.agent.v2_eval_runner import SyntheticProjectionExecutor
from app.agent.v2_eval_schemas import V2RunArtifacts
from app.agent.v2_graders import V2DeterministicGraders, V2GradingContext
from app.agent.v2_materializer import WorldStateMaterializer


ROOT = Path(__file__).resolve().parents[2]


def _baseline_context(*, fault_type: str | None = None):
    worlds, queries, _ = load_v2_benchmark(project_root=ROOT)
    if fault_type is None:
        world = worlds.world_states[0]
    else:
        world = next(
            item
            for item in worlds.world_states
            if item.fault_injection.fault_type == fault_type
        )
    query = next(item for item in queries.queries if item.world_state_id == world.world_state_id)
    materialized = WorldStateMaterializer().materialize(world, query)
    artifacts = SyntheticProjectionExecutor().execute(materialized, repeat_index=0)
    return world, query, artifacts


def _grade(context):
    grades = V2DeterministicGraders().grade(context)
    return {grade.grader: grade for grade in grades}


def test_synthetic_projection_passes_all_nine_graders() -> None:
    world, query, artifacts = _baseline_context()

    grades = _grade(V2GradingContext(world=world, query=query, artifacts=artifacts))

    assert set(grades) == set(V2DeterministicGraders.LAYER_ORDER)
    assert all(grade.passed for grade in grades.values())


def test_missing_tool_has_partial_accuracy_and_failure_reason() -> None:
    world, query, artifacts = _baseline_context()
    bad_trace = artifacts.run_trace.model_copy(
        update={"tool_calls": artifacts.run_trace.tool_calls[:-1]}
    )
    bad_artifacts = artifacts.model_copy(
        update={
            "run_trace": bad_trace,
            "observed_tool_names": artifacts.observed_tool_names[:-1],
        }
    )

    tool_grade = _grade(
        V2GradingContext(world=world, query=query, artifacts=bad_artifacts)
    )["tool"]

    assert tool_grade.passed is False
    assert tool_grade.score < 1.0
    assert any(reason.startswith("tool.missing:") for reason in tool_grade.failure_reasons)


def test_forbidden_claim_is_detected() -> None:
    world, query, artifacts = _baseline_context()
    envelope = artifacts.run_trace.final_answer.answer_envelope
    assert envelope is not None
    forbidden_claim = FinalClaim(
        claim_id=f"{artifacts.run_trace.run_id}:forbidden",
        fact_key="action_executed",
        subject_id=query.expected_member_id,
        value=True,
        source_ids=envelope.context_source_ids[:1],
        claim_type="operational_fact",
    )
    bad_envelope = envelope.model_copy(
        update={"claims": (*envelope.claims, forbidden_claim)}
    )
    bad_answer = artifacts.run_trace.final_answer.model_copy(
        update={"answer_envelope": bad_envelope}
    )
    bad_trace = artifacts.run_trace.model_copy(update={"final_answer": bad_answer})
    bad_artifacts = artifacts.model_copy(update={"run_trace": bad_trace})

    claim_grade = _grade(
        V2GradingContext(world=world, query=query, artifacts=bad_artifacts)
    )["claim"]

    assert claim_grade.passed is False
    assert "claim.forbidden:action_executed" in claim_grade.failure_reasons


def test_missing_safety_flag_fails_safety_grade() -> None:
    world, query, artifacts = _baseline_context()
    bad_safety = artifacts.run_trace.safety_trace.model_copy(update={"flags": ()})
    bad_trace = artifacts.run_trace.model_copy(update={"safety_trace": bad_safety})
    bad_artifacts = artifacts.model_copy(update={"run_trace": bad_trace})

    safety_grade = _grade(
        V2GradingContext(world=world, query=query, artifacts=bad_artifacts)
    )["safety"]

    assert safety_grade.passed is False
    assert "safety.flags_mismatch" in safety_grade.failure_reasons


def test_member_mismatch_fails_context_isolation() -> None:
    world, query, artifacts = _baseline_context()
    bad_trace = artifacts.run_trace.model_copy(update={"member_id": "foreign-member"})
    bad_artifacts = artifacts.model_copy(update={"run_trace": bad_trace})

    context_grade = _grade(
        V2GradingContext(world=world, query=query, artifacts=bad_artifacts)
    )["context"]

    assert context_grade.passed is False
    assert "context.member_mismatch" in context_grade.failure_reasons


def test_stale_rag_source_fails_rag_grade() -> None:
    world, query, artifacts = _baseline_context(fault_type="stale_source")
    stale_source = world.knowledge_state.stale_source_ids[0]
    stale_rag = RAGTrace(
        source_id=stale_source,
        source_name="synthetic:stale",
        member_id=None,
    )
    bad_trace = artifacts.run_trace.model_copy(
        update={"rag_traces": (*artifacts.run_trace.rag_traces, stale_rag)}
    )
    bad_artifacts = artifacts.model_copy(
        update={
            "run_trace": bad_trace,
            "observed_source_ids": (*artifacts.observed_source_ids, stale_source),
            "observed_rag_source_ids": (*artifacts.observed_rag_source_ids, stale_source),
        }
    )

    rag_grade = _grade(
        V2GradingContext(world=world, query=query, artifacts=bad_artifacts)
    )["rag"]

    assert rag_grade.passed is False
    assert f"rag.stale_source:{stale_source}" in rag_grade.failure_reasons


def test_graders_do_not_modify_frozen_final_answer() -> None:
    world, query, artifacts = _baseline_context()
    before = artifacts.run_trace.final_answer.model_dump(mode="json")

    _grade(V2GradingContext(world=world, query=query, artifacts=artifacts))

    assert artifacts.run_trace.final_answer.model_dump(mode="json") == before

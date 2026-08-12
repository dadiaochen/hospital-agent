from app.agent.unified_eval_dataset import (
    DATASET_VERSION,
    load_unified_agent_benchmark,
)
from app.agent.v2_eval_runner import V2EvalRunner
from app.agent.v2_eval_schemas import V2RunnerOptions
from app.agent.v2_graders import V2GradingContext


def test_unified_loader_and_trace_freeze_tool_input_and_block_state() -> None:
    worlds, queries, manifest = load_unified_agent_benchmark()

    assert manifest.dataset_version == DATASET_VERSION
    assert len(worlds.world_states) == 100
    assert len(queries.queries) == 400
    assert queries.queries[0].expected_tool_invocations

    report = V2EvalRunner(
        dataset_loader=load_unified_agent_benchmark
    ).run(
        V2RunnerOptions(max_cases=4)
    )

    assert report.dataset_version == DATASET_VERSION
    assert report.sample_count == 4
    assert all(result.tool_calls for result in report.case_results)
    assert all(
        any(call.tool_input for call in result.tool_calls)
        for result in report.case_results
    )
    assert all(
        result.observed_blocked == result.expected_blocked
        for result in report.case_results
    )
    assert all(result.review_status == "automatic_gold" for result in report.case_results)
    metrics = {metric.name: metric for metric in report.metrics}
    assert metrics["tool_call_accuracy"].value == 1.0
    assert metrics["tool_parameter_accuracy"].value == 1.0
    assert "high_risk_false_block_rate" in metrics


def test_unified_parallel_projection_keeps_dataset_order_and_cleans_up() -> None:
    runner = V2EvalRunner(dataset_loader=load_unified_agent_benchmark)

    report = runner.run(V2RunnerOptions(max_cases=12, concurrency=4))

    assert report.sample_count == 12
    assert [item.query_id for item in report.case_results] == [
        query.query_id
        for query in load_unified_agent_benchmark()[1].queries[:12]
    ]
    assert all(item.cleanup_succeeded for item in report.case_results)
    assert runner.materializer.backend.active_namespaces == ()
    assert any("bounded concurrency=4" in note for note in report.notes)


def test_unified_tool_parameter_grade_detects_wrong_actual_input() -> None:
    runner = V2EvalRunner(dataset_loader=load_unified_agent_benchmark)
    worlds, queries, _ = load_unified_agent_benchmark()
    world = worlds.world_states[0]
    query = queries.queries[0]
    materialized = runner.materializer.materialize(world, query)
    artifacts = runner.executor.execute(materialized, repeat_index=0)
    first = artifacts.run_trace.tool_calls[0].model_copy(
        update={"tool_input": {"member_id": "wrong-member"}}
    )
    trace = artifacts.run_trace.model_copy(
        update={"tool_calls": (first, *artifacts.run_trace.tool_calls[1:])}
    )
    changed = artifacts.model_copy(update={"run_trace": trace})
    grades = runner.graders.grade(
        V2GradingContext(world=world, query=query, artifacts=changed)
    )
    tool_grade = next(grade for grade in grades if grade.grader == "tool")

    assert not tool_grade.passed
    assert not tool_grade.details["parameter_match"]
    assert any(
        reason.startswith("tool.parameter_mismatch:")
        for reason in tool_grade.failure_reasons
    )

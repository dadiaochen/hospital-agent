from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.v2_ablation import (
    V2AblationRunner,
    default_v2_ablation_conditions,
)
from app.agent.v2_benchmark_generator import V2BenchmarkDataError, load_v2_benchmark
from app.agent.v2_eval_runner import V2EvalRunner
from app.agent.v2_eval_schemas import V2RunnerOptions
from app.agent.v2_integration import (
    IntegrationExecutionError,
    IntegrationIdentityMap,
    PostgresV2Materializer,
    ScopedProviderSandbox,
)
from app.providers.schemas import ProviderRequest


ROOT = Path(__file__).resolve().parents[2]


def _first_case():
    worlds, queries, _ = load_v2_benchmark(project_root=ROOT)
    world = worlds.world_states[0]
    query = next(item for item in queries.queries if item.world_state_id == world.world_state_id)
    return world, query


def test_integration_runner_requires_real_materializer_and_executor() -> None:
    with pytest.raises(V2BenchmarkDataError, match="requires PostgresV2Materializer"):
        V2EvalRunner(project_root=ROOT).run(
            V2RunnerOptions(
                runner_mode="integration",
                max_cases=1,
                allow_pending_review=True,
            )
        )


def test_postgres_materializer_rejects_sqlite_session() -> None:
    engine = create_engine("sqlite:///:memory:")
    world, query = _first_case()

    with pytest.raises(ValueError, match="PostgreSQL session"):
        PostgresV2Materializer(lambda: Session(engine)).materialize(world, query)

    engine.dispose()


def test_identity_and_source_mapping_fail_closed() -> None:
    identity = IntegrationIdentityMap(
        benchmark_user_id="benchmark-user",
        actual_user_id="actual-user",
        member_ids={"benchmark-member": "actual-member"},
        source_ids={"actual-source": "benchmark-source"},
    )

    assert identity.resolve_member("benchmark-member") == "actual-member"
    assert identity.map_source("actual-source") == "benchmark-source"
    with pytest.raises(IntegrationExecutionError, match="missing real member mapping"):
        identity.resolve_member("foreign-member")
    with pytest.raises(IntegrationExecutionError, match="missing benchmark source mapping"):
        identity.map_source("unregistered-source")


def test_provider_sandbox_is_case_scoped_and_records_timeout_attempts() -> None:
    worlds, _queries, _manifest = load_v2_benchmark(project_root=ROOT)
    world = next(
        item for item in worlds.world_states if item.fault_injection.fault_type == "timeout"
    )
    request = ProviderRequest(
        operation="search_inventory",
        business_domain="chronic_care",
        provider_mode="sandbox",
        user_id=world.user.user_id,
        member_id=world.gold.expected_member_id,
        payload={"medicine_name": "demo"},
    )

    response = ScopedProviderSandbox(world).invoke("pharmacy", request)

    assert response.success is False
    assert response.degraded is True
    assert len(response.attempts) == 2
    assert all(attempt.error_type == "timeout" for attempt in response.attempts)


def test_ablation_defines_four_fair_conditions() -> None:
    conditions = default_v2_ablation_conditions()

    assert tuple(item.condition for item in conditions) == ("A", "B", "C", "D")
    assert conditions[0].runtime_options.context_mode == "all_history"
    assert conditions[0].runtime_options.evaluation_only is True
    assert conditions[2].runtime_options.execution_mode == "parallel"
    assert conditions[3].runtime_options.context_mode == "dependency_only"
    assert all(item.held_constant for item in conditions)


def test_ablation_preview_emits_one_result_per_condition() -> None:
    report = V2AblationRunner(project_root=ROOT).run(
        runner_options=V2RunnerOptions(max_cases=1, allow_pending_review=True)
    )

    assert report.status == "preview"
    assert tuple(item.condition for item in report.conditions) == ("A", "B", "C", "D")
    assert all(item.sample_count == 1 for item in report.conditions)

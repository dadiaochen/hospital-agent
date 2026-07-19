from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.demo_runner import (
    EXPECTED_DEMO_CASE_IDS,
    MvpDemoError,
    MvpDemoRunner,
)
from app.agent.runtime_harness import RuntimeE2EHarnessRunner
from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from scripts.seed import (
    seed_agent_audit_example,
    seed_knowledge,
    seed_medication_context,
    seed_pharmacy,
    seed_user_and_family,
)


DEMO_SUITE_PATH = (
    Path(__file__).parents[1] / "app" / "agent" / "demo_scenarios.json"
)
FULL_RUNTIME_SUITE_PATH = (
    Path(__file__).parent / "fixtures" / "runtime_harness_cases.json"
)


@pytest.fixture()
def demo_client() -> Iterator[tuple[TestClient, Session]]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    family = seed_user_and_family(session)
    seed_medication_context(session, family["father"], family["mother"])
    seed_pharmacy(session)
    seed_knowledge(session)
    session.commit()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_demo_suite_contains_only_the_four_presentation_scenarios() -> None:
    suite = MvpDemoRunner.load_suite(DEMO_SUITE_PATH)

    assert tuple(case.case_id for case in suite.trace_cases) == EXPECTED_DEMO_CASE_IDS
    assert tuple(case.input_category for case in suite.trace_cases) == (
        "refill",
        "consultation",
        "reminder",
        "safety",
    )
    assert suite.guard_cases == ()


def test_demo_runner_executes_four_scenarios_and_writes_safe_reports(
    demo_client: tuple[TestClient, Session],
    tmp_path: Path,
) -> None:
    client, session = demo_client
    suite = MvpDemoRunner.load_suite(DEMO_SUITE_PATH)
    runtime_output = RuntimeE2EHarnessRunner(
        client,
        run_key_prefix="pytest-3d-demo",
        environment="pytest_sqlite_deterministic",
    ).run(suite)

    report = MvpDemoRunner.build_report(runtime_output)

    assert report.all_passed is True
    assert report.scenario_pass_rate == 1.0
    assert [item.initial_status for item in report.scenarios] == [
        "needs_confirmation",
        "needs_confirmation",
        "needs_confirmation",
        "blocked",
    ]
    assert [item.final_status for item in report.scenarios] == [
        "completed",
        "completed",
        "completed",
        "blocked",
    ]
    assert all(
        item.external_action_status == "not_submitted" for item in report.scenarios
    )

    json_path = tmp_path / "mvp-demo.json"
    markdown_path = tmp_path / "mvp-demo.md"
    MvpDemoRunner.write_reports(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    serialized = json_path.read_text(encoding="utf-8")
    payload = json.loads(serialized)
    assert payload["all_passed"] is True
    assert "run_id" not in serialized
    assert "member_id" not in serialized
    assert "final_answer" not in serialized
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "3D MVP Demo Verification Report" in markdown
    assert "not a production" in markdown

    family = seed_user_and_family(session)
    seed_medication_context(session, family["father"], family["mother"])
    seed_pharmacy(session)
    seed_knowledge(session)
    seed_agent_audit_example(session, family["user"], family["father"])
    session.commit()


def test_demo_runner_rejects_a_non_presentation_suite() -> None:
    suite = RuntimeE2EHarnessRunner.load_suite(FULL_RUNTIME_SUITE_PATH)

    with pytest.raises(MvpDemoError, match="four fixed scenarios"):
        MvpDemoRunner.validate_suite(suite)

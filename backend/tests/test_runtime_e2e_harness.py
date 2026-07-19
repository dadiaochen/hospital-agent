from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.runtime_harness import RuntimeE2EHarnessRunner
from app.agent.runtime_trace_adapter import (
    RuntimeTraceAdapter,
    RuntimeTraceAdapterError,
)
from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from scripts.seed import (
    seed_knowledge,
    seed_medication_context,
    seed_pharmacy,
    seed_user_and_family,
)


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "runtime_harness_cases.json"
)


@pytest.fixture()
def runtime_harness_client() -> Iterator[tuple[TestClient, Session]]:
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


def test_runtime_suite_defines_core_failure_and_guard_scenarios() -> None:
    suite = RuntimeE2EHarnessRunner.load_suite(FIXTURE_PATH)

    assert len(suite.trace_cases) == 7
    assert len(suite.guard_cases) == 2
    assert {case.input_category for case in suite.trace_cases} == {
        "refill",
        "consultation",
        "reminder",
        "safety",
        "tool_failure",
        "no_source",
        "isolation",
    }
    assert {case.guard_type for case in suite.guard_cases} == {
        "cross_member_rejected",
        "initial_confirmation_rejected",
    }


def test_runtime_harness_drives_real_api_and_generates_reports(
    runtime_harness_client: tuple[TestClient, Session],
    tmp_path: Path,
) -> None:
    client, _ = runtime_harness_client
    suite = RuntimeE2EHarnessRunner.load_suite(FIXTURE_PATH)
    runner = RuntimeE2EHarnessRunner(
        client,
        run_key_prefix="pytest-3c-runtime",
        environment="pytest_sqlite_deterministic",
    )

    output = runner.run(suite)

    assert len(output.trace_results) == 7
    assert len(output.guard_results) == 2
    assert all(result.runtime_contract_passed for result in output.trace_results)
    assert all(result.evaluation.task_success for result in output.trace_results)
    assert all(result.external_action_status == "not_submitted" for result in output.trace_results)
    assert all(result.passed for result in output.guard_results)
    assert output.metrics.case_count == 7
    assert output.metrics.trace_contract_pass_rate == 1.0
    assert output.metrics.guard_pass_rate == 1.0
    assert output.metrics.overall_case_pass_rate == 1.0

    tool_failure = next(
        result
        for result in output.trace_results
        if result.case_id == "3c_tool_failure_empty_self_records"
    )
    assert any(not call.success for call in tool_failure.trace.tool_calls)
    assert tool_failure.evaluation.groundedness == 1.0
    assert tool_failure.trace.final_answer.contains_factual_claims is False

    no_source = next(
        result
        for result in output.trace_results
        if result.case_id == "3c_no_source_refuses_inventory_claim"
    )
    assert no_source.source_ids == ()
    assert no_source.trace.final_answer.contains_factual_claims is False
    assert no_source.evaluation.hallucination_detected is False

    json_report = tmp_path / "runtime-report.json"
    markdown_report = tmp_path / "runtime-report.md"
    runner.write_reports(
        output,
        json_path=json_report,
        markdown_path=markdown_report,
    )

    assert json_report.is_file()
    json_payload = json.loads(json_report.read_text(encoding="utf-8"))
    serialized_report = json.dumps(json_payload, ensure_ascii=False)
    assert json_payload["metrics"]["case_count"] == 7
    assert "member_id" not in serialized_report
    assert "final_answer" not in serialized_report
    assert "run_id" not in serialized_report
    rendered = markdown_report.read_text(encoding="utf-8")
    assert "3C Runtime E2E Evaluation Report" in rendered
    assert "pytest_sqlite_deterministic" in rendered
    assert "not a production" in rendered
    assert "api_key" not in rendered.casefold()
    assert "request_fingerprint" not in rendered.casefold()


def test_trace_adapter_redacts_secrets_and_rejects_member_tampering(
    runtime_harness_client: tuple[TestClient, Session],
) -> None:
    client, _ = runtime_harness_client
    members = client.get("/api/family-members").json()["items"]
    mother_id = next(
        item["id"] for item in members if item["relationship"] == "mother"
    )
    suite = RuntimeE2EHarnessRunner.load_suite(FIXTURE_PATH)
    case = next(
        item
        for item in suite.trace_cases
        if item.case_id == "3c_reminder_mother_confirmed"
    ).to_expected_case(mother_id)
    response = client.post(
        "/api/agent-runs",
        json={
            "member_id": mother_id,
            "idempotency_key": "pytest-3c-adapter-redaction",
            "user_input": "请给妈妈创建每天早晚的用药提醒草稿。",
            "medication_name": "中药颗粒",
        },
    )
    assert response.status_code == 201
    artifacts = response.json()["artifacts"]
    artifacts["api_key"] = "should-never-survive"
    artifacts["debug"] = {
        "raw_conversation": "private conversation",
        "nested": {"provider_raw_response": "private provider output"},
    }

    adapter = RuntimeTraceAdapter()
    adapted = adapter.adapt(case, artifacts)

    assert set(adapted.redacted_paths) == {
        "api_key",
        "debug.raw_conversation",
        "debug.nested.provider_raw_response",
    }
    serialized = adapted.model_dump_json()
    assert "should-never-survive" not in serialized
    assert "private conversation" not in serialized
    with pytest.raises(ValidationError):
        adapted.trace.final_answer.content = "mutated by evaluator"

    tampered = response.json()["artifacts"]
    tampered["tool_evidence_refs"][0]["member_id"] = "another-member"
    with pytest.raises(RuntimeTraceAdapterError, match="member"):
        adapter.adapt(case, tampered)

    inconsistent = response.json()["artifacts"]
    inconsistent["tool_evidence_refs"][0]["source_id"] = "different-source"
    with pytest.raises(RuntimeTraceAdapterError, match="references"):
        adapter.adapt(case, inconsistent)

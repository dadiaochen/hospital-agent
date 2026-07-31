from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.run_trace_schemas import RunTrace
from app.agent.runtime_schemas import PersistedRunArtifacts
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import (
    AgentRun,
    AgentToolCall,
    FamilyMember,
    HealthProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicationReminder,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    User,
)


DEMO_USER_ID = "user-runtime-demo"
OTHER_USER_ID = "user-runtime-other"
FATHER_ID = "member-runtime-father"
MOTHER_ID = "member-runtime-mother"
OTHER_MEMBER_ID = "member-runtime-other"
OTHER_RUN_ID = "run-runtime-other"


@pytest.fixture()
def runtime_client() -> Iterator[tuple[TestClient, Session]]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    _seed_runtime_data(session)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def _start_reminder_request(
    *,
    idempotency_key: str = "runtime-reminder-start",
) -> dict:
    return {
        "member_id": MOTHER_ID,
        "idempotency_key": idempotency_key,
        "user_input": "请给妈妈创建每天早晚的用药提醒。",
        "medication_name": "metformin",
        "city": "Shanghai",
    }


def _continue_request(
    *,
    idempotency_key: str = "runtime-reminder-confirm",
) -> dict:
    return {
        "idempotency_key": idempotency_key,
        "confirmation_message": "我确认创建这份本地提醒草稿。",
        "human_confirmation_granted": True,
    }


def _start_reminder(client: TestClient, *, key: str = "runtime-reminder-start") -> dict:
    response = client.post(
        "/api/agent-runs",
        json=_start_reminder_request(idempotency_key=key),
    )
    assert response.status_code == 201
    return response.json()


def test_initial_run_persists_frozen_audit_artifacts_and_waits_for_confirmation(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, session = runtime_client

    payload = _start_reminder(client)
    run_id = payload["run"]["id"]

    assert payload["run"]["status"] == "needs_confirmation"
    assert payload["run"]["need_human_confirmation"] is True
    assert payload["idempotent_replay"] is False
    assert payload["artifacts"]["evaluation_result"]["task_success"] is True
    assert payload["artifacts"]["run_trace"]["final_answer"][
        "waiting_for_user_confirmation"
    ] is True
    assert session.scalar(select(func.count(MedicationReminder.id))) == 0

    run = session.get(AgentRun, run_id)
    assert run is not None
    artifacts = PersistedRunArtifacts.model_validate(run.raw_state)
    assert artifacts.run_trace.final_answer.content == run.final_answer
    assert artifacts.model_call_trace.success is True
    assert artifacts.model_call_trace.requested_provider == "deterministic"
    assert run.step_count > 0
    assert "role_views" not in run.raw_state
    assert "raw_conversation" not in run.raw_state
    assert "scratchpad" not in run.raw_state
    assert "provider_raw_response" not in run.raw_state
    assert "api_key" not in str(run.raw_state).casefold()

    calls = list(
        session.scalars(
            select(AgentToolCall)
            .where(AgentToolCall.run_id == run_id)
            .order_by(AgentToolCall.created_at)
        )
    )
    refs = artifacts.tool_evidence_refs
    assert [call.tool_name for call in calls] == ["query_medicine_box"]
    assert refs[0].tool_call_id == calls[0].id
    assert calls[0].tool_output["source_name"] == "medicine_box_items"

    replay = client.get(f"/api/agent-runs/{run_id}/artifacts")
    assert replay.status_code == 200
    assert replay.json()["run_trace"] == payload["artifacts"]["run_trace"]
    assert "request_fingerprint" not in replay.json()

    frozen_trace = RunTrace.model_validate(replay.json()["run_trace"])
    with pytest.raises(ValidationError):
        frozen_trace.intent = "refill"


def test_initial_run_is_idempotent_and_rejects_key_reuse_with_new_input(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, session = runtime_client
    first = _start_reminder(client)

    replay = client.post("/api/agent-runs", json=_start_reminder_request())

    assert replay.status_code == 201
    assert replay.json()["run"]["id"] == first["run"]["id"]
    assert replay.json()["idempotent_replay"] is True
    assert session.scalar(select(func.count(AgentRun.id))) == 2
    assert session.scalar(select(func.count(AgentToolCall.id))) == 1

    conflict_request = _start_reminder_request()
    conflict_request["user_input"] = "请创建另一个不同的提醒。"
    conflict = client.post("/api/agent-runs", json=conflict_request)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_confirmation_continuation_keeps_task_and_creates_only_local_draft(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, session = runtime_client
    first = _start_reminder(client)
    first_run_id = first["run"]["id"]
    first_artifacts = first["artifacts"]

    response = client.post(
        f"/api/agent-runs/{first_run_id}/continue",
        json=_continue_request(),
    )

    assert response.status_code == 201
    continued = response.json()
    assert continued["run"]["status"] == "completed"
    assert continued["artifacts"]["task_id"] == first_artifacts["task_id"]
    assert continued["artifacts"]["resumed_from_run_id"] == first_run_id
    assert set(continued["artifacts"]["restored_source_ids"]) == {
        ref["source_id"] for ref in first_artifacts["tool_evidence_refs"]
    }
    assert continued["artifacts"]["external_action_status"] == "not_submitted"
    assert continued["artifacts"]["run_trace"]["final_answer"][
        "human_confirmation_present"
    ] is True
    assert continued["artifacts"]["evaluation_result"]["task_success"] is True

    reminder = session.scalar(select(MedicationReminder))
    assert reminder is not None
    assert reminder.member_id == MOTHER_ID
    assert reminder.status == "draft"
    assert reminder.need_human_confirmation is True
    assert reminder.schedule["_agent_audit"]["external_action_status"] == (
        "not_submitted"
    )

    continued_run_id = continued["run"]["id"]
    assert all(
        ref["run_id"] == continued_run_id
        for ref in continued["artifacts"]["tool_evidence_refs"]
    )
    calls = list(
        session.scalars(
            select(AgentToolCall).where(AgentToolCall.run_id == continued_run_id)
        )
    )
    assert {call.tool_name for call in calls} == {
        "query_medicine_box",
        "create_confirmation_draft",
    }
    assert all(call.success for call in calls)

    replay = client.post(
        f"/api/agent-runs/{first_run_id}/continue",
        json=_continue_request(),
    )
    assert replay.status_code == 201
    assert replay.json()["run"]["id"] == continued_run_id
    assert replay.json()["idempotent_replay"] is True
    assert session.scalar(select(func.count(MedicationReminder.id))) == 1

    conflicting_confirmation = client.post(
        f"/api/agent-runs/{first_run_id}/continue",
        json=_continue_request(idempotency_key="runtime-second-confirmation"),
    )
    assert conflicting_confirmation.status_code == 409
    assert conflicting_confirmation.json()["error"]["code"] == (
        "idempotency_conflict"
    )
    assert session.scalar(select(func.count(MedicationReminder.id))) == 1


def test_runtime_confirmation_cannot_be_bypassed_or_reused_from_wrong_state(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, _ = runtime_client

    bypass = _start_reminder_request(idempotency_key="runtime-bypass")
    bypass["human_confirmation_granted"] = True
    assert client.post("/api/agent-runs", json=bypass).status_code == 422

    first = _start_reminder(client, key="runtime-confirmation-state")
    run_id = first["run"]["id"]
    missing_confirmation = _continue_request(idempotency_key="runtime-missing-confirm")
    missing_confirmation["human_confirmation_granted"] = False
    invalid = client.post(
        f"/api/agent-runs/{run_id}/continue",
        json=missing_confirmation,
    )
    assert invalid.status_code == 422

    completed = client.post(
        f"/api/agent-runs/{run_id}/continue",
        json=_continue_request(idempotency_key="runtime-complete-once"),
    )
    assert completed.status_code == 201
    completed_run_id = completed.json()["run"]["id"]
    wrong_state = client.post(
        f"/api/agent-runs/{completed_run_id}/continue",
        json=_continue_request(idempotency_key="runtime-complete-twice"),
    )
    assert wrong_state.status_code == 409
    assert wrong_state.json()["error"]["code"] == "run_not_continuable"


def test_high_risk_run_is_blocked_and_cannot_be_continued(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, session = runtime_client
    response = client.post(
        "/api/agent-runs",
        json={
            "member_id": FATHER_ID,
            "idempotency_key": "runtime-high-risk",
            "user_input": "我现在胸痛，能不能直接把降压药加量？",
            "medication_name": "amlodipine",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["status"] == "blocked"
    assert payload["artifacts"]["safety_trace"]["blocked"] is True
    assert "dosage_change_request" in payload["artifacts"]["safety_trace"]["flags"]
    assert payload["artifacts"]["evaluation_result"]["safety_recall"] == 1.0
    rag_ref = payload["artifacts"]["rag_source_refs"][0]
    assert rag_ref["source_id"] == (
        "knowledge:knowledge-runtime-safety:knowledge-runtime-safety-chunk"
    )
    assert rag_ref["document_id"] == "knowledge-runtime-safety"
    assert rag_ref["chunk_id"] == "knowledge-runtime-safety-chunk"
    assert rag_ref["member_id"] == FATHER_ID
    assert rag_ref["version"]
    assert rag_ref["purpose"] == "safety_and_workflow_grounding"
    assert session.scalar(select(func.count(MedicationReminder.id))) == 0

    continuation = client.post(
        f"/api/agent-runs/{payload['run']['id']}/continue",
        json=_continue_request(idempotency_key="runtime-blocked-continue"),
    )
    assert continuation.status_code == 409
    assert continuation.json()["error"]["code"] == "run_not_continuable"


def test_runtime_member_and_run_queries_are_user_scoped(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, _ = runtime_client

    cross_member = _start_reminder_request(idempotency_key="runtime-cross-member")
    cross_member["member_id"] = OTHER_MEMBER_ID
    response = client.post("/api/agent-runs", json=cross_member)
    assert response.status_code == 404

    artifacts = client.get(f"/api/agent-runs/{OTHER_RUN_ID}/artifacts")
    assert artifacts.status_code == 404
    assert artifacts.json()["error"]["code"] == "not_found"


def test_workflow_failure_is_normalized_and_the_failed_run_remains_auditable(
    runtime_client: tuple[TestClient, Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = runtime_client

    def fail_workflow(*_args, **_kwargs):
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(
        "app.services.agent_runtime_service.LangGraphAgentWorkflow.run",
        fail_workflow,
    )
    response = client.post(
        "/api/agent-runs",
        json=_start_reminder_request(idempotency_key="runtime-failure"),
    )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "agent_run_failed",
        "message": "agent workflow execution failed",
        "details": None,
    }
    failed = session.scalar(
        select(AgentRun).where(AgentRun.user_goal == "请给妈妈创建每天早晚的用药提醒。")
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.raw_state["error_type"] == "RuntimeError"
    assert "private provider detail" not in str(failed.raw_state)
    assert session.scalar(
        select(func.count(AgentToolCall.id)).where(AgentToolCall.run_id == failed.id)
    ) == 0


def test_openapi_exposes_runtime_run_artifact_and_continuation_contracts(
    runtime_client: tuple[TestClient, Session],
) -> None:
    client, _ = runtime_client

    paths = client.get("/openapi.json").json()["paths"]

    assert "post" in paths["/api/agent-runs"]
    assert "get" in paths["/api/agent-runs/{run_id}/artifacts"]
    assert "post" in paths["/api/agent-runs/{run_id}/continue"]


def _seed_runtime_data(session: Session) -> None:
    demo_user = User(
        id=DEMO_USER_ID,
        name="Runtime Demo User",
        phone=settings.demo_user_phone,
    )
    other_user = User(
        id=OTHER_USER_ID,
        name="Runtime Other User",
        phone="13900000000",
    )
    father = FamilyMember(
        id=FATHER_ID,
        user_id=DEMO_USER_ID,
        name="Father",
        relationship="father",
    )
    mother = FamilyMember(
        id=MOTHER_ID,
        user_id=DEMO_USER_ID,
        name="Mother",
        relationship="mother",
    )
    other_member = FamilyMember(
        id=OTHER_MEMBER_ID,
        user_id=OTHER_USER_ID,
        name="Other Member",
        relationship="self",
    )
    session.add_all([demo_user, other_user, father, mother, other_member])
    session.flush()

    session.add_all(
        [
            HealthProfile(
                id="profile-runtime-father",
                member_id=FATHER_ID,
                chronic_disease_tags=["hypertension"],
                allergies=["none recorded"],
                current_medications=[{"medicine_name": "amlodipine"}],
                safety_notes=["do not change dosage without clinician review"],
            ),
            HealthProfile(
                id="profile-runtime-mother",
                member_id=MOTHER_ID,
                chronic_disease_tags=["type 2 diabetes"],
                allergies=["none recorded"],
                current_medications=[{"medicine_name": "metformin"}],
                safety_notes=["reminders do not change the prescription"],
            ),
            MedicineBoxItem(
                id="box-runtime-father",
                member_id=FATHER_ID,
                medicine_name="amlodipine",
                total_quantity=28,
                remaining_quantity=3,
                dosage="one tablet",
                frequency="once daily",
                purchased_at=date(2026, 7, 1),
                estimated_remaining_days=3,
            ),
            MedicineBoxItem(
                id="box-runtime-mother",
                member_id=MOTHER_ID,
                medicine_name="metformin",
                total_quantity=60,
                remaining_quantity=20,
                dosage="one tablet",
                frequency="twice daily",
                purchased_at=date(2026, 7, 1),
                estimated_remaining_days=10,
            ),
            Prescription(
                id="rx-runtime-father",
                member_id=FATHER_ID,
                prescription_no="RX-RUNTIME-FATHER",
                medicine_items=[{"medicine_name": "amlodipine"}],
                status="valid",
            ),
            Prescription(
                id="rx-runtime-mother",
                member_id=MOTHER_ID,
                prescription_no="RX-RUNTIME-MOTHER",
                medicine_items=[{"medicine_name": "metformin"}],
                status="valid",
            ),
        ]
    )

    pharmacy = Pharmacy(
        id="pharmacy-runtime",
        name="Runtime Pharmacy",
        city="Shanghai",
        supports_delivery=True,
        supports_pickup=True,
    )
    session.add(pharmacy)
    session.add_all(
        [
            PharmacyInventory(
                id="inventory-runtime-amlodipine",
                pharmacy_id=pharmacy.id,
                medicine_name="amlodipine",
                stock_quantity=20,
                delivery_options=["delivery", "pickup"],
            ),
            PharmacyInventory(
                id="inventory-runtime-metformin",
                pharmacy_id=pharmacy.id,
                medicine_name="metformin",
                stock_quantity=30,
                delivery_options=["delivery", "pickup"],
            ),
        ]
    )

    knowledge = KnowledgeDocument(
        id="knowledge-runtime-safety",
        title="Medication safety escalation",
        category="medical_safety",
        source="runtime-test-sop",
        content="Chest pain and dosage changes require urgent human review.",
        safety_level="high",
    )
    session.add(knowledge)
    session.add(
        KnowledgeChunk(
            id="knowledge-runtime-safety-chunk",
            document_id=knowledge.id,
            chunk_index=0,
            content="胸痛、呼吸困难、停药、换药或加量必须转人工和医生处理。",
            keywords=["胸痛", "加量", "停药", "换药", "安全"],
        )
    )
    session.add(
        AgentRun(
            id=OTHER_RUN_ID,
            user_id=OTHER_USER_ID,
            member_id=OTHER_MEMBER_ID,
            user_goal="hidden other-user run",
            status="completed",
            safety_result={},
            raw_state={},
        )
    )
    session.commit()

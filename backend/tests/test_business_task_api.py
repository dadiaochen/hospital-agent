from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    FamilyMember,
    HealthProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicineBoxItem,
    Prescription,
    User,
)


USER_ID = "business-api-user"
FATHER_ID = "business-api-father"
MOTHER_ID = "business-api-mother"


@pytest.fixture()
def business_client() -> Iterator[tuple[TestClient, Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    _seed_business_data(session)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_chronic_care_task_waits_then_resumes_after_confirmation(
    business_client: tuple[TestClient, Session],
) -> None:
    client, session = business_client

    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "chronic_care",
            "member_id": FATHER_ID,
            "user_input": "请整理父亲的降压药续方材料。",
            "input_payload": {
                "action_type": "refill_request",
                "medicine_name": "amlodipine",
            },
            "idempotency_key": "business-refill-1",
        },
    )

    assert response.status_code == 201
    first = response.json()
    assert first["status"] == "needs_confirmation"
    assert first["need_human_confirmation"] is True
    assert first["task"]["member_id"] == FATHER_ID
    assert all(ref["member_id"] == FATHER_ID for ref in first["source_refs"])
    assert first["run_trace"]["run_id"] == first["run_id"]
    assert first["run_summary"]["task_id"] == first["task"]["id"]
    assert first["evaluation_result"]["context_isolation_passed"] is True
    assert first["model_call_trace"]["requested_provider"] == "deterministic"
    assert first["model_call_trace"]["effective_provider"] == "deterministic"
    assert first["model_call_trace"]["success"] is True

    confirmed = client.post(
        f"/api/business-tasks/{first['task']['id']}/confirm",
        json={
            "human_confirmation_granted": True,
            "idempotency_key": "business-refill-1",
        },
    )

    assert confirmed.status_code == 200
    second = confirmed.json()
    assert second["status"] == "completed"
    assert second["need_human_confirmation"] is False
    assert second["confirmation_result"]["external_action_status"] == "not_submitted"
    assert second["task"]["confirmed_at"] is not None
    assert second["model_call_trace"]["purpose"] == (
        "business_chronic_care_final_answer"
    )
    assert session.scalar(select(User).where(User.id == USER_ID)) is not None

    artifacts = client.get(f"/api/business-tasks/{first['task']['id']}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()["run_trace"]["run_id"] == second["run_id"]
    assert artifacts.json()["evaluation_result"]["run_id"] == second["run_id"]


def test_preconsultation_uses_mock_provider_without_claiming_real_data(
    business_client: tuple[TestClient, Session],
) -> None:
    client, _ = business_client

    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "preconsultation",
            "member_id": MOTHER_ID,
            "user_input": "请整理妈妈的复诊材料。",
            "input_payload": {"symptoms": "近期需要复诊", "department_keyword": "内科"},
            "idempotency_key": "business-consultation-1",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "needs_confirmation"
    assert payload["provider_calls"]
    assert payload["model_call_trace"]["success"] is True
    assert payload["model_call_trace"]["purpose"] == (
        "business_preconsultation_final_answer"
    )
    assert all(call["provider_mode"] == "mock" for call in payload["provider_calls"])
    provider_refs = [
        ref
        for ref in payload["source_refs"]
        if ref.get("provider") in {"hospital", "online_consultation"}
    ]
    assert provider_refs
    assert all(ref["source_metadata"]["simulation"] is True for ref in provider_refs)
    assert all(ref["verified"] is False for ref in provider_refs)


def test_health_record_task_requires_confirmation_and_preserves_member_sources(
    business_client: tuple[TestClient, Session],
) -> None:
    client, session = business_client

    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "health_record",
            "member_id": MOTHER_ID,
            "user_input": "请整理这份检查报告并生成健康档案草稿。",
            "input_payload": {
                "document_type": "medical_report",
                "text": "检查报告示例文本",
                "event_type": "report_review",
            },
            "idempotency_key": "business-record-1",
        },
    )

    assert response.status_code == 201
    first = response.json()
    assert first["status"] == "needs_confirmation"
    assert first["confirmation_request"]["tool_name"] == "create_health_record_draft"
    assert all(ref["member_id"] == MOTHER_ID for ref in first["source_refs"])
    assert first["model_call_trace"]["purpose"] == (
        "business_health_record_final_answer"
    )
    assert first["model_call_trace"]["effective_provider"] == "deterministic"

    confirmed = client.post(
        f"/api/business-tasks/{first['task']['id']}/confirm",
        json={
            "human_confirmation_granted": True,
            "idempotency_key": "business-record-1",
        },
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"
    assert session.execute(select(HealthProfile)).scalars().all()


def test_high_risk_request_is_blocked_before_business_tools(
    business_client: tuple[TestClient, Session],
) -> None:
    client, _ = business_client

    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "chronic_care",
            "member_id": FATHER_ID,
            "user_input": "我胸痛，能不能把降压药加量？",
            "input_payload": {
                "action_type": "refill_request",
                "medicine_name": "amlodipine",
            },
            "idempotency_key": "business-safety-1",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "blocked"
    assert {"urgent_symptom", "manual_review_required"}.issubset(
        payload["safety_flags"]
    )
    assert payload["tool_calls"] == []
    assert payload["need_human_confirmation"] is True


def test_provider_mode_is_explicitly_degraded_when_no_sandbox_adapter_exists(
    business_client: tuple[TestClient, Session],
) -> None:
    client, _ = business_client

    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "preconsultation",
            "member_id": MOTHER_ID,
            "user_input": "请查询可用的复诊科室。",
            "input_payload": {},
            "provider_mode": "sandbox",
            "idempotency_key": "business-sandbox-1",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["degraded"] is True
    assert any(
        call["fallback_reason"] == "sandbox_adapter_not_configured"
        for call in payload["provider_calls"]
    )


def test_confirmation_requires_the_original_idempotency_key(
    business_client: tuple[TestClient, Session],
) -> None:
    client, _ = business_client
    first = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "chronic_care",
            "member_id": FATHER_ID,
            "user_input": "请整理续方材料。",
            "input_payload": {
                "action_type": "refill_request",
                "medicine_name": "amlodipine",
            },
            "idempotency_key": "business-key-1",
        },
    ).json()

    wrong_key = client.post(
        f"/api/business-tasks/{first['task']['id']}/confirm",
        json={
            "human_confirmation_granted": True,
            "idempotency_key": "business-key-wrong",
        },
    )

    assert wrong_key.status_code == 409
    assert wrong_key.json()["error"]["code"] == "idempotency_conflict"


def test_initial_business_request_cannot_bypass_confirmation_schema(
    business_client: tuple[TestClient, Session],
) -> None:
    client, _ = business_client
    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "chronic_care",
            "member_id": FATHER_ID,
            "user_input": "请创建提醒。",
            "input_payload": {
                "action_type": "reminder_create",
                "medicine_name": "amlodipine",
                "schedule": "每天早上",
            },
            "human_confirmation_granted": True,
            "idempotency_key": "business-bypass-1",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def _seed_business_data(session: Session) -> None:
    user = User(id=USER_ID, name="Business API User", phone=settings.demo_user_phone)
    father = FamilyMember(
        id=FATHER_ID,
        user_id=USER_ID,
        name="父亲",
        relationship="father",
        birthday=date(1965, 8, 20),
    )
    mother = FamilyMember(
        id=MOTHER_ID,
        user_id=USER_ID,
        name="母亲",
        relationship="mother",
        birthday=date(1968, 3, 12),
    )
    session.add_all([user, father, mother])
    session.flush()

    session.add_all(
        [
            HealthProfile(
                id="business-profile-father",
                member_id=FATHER_ID,
                chronic_disease_tags=["hypertension"],
                allergies=["no confirmed allergy"],
                current_medications=[{"medicine_name": "amlodipine"}],
                safety_notes=["dose changes require doctor review"],
            ),
            HealthProfile(
                id="business-profile-mother",
                member_id=MOTHER_ID,
                chronic_disease_tags=["follow_up"],
                allergies=["no confirmed allergy"],
                current_medications=[{"medicine_name": "metformin"}],
                safety_notes=["submission requires confirmation"],
            ),
            MedicineBoxItem(
                id="business-box-father",
                member_id=FATHER_ID,
                medicine_name="amlodipine",
                total_quantity=28,
                remaining_quantity=3,
                dosage="按处方",
                frequency="每日一次",
                estimated_remaining_days=3,
            ),
            Prescription(
                id="business-rx-father",
                member_id=FATHER_ID,
                prescription_no="BUSINESS-RX-001",
                medicine_items=[{"medicine_name": "amlodipine"}],
                status="valid",
                doctor_confirmation_required=True,
            ),
        ]
    )

    document = KnowledgeDocument(
        id="business-knowledge-confirmation",
        title="Human confirmation rule",
        category="human_confirmation",
        source="business-test-sop:v1",
        content="续方、提醒和档案草稿都必须等待用户确认。",
        safety_level="general",
    )
    session.add(document)
    session.flush()
    session.add(
        KnowledgeChunk(
            id="business-knowledge-confirmation-chunk",
            document_id=document.id,
            chunk_index=0,
            content=document.content,
            keywords=["续方", "提醒", "确认", "报告"],
        )
    )
    session.commit()

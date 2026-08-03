from datetime import date, datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import (
    AgentRun,
    AgentToolCall,
    FamilyMember,
    HealthProfile,
    MedicalDocument,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    PurchaseRecord,
    User,
)


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, dict[str, str]]]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    ids = _seed_api_data(session)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, ids
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_family_and_medication_reads_are_scoped_to_demo_user(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = api_client

    members = client.get("/api/family-members")
    assert members.status_code == 200
    assert [item["id"] for item in members.json()["items"]] == [ids["father_id"]]

    profile = client.get(f"/api/family-members/{ids['father_id']}/health-profile")
    assert profile.status_code == 200
    assert profile.json()["profile"]["allergies"] == ["none recorded"]

    medicine_box = client.get(f"/api/family-members/{ids['father_id']}/medicine-box")
    assert medicine_box.status_code == 200
    assert medicine_box.json()["items"][0]["medicine_name"] == "amlodipine"

    prescriptions = client.get(f"/api/family-members/{ids['father_id']}/prescriptions")
    assert prescriptions.status_code == 200
    assert prescriptions.json()["items"][0]["prescription_no"] == "RX-API-001"

    purchases = client.get(f"/api/family-members/{ids['father_id']}/purchase-records")
    assert purchases.status_code == 200
    assert purchases.json()["items"][0]["medicine_name"] == "amlodipine"


def test_report_reads_follow_the_frozen_detail_contract_and_member_scope(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = api_client

    reports = client.get(f"/api/family-members/{ids['father_id']}/reports")
    assert reports.status_code == 200
    assert reports.json()["items"][0] == {
        "id": ids["report_id"],
        "member_id": ids["father_id"],
        "title": "Father sample health report",
        "document_type": "checkup_report",
        "status": "ready",
        "reported_at": reports.json()["items"][0]["reported_at"],
        "updated_at": reports.json()["items"][0]["updated_at"],
        "document_version": "1.0",
        "source_name": "Father sample health report",
        "metric_count": 1,
    }

    detail = client.get(
        f"/api/family-members/{ids['father_id']}/reports/{ids['report_id']}"
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["report"]["member_id"] == ids["father_id"]
    assert payload["metrics"][0]["name"] == "空腹血糖"
    assert payload["metrics"][0]["interpretation_status"] == "within_range"
    assert payload["metrics"][0]["source_ref"] == payload["sources"][0]["id"]
    assert payload["safety"]["requires_professional_review"] is True
    assert "诊断" in payload["summary"]["disclaimer"]

    cross_member = client.get(
        f"/api/family-members/{ids['other_member_id']}/reports/{ids['report_id']}"
    )
    assert cross_member.status_code == 404
    assert cross_member.json()["error"]["code"] == "not_found"


def test_cross_member_reads_return_a_uniform_not_found_error(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = api_client

    response = client.get(f"/api/family-members/{ids['other_member_id']}/medicine-box")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "family member was not found", "details": None}
    }


def test_pharmacy_inventory_requires_a_filter_and_returns_candidates(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api_client

    missing_filter = client.get("/api/pharmacy-inventory")
    assert missing_filter.status_code == 422
    assert missing_filter.json()["error"]["code"] == "validation_error"

    empty_filter = client.get("/api/pharmacy-inventory", params={"medicine_name": ""})
    assert empty_filter.status_code == 422
    assert empty_filter.json()["error"]["code"] == "validation_error"

    response = client.get("/api/pharmacy-inventory", params={"medicine_name": "amlodipine"})
    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "inventory_id": "inventory-api",
            "pharmacy_id": "pharmacy-api",
            "pharmacy_name": "Demo Pharmacy",
            "city": "Demo City",
            "address": "1 Demo Road",
            "supports_delivery": True,
            "supports_pickup": True,
            "contact_phone": "010-00000000",
            "medicine_name": "amlodipine",
            "stock_quantity": 12,
            "delivery_options": ["delivery", "pickup"],
            "safety_note": "inventory is a candidate, not an order",
        }
    ]


def test_agent_audit_reads_are_scoped_and_hide_raw_state(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = api_client

    runs = client.get("/api/agent-runs", params={"member_id": ids["father_id"]})
    assert runs.status_code == 200
    assert runs.json()["items"][0]["id"] == ids["run_id"]
    assert "raw_state" not in runs.json()["items"][0]

    tool_calls = client.get(f"/api/agent-runs/{ids['run_id']}/tool-calls")
    assert tool_calls.status_code == 200
    assert tool_calls.json()["items"][0]["tool_name"] == "query_medicine_box"

    other_run = client.get(f"/api/agent-runs/{ids['other_run_id']}")
    assert other_run.status_code == 404
    assert other_run.json()["error"]["code"] == "not_found"


def test_openapi_includes_the_implemented_read_endpoints(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/family-members" in paths
    assert "/api/family-members/{member_id}/medicine-box" in paths
    assert "/api/pharmacy-inventory" in paths
    assert "/api/agent-runs/{run_id}/tool-calls" in paths
    assert "/api/family-members/{member_id}/reports" in paths
    assert "/api/family-members/{member_id}/reports/{report_id}" in paths


def _seed_api_data(session: Session) -> dict[str, str]:
    demo_user = User(id="user-demo", name="Demo User", phone="13800000001")
    other_user = User(id="user-other", name="Other User", phone="13900000000")
    father = FamilyMember(
        id="member-father",
        user_id=demo_user.id,
        name="Father",
        relationship="father",
        birthday=date(1965, 8, 20),
    )
    other_member = FamilyMember(
        id="member-other",
        user_id=other_user.id,
        name="Other Member",
        relationship="self",
    )
    session.add_all([demo_user, other_user, father, other_member])
    session.add(
        HealthProfile(
            id="profile-father",
            member_id=father.id,
            chronic_disease_tags=["hypertension"],
            allergies=["none recorded"],
            current_medications=[{"medicine_name": "amlodipine"}],
            health_notes="Demo health profile",
            safety_notes=["do not change dosage"],
        )
    )
    report = MedicalDocument(
        id="report-api",
        user_id=demo_user.id,
        member_id=father.id,
        document_type="checkup_report",
        title="Father sample health report",
        source_text="Synthetic report source text",
        status="parsed",
        extracted_content={
            "summary": {
                "text": "报告中的一项指标已整理。",
                "disclaimer": "这是信息整理，不是诊断。",
            },
            "metrics": [
                {
                    "id": "metric-api",
                    "name": "空腹血糖",
                    "value": "5.6",
                    "unit": "mmol/L",
                    "reference_range": {
                        "low": 3.9,
                        "high": 6.1,
                        "display_text": "3.9–6.1 mmol/L",
                    },
                    "interpretation_status": "within_range",
                    "trend": "unknown",
                    "explanation": "结果与报告提供的参考范围相符。",
                }
            ],
            "sections": [
                {
                    "id": "section-api",
                    "title": "检查说明",
                    "content": "这是测试用报告说明。",
                }
            ],
        },
        document_version="1.0",
        need_human_confirmation=True,
    )
    session.add(report)
    session.add(
        MedicineBoxItem(
            id="box-father",
            member_id=father.id,
            medicine_name="amlodipine",
            specification="5mg*28",
            total_quantity=28,
            remaining_quantity=3,
            dosage="one tablet",
            frequency="once daily",
            estimated_remaining_days=3,
            safety_note="prepare refill materials only",
        )
    )
    prescription = Prescription(
        id="prescription-api",
        member_id=father.id,
        prescription_no="RX-API-001",
        doctor_name="Demo Doctor",
        hospital_name="Demo Hospital",
        doctor_diagnosis_summary="existing prescription record",
        medicine_items=[{"medicine_name": "amlodipine"}],
        issued_at=date(2026, 1, 1),
        expires_at=date(2026, 12, 31),
        status="valid",
        doctor_confirmation_required=True,
        safety_note="no dosage changes",
    )
    session.add(prescription)
    session.add(
        PurchaseRecord(
            id="purchase-api",
            member_id=father.id,
            prescription_id=prescription.id,
            medicine_name="amlodipine",
            quantity=28,
            dosage="one tablet",
            frequency="once daily",
            pharmacy_name="Demo Pharmacy",
            purchased_at=date(2026, 1, 2),
            purchase_channel="demo",
        )
    )
    pharmacy = Pharmacy(
        id="pharmacy-api",
        name="Demo Pharmacy",
        city="Demo City",
        address="1 Demo Road",
        supports_delivery=True,
        supports_pickup=True,
        contact_phone="010-00000000",
    )
    session.add(pharmacy)
    session.add(
        PharmacyInventory(
            id="inventory-api",
            pharmacy_id=pharmacy.id,
            medicine_name="amlodipine",
            stock_quantity=12,
            delivery_options=["delivery", "pickup"],
            safety_note="inventory is a candidate, not an order",
        )
    )
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id="run-api",
        user_id=demo_user.id,
        member_id=father.id,
        user_goal="prepare refill materials",
        intent="refill",
        status="completed",
        final_answer="draft prepared",
        need_human_confirmation=True,
        safety_result={"allowed": True},
        raw_state={"internal": "must not be returned"},
        started_at=now,
        ended_at=now,
        duration_ms=10,
        step_count=2,
        task_success=True,
        groundedness_score=1.0,
        hallucination_flag=False,
        human_confirmation_rate=1.0,
    )
    other_run = AgentRun(
        id="run-other",
        user_id=other_user.id,
        member_id=other_member.id,
        user_goal="other user run",
        status="completed",
        safety_result={},
    )
    session.add_all([run, other_run])
    session.add(
        AgentToolCall(
            id="tool-call-api",
            run_id=run.id,
            agent_role="RefillAgent",
            tool_name="query_medicine_box",
            tool_input={"member_id": father.id},
            tool_output={"source_id": "medicine_box:box-father"},
            latency_ms=2,
            success=True,
            schema_valid=True,
        )
    )
    session.commit()
    return {
        "father_id": father.id,
        "other_member_id": other_member.id,
        "report_id": report.id,
        "run_id": run.id,
        "other_run_id": other_run.id,
    }

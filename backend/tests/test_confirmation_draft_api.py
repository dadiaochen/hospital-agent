from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import (
    ConsultationDraft,
    FamilyMember,
    MedicationReminder,
    MedicineBoxItem,
    Pharmacy,
    Prescription,
    PurchasePlan,
    RefillPlan,
    User,
)
from app.models.base import utc_now


DEMO_USER_ID = "user-draft-api"
OTHER_USER_ID = "user-draft-other"
FATHER_ID = "member-draft-father"
MOTHER_ID = "member-draft-mother"
OTHER_MEMBER_ID = "member-draft-other"
FATHER_RX_ID = "rx-draft-father"
MOTHER_RX_ID = "rx-draft-mother"
MOTHER_BOX_ID = "box-draft-mother"
PHARMACY_ID = "pharmacy-draft"
OTHER_DRAFT_ID = "draft-other-user"


@pytest.fixture()
def draft_client() -> Iterator[tuple[TestClient, Session]]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    _seed_draft_api_data(session)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


def _create_request(
    *,
    draft_type: str = "refill_request",
    member_id: str = FATHER_ID,
    idempotency_key: str = "api-refill-001",
    summary: str = "Prepare a local refill materials draft for review.",
    payload: dict | None = None,
    confirmed: bool = True,
) -> dict:
    return {
        "member_id": member_id,
        "draft_type": draft_type,
        "idempotency_key": idempotency_key,
        "summary": summary,
        "payload": payload
        or {
            "medicine_name": "amlodipine tablets",
            "prescription_id": FATHER_RX_ID,
            "remaining_days": 3,
            "plan_detail": {"purpose": "refill_materials_only"},
        },
        "human_confirmation_granted": confirmed,
    }


def _decision_request(key: str, *, present: bool = True) -> dict:
    return {
        "idempotency_key": key,
        "human_confirmation_present": present,
        "note": "Local decision only; do not submit an external action.",
    }


def _post_draft(client: TestClient, **overrides) -> dict:
    response = client.post(
        "/api/confirmation-drafts",
        json=_create_request(**overrides),
    )
    assert response.status_code == 201
    return response.json()


def test_create_requires_confirmation_before_database_write(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, session = draft_client

    response = client.post(
        "/api/confirmation-drafts",
        json=_create_request(confirmed=False),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "human_confirmation_required"
    count = session.scalar(
        select(func.count())
        .select_from(RefillPlan)
        .where(RefillPlan.member_id == FATHER_ID)
    )
    assert count == 0


def test_create_is_idempotent_and_never_claims_external_submission(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client

    first = _post_draft(client)
    replay = _post_draft(client)

    assert first["draft_id"] == replay["draft_id"]
    assert first["status"] == "draft"
    assert first["confirmed_at"] is not None
    assert first["resolved_at"] is None
    assert first["external_action_status"] == "not_submitted"
    assert first["content"]["medicine_name"] == "amlodipine tablets"
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True


@pytest.mark.parametrize(
    ("draft_type", "member_id", "payload", "model"),
    [
        (
            "consultation_request",
            MOTHER_ID,
            {
                "prescription_id": MOTHER_RX_ID,
                "draft_content": "Organize follow-up materials.",
                "material_summary": {"purpose": "follow_up_materials"},
            },
            ConsultationDraft,
        ),
        (
            "pharmacy_option",
            FATHER_ID,
            {
                "medicine_name": "amlodipine tablets",
                "pharmacy_id": PHARMACY_ID,
                "delivery_option": "pickup",
                "plan_detail": {"purpose": "candidate_only"},
            },
            PurchasePlan,
        ),
        (
            "reminder_create",
            MOTHER_ID,
            {
                "medicine_name": "TCM granules",
                "medicine_box_item_id": MOTHER_BOX_ID,
                "schedule": {"times": ["08:00", "20:00"]},
            },
            MedicationReminder,
        ),
    ],
)
def test_api_creates_each_supported_local_draft_type(
    draft_client: tuple[TestClient, Session],
    draft_type: str,
    member_id: str,
    payload: dict,
    model,
) -> None:
    client, session = draft_client

    result = _post_draft(
        client,
        draft_type=draft_type,
        member_id=member_id,
        idempotency_key=f"api-{draft_type}",
        payload=payload,
    )

    assert result["draft_type"] == draft_type
    assert result["status"] == "draft"
    assert result["external_action_status"] == "not_submitted"
    assert session.scalar(select(func.count()).select_from(model)) == 1


def test_list_and_detail_are_scoped_to_demo_user(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client
    created = _post_draft(client)

    listed = client.get(
        "/api/confirmation-drafts",
        params={"member_id": FATHER_ID, "status": "draft"},
    )
    hidden = client.get(
        f"/api/confirmation-drafts/refill_request/{OTHER_DRAFT_ID}"
    )
    cross_member_filter = client.get(
        "/api/confirmation-drafts",
        params={"member_id": OTHER_MEMBER_ID},
    )

    assert listed.status_code == 200
    assert [item["draft_id"] for item in listed.json()["items"]] == [
        created["draft_id"]
    ]
    assert hidden.status_code == 404
    assert cross_member_filter.status_code == 404


def test_confirm_is_idempotent_and_keeps_external_action_unsubmitted(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, session = draft_client
    created = _post_draft(client)
    path = (
        f"/api/confirmation-drafts/refill_request/{created['draft_id']}/confirm"
    )

    missing_decision = client.post(
        path,
        json=_decision_request("confirm-refill", present=False),
    )
    confirmed = client.post(path, json=_decision_request("confirm-refill"))
    replay = client.post(path, json=_decision_request("confirm-refill"))

    assert missing_decision.status_code == 409
    assert missing_decision.json()["error"]["code"] == "human_confirmation_required"
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["resolved_at"] is not None
    assert confirmed.json()["external_action_status"] == "not_submitted"
    assert confirmed.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True

    row = session.get(RefillPlan, created["draft_id"])
    assert row is not None
    assert row.status == "confirmed"
    assert len(row.plan_detail["_agent_audit"]["status_transitions"]) == 1


def test_rejected_draft_cannot_transition_to_confirmed(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client
    created = _post_draft(client, idempotency_key="api-reject-001")
    base = f"/api/confirmation-drafts/refill_request/{created['draft_id']}"

    rejected = client.post(
        f"{base}/reject",
        json=_decision_request("reject-refill"),
    )
    invalid_confirm = client.post(
        f"{base}/confirm",
        json=_decision_request("confirm-after-reject"),
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["external_action_status"] == "not_submitted"
    assert invalid_confirm.status_code == 409
    assert invalid_confirm.json()["error"]["code"] == "invalid_state_transition"


def test_cross_member_reference_and_forbidden_medical_action_are_rejected(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client

    cross_member = client.post(
        "/api/confirmation-drafts",
        json=_create_request(
            payload={
                "medicine_name": "amlodipine tablets",
                "prescription_id": MOTHER_RX_ID,
            }
        ),
    )
    unsafe = client.post(
        "/api/confirmation-drafts",
        json=_create_request(
            idempotency_key="api-unsafe-001",
            summary="Increase dose and submit the refill automatically.",
        ),
    )

    assert cross_member.status_code == 404
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "medical_safety_violation"


def test_optional_run_reference_must_match_demo_user_and_member(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client
    request = _create_request(idempotency_key="api-run-scope-001")
    request["run_id"] = "missing-or-unscoped-run"

    response = client.post("/api/confirmation-drafts", json=request)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_openapi_exposes_confirmation_draft_state_machine(
    draft_client: tuple[TestClient, Session],
) -> None:
    client, _ = draft_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/confirmation-drafts" in paths
    assert "/api/confirmation-drafts/{draft_type}/{draft_id}" in paths
    assert "/api/confirmation-drafts/{draft_type}/{draft_id}/confirm" in paths
    assert "/api/confirmation-drafts/{draft_type}/{draft_id}/reject" in paths


def _seed_draft_api_data(session: Session) -> None:
    demo_user = User(
        id=DEMO_USER_ID,
        name="Draft API Demo User",
        phone=settings.demo_user_phone,
    )
    other_user = User(
        id=OTHER_USER_ID,
        name="Other User",
        phone="13900000000",
    )
    father = FamilyMember(
        id=FATHER_ID,
        user_id=demo_user.id,
        name="Father",
        relationship="father",
    )
    mother = FamilyMember(
        id=MOTHER_ID,
        user_id=demo_user.id,
        name="Mother",
        relationship="mother",
    )
    other_member = FamilyMember(
        id=OTHER_MEMBER_ID,
        user_id=other_user.id,
        name="Other Member",
        relationship="self",
    )
    session.add_all([demo_user, other_user, father, mother, other_member])
    session.flush()
    session.add_all(
        [
            Prescription(
                id=FATHER_RX_ID,
                member_id=FATHER_ID,
                prescription_no="RX-DRAFT-FATHER",
                medicine_items=[{"medicine_name": "amlodipine tablets"}],
            ),
            Prescription(
                id=MOTHER_RX_ID,
                member_id=MOTHER_ID,
                prescription_no="RX-DRAFT-MOTHER",
                medicine_items=[{"medicine_name": "TCM granules"}],
            ),
            MedicineBoxItem(
                id=MOTHER_BOX_ID,
                member_id=MOTHER_ID,
                medicine_name="TCM granules",
                total_quantity=14,
                remaining_quantity=6,
                dosage="1 pack",
                frequency="twice daily",
                purchased_at=date.today(),
            ),
            Pharmacy(
                id=PHARMACY_ID,
                name="Draft API Pharmacy",
                city="Shanghai",
            ),
            RefillPlan(
                id=OTHER_DRAFT_ID,
                member_id=OTHER_MEMBER_ID,
                medicine_name="hidden medicine",
                plan_detail={"_agent_audit": {"external_action_status": "not_submitted"}},
                status="draft",
                need_human_confirmation=True,
                confirmed_at=utc_now(),
                confirmation_note="Local draft only; no external action was submitted.",
            ),
        ]
    )
    session.commit()

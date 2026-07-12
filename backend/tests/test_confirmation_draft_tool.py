from __future__ import annotations

import subprocess
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
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
from app.tools.db_tools import create_db_tool_registry
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolExecutionContext


USER_ID = "user-demo"
FATHER_ID = "member-father"
MOTHER_ID = "member-mother"
FATHER_RX_ID = "rx-father"
MOTHER_RX_ID = "rx-mother"
MOTHER_BOX_ID = "box-mother"
PHARMACY_ID = "pharmacy-demo"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with TestingSession() as session:
        _seed_confirmation_data(session)
        yield session


@pytest.fixture()
def registry(db_session: Session) -> ToolRegistry:
    return create_db_tool_registry(db_session, include_confirmation_tools=True)


def _context(
    role: str,
    member_id: str,
    *,
    user_id: str = USER_ID,
    confirmed: bool = True,
    run_id: str = "run-confirmation",
) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id=run_id,
        task_id="task-confirmation",
        user_id=user_id,
        member_id=member_id,
        agent_role=role,
        allowed_tools=["create_confirmation_draft"],
        human_confirmation_granted=confirmed,
    )


def _input(
    *,
    action_type: str = "refill_request",
    member_id: str = FATHER_ID,
    idempotency_key: str = "idem-refill-001",
    summary: str = "Prepare a local refill materials draft for review.",
    payload: dict | None = None,
) -> dict:
    return {
        "user_id": USER_ID,
        "member_id": member_id,
        "action_type": action_type,
        "idempotency_key": idempotency_key,
        "summary": summary,
        "payload": payload
        or {
            "medicine_name": "amlodipine tablets",
            "prescription_id": FATHER_RX_ID,
            "remaining_days": 3,
            "plan_detail": {"purpose": "refill_materials_only"},
        },
    }


def _seed_confirmation_data(session: Session) -> None:
    session.add(User(id=USER_ID, name="Demo User", phone="13800000000"))
    session.add_all(
        [
            FamilyMember(
                id=FATHER_ID,
                user_id=USER_ID,
                name="Father",
                relationship="father",
            ),
            FamilyMember(
                id=MOTHER_ID,
                user_id=USER_ID,
                name="Mother",
                relationship="mother",
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            Prescription(
                id=FATHER_RX_ID,
                member_id=FATHER_ID,
                prescription_no="RX-FATHER",
                medicine_items=[{"medicine_name": "amlodipine tablets"}],
            ),
            Prescription(
                id=MOTHER_RX_ID,
                member_id=MOTHER_ID,
                prescription_no="RX-MOTHER",
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
                name="Demo Pharmacy",
                city="Shanghai",
            ),
        ]
    )
    session.commit()


def test_confirmation_tool_is_registered_only_when_explicitly_enabled(
    db_session: Session,
) -> None:
    read_registry = create_db_tool_registry(db_session)
    write_registry = create_db_tool_registry(
        db_session,
        include_confirmation_tools=True,
    )

    assert "create_confirmation_draft" not in read_registry.list_tool_names()
    spec = write_registry.get_tool("create_confirmation_draft")
    assert spec.read_only is False
    assert spec.requires_human_confirmation is True


def test_unconfirmed_call_is_blocked_without_database_write(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID, confirmed=False),
    )

    assert result.success is False
    assert result.error_type == "human_confirmation_required"
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 0


def test_confirmed_refill_call_creates_local_draft_only(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID),
    )

    output = result.tool_output
    assert result.success is True
    assert output is not None
    assert output["status"] == "draft"
    assert output["external_action_status"] == "not_submitted"
    assert output["local_confirmation_recorded"] is True
    row = db_session.get(RefillPlan, output["draft_id"])
    assert row is not None
    assert row.status == "draft"
    assert row.need_human_confirmation is True
    assert row.confirmed_at is not None
    assert "no external action" in (row.confirmation_note or "").lower()
    assert row.plan_detail["_agent_audit"]["created_by_run_id"] == "run-confirmation"
    assert "refill materials" in row.plan_detail["_agent_audit"]["summary"]


def test_idempotency_key_returns_existing_draft_without_duplicate(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    first = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID, run_id="run-first"),
    )
    second = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID, run_id="run-retry"),
    )

    assert first.success is True and second.success is True
    assert first.tool_output["draft_id"] == second.tool_output["draft_id"]
    assert second.tool_output["idempotent_replay"] is True
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 1


@pytest.mark.parametrize(
    ("action_type", "role", "member_id", "payload", "model"),
    [
        (
            "consultation_request",
            "RefillAgent",
            MOTHER_ID,
            {
                "prescription_id": MOTHER_RX_ID,
                "material_summary": {"purpose": "follow_up_materials"},
            },
            ConsultationDraft,
        ),
        (
            "pharmacy_option",
            "PharmacyAgent",
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
            "ReminderAgent",
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
def test_supported_draft_types_write_only_local_draft_rows(
    registry: ToolRegistry,
    db_session: Session,
    action_type: str,
    role: str,
    member_id: str,
    payload: dict,
    model,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(
            action_type=action_type,
            member_id=member_id,
            idempotency_key=f"idem-{action_type}",
            payload=payload,
        ),
        _context(role, member_id),
    )

    assert result.success is True
    assert result.tool_output["status"] == "draft"
    assert result.tool_output["external_action_status"] == "not_submitted"
    assert db_session.scalar(select(func.count()).select_from(model)) == 1


def test_member_context_mismatch_is_rejected_without_write(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(member_id=MOTHER_ID),
        _context("RefillAgent", FATHER_ID),
    )

    assert result.success is False
    assert result.error_type == "context_isolation_violation"
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 0


def test_user_context_mismatch_is_rejected_without_write(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID, user_id="user-other"),
    )

    assert result.success is False
    assert result.error_type == "context_isolation_violation"
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 0


def test_action_role_mismatch_is_rejected(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(
            action_type="pharmacy_option",
            payload={"medicine_name": "amlodipine tablets"},
        ),
        _context("RefillAgent", FATHER_ID),
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
    assert db_session.scalar(select(func.count()).select_from(PurchasePlan)) == 0


def test_cross_member_prescription_reference_is_rejected(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(payload={"medicine_name": "amlodipine", "prescription_id": MOTHER_RX_ID}),
        _context("RefillAgent", FATHER_ID),
    )

    assert result.success is False
    assert result.error_type == "related_record_not_found"
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 0


def test_forbidden_medical_action_language_is_rejected(
    registry: ToolRegistry,
    db_session: Session,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(summary="Increase dose and prepare the refill automatically."),
        _context("RefillAgent", FATHER_ID),
    )

    assert result.success is False
    assert result.error_type == "medical_safety_violation"
    assert result.fallback_action == "route_to_safety_agent"
    assert db_session.scalar(select(func.count()).select_from(RefillPlan)) == 0


def test_tool_result_maps_to_trace_without_external_success_claim(
    registry: ToolRegistry,
) -> None:
    result = registry.call(
        "create_confirmation_draft",
        _input(),
        _context("RefillAgent", FATHER_ID),
    )

    trace = result.to_tool_call_trace()
    rendered = str(result.tool_output).lower()
    assert trace.tool_name == "create_confirmation_draft"
    assert trace.member_id == FATHER_ID
    assert trace.evidence_present is True
    assert "order placed" not in rendered
    assert "submitted to hospital" not in rendered
    assert "auto_prescribe" not in rendered


def test_2d2_does_not_modify_models_migrations_seed_api_or_frontend() -> None:
    project_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            "backend/app/models",
            "backend/alembic",
            "scripts/seed.py",
            "backend/app/api",
            "frontend",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("git diff unavailable in this test environment")

    assert [line for line in completed.stdout.splitlines() if line.strip()] == []

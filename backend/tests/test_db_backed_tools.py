from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import subprocess
from typing import Any

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.core.database import Base
from app.models import (
    FamilyMember,
    HealthProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    PurchaseRecord,
    User,
)
from app.services.agent_tool_query_service import (
    get_health_profile_context,
    get_medicine_box_context,
    get_pharmacy_inventory_context,
    get_prescription_context,
    search_safety_knowledge_context,
)
from app.tools.db_tools import HealthProfileInput, create_db_tool_registry
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolContractModel, ToolExecutionContext, ToolSpec


USER_ID = "user-seed"
FATHER_ID = "member-father"
MOTHER_ID = "member-mother"


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with TestingSession() as session:
        seed_db_tool_data(session)
        yield session


@pytest.fixture()
def registry(db_session: Session) -> ToolRegistry:
    return create_db_tool_registry(db_session)


def context_for(
    agent_role: str,
    member_id: str = FATHER_ID,
    allowed_tools: list[str] | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id=f"run-{agent_role.lower()}",
        task_id=f"task-{agent_role.lower()}",
        agent_role=agent_role,
        user_id=USER_ID,
        member_id=member_id,
        allowed_tools=allowed_tools or [],
    )


def seed_db_tool_data(session: Session) -> None:
    today = date.today()
    user = User(id=USER_ID, name="Yuxi", phone="13800000001", is_active=True)
    father = FamilyMember(
        id=FATHER_ID,
        user_id=USER_ID,
        name="Father",
        relationship="father",
        gender="male",
        birthday=date(1965, 8, 20),
        default_address="Shanghai Pudong",
    )
    mother = FamilyMember(
        id=MOTHER_ID,
        user_id=USER_ID,
        name="Mother",
        relationship="mother",
        gender="female",
        birthday=date(1968, 3, 12),
        default_address="Shanghai Xuhui",
    )
    session.add_all([user, father, mother])
    session.flush()

    session.add_all(
        [
            HealthProfile(
                id="profile-father",
                member_id=FATHER_ID,
                chronic_disease_tags=["hypertension", "long_term_medication"],
                allergies=["no confirmed drug allergy record"],
                current_medications=[
                    {
                        "medicine_name": "amlodipine besylate tablets",
                        "usage": "take according to doctor prescription",
                    }
                ],
                health_notes="Doctor-managed hypertension refill scenario.",
                safety_notes=[
                    "Do not provide self-directed dose changes or prescription edits."
                ],
            ),
            HealthProfile(
                id="profile-mother",
                member_id=MOTHER_ID,
                chronic_disease_tags=["sleep_follow_up", "tcm_follow_up"],
                allergies=["no confirmed drug allergy record"],
                current_medications=[
                    {
                        "medicine_name": "TCM granules",
                        "usage": "take according to previous doctor prescription",
                    }
                ],
                health_notes="TCM follow-up material organization only.",
                safety_notes=["Submission requires user confirmation."],
            ),
        ]
    )

    father_rx = Prescription(
        id="rx-father-bp",
        member_id=FATHER_ID,
        prescription_no="RX-FATHER-BP-001",
        doctor_name="Dr. Wang",
        hospital_name="Demo Internet Hospital",
        doctor_diagnosis_summary="Doctor record: hypertension long-term management.",
        medicine_items=[
            {
                "medicine_name": "amlodipine besylate tablets",
                "specification": "5mg*28 tablets",
                "dosage": "1 tablet each time",
                "frequency": "once daily",
            }
        ],
        issued_at=today - timedelta(days=25),
        expires_at=today + timedelta(days=5),
        status="valid",
        doctor_confirmation_required=True,
        safety_note="Refill and dosage decisions require doctor confirmation.",
    )
    mother_rx = Prescription(
        id="rx-mother-tcm",
        member_id=MOTHER_ID,
        prescription_no="RX-MOTHER-TCM-001",
        doctor_name="Dr. Li",
        hospital_name="Demo TCM Internet Hospital",
        doctor_diagnosis_summary="Doctor record: sleep follow-up TCM treatment.",
        medicine_items=[
            {
                "medicine_name": "TCM granules",
                "specification": "7 packs",
                "dosage": "1 pack each time",
                "frequency": "morning and evening",
            }
        ],
        issued_at=today - timedelta(days=5),
        expires_at=today + timedelta(days=10),
        status="valid",
        doctor_confirmation_required=True,
        safety_note="Follow-up material is for doctor review only.",
    )
    session.add_all([father_rx, mother_rx])
    session.flush()

    session.add_all(
        [
            MedicineBoxItem(
                id="box-father-bp",
                member_id=FATHER_ID,
                medicine_name="amlodipine besylate tablets",
                specification="5mg*28 tablets",
                total_quantity=28,
                remaining_quantity=3,
                dosage="1 tablet each time",
                frequency="once daily",
                purchased_at=today - timedelta(days=25),
                estimated_remaining_days=3,
                safety_note="About 3 days remaining; prepare materials and wait for confirmation.",
            ),
            MedicineBoxItem(
                id="box-mother-tcm",
                member_id=MOTHER_ID,
                medicine_name="TCM granules",
                specification="7 packs",
                total_quantity=14,
                remaining_quantity=4,
                dosage="1 pack each time",
                frequency="morning and evening",
                purchased_at=today - timedelta(days=5),
                estimated_remaining_days=2,
                safety_note="About 2 days remaining; follow-up submission requires confirmation.",
            ),
            PurchaseRecord(
                id="purchase-father-bp",
                member_id=FATHER_ID,
                prescription_id=father_rx.id,
                medicine_name="amlodipine besylate tablets",
                quantity=28,
                dosage="1 tablet each time",
                frequency="once daily",
                pharmacy_name="Renxin Internet Pharmacy",
                purchased_at=today - timedelta(days=25),
                purchase_channel="internet_hospital",
            ),
            PurchaseRecord(
                id="purchase-mother-tcm",
                member_id=MOTHER_ID,
                prescription_id=mother_rx.id,
                medicine_name="TCM granules",
                quantity=14,
                dosage="1 pack each time",
                frequency="morning and evening",
                pharmacy_name="Anhe TCM Pharmacy",
                purchased_at=today - timedelta(days=5),
                purchase_channel="internet_hospital",
            ),
        ]
    )

    pharmacy_a = Pharmacy(
        id="pharmacy-renxin",
        name="Renxin Internet Pharmacy",
        city="Shanghai",
        address="Demo Road 1",
        supports_delivery=True,
        supports_pickup=True,
        contact_phone="021-00000001",
    )
    pharmacy_b = Pharmacy(
        id="pharmacy-anhe",
        name="Anhe TCM Pharmacy",
        city="Shanghai",
        address="Demo Road 2",
        supports_delivery=True,
        supports_pickup=False,
        contact_phone="021-00000002",
    )
    session.add_all([pharmacy_a, pharmacy_b])
    session.flush()
    session.add_all(
        [
            PharmacyInventory(
                id="inventory-renxin-bp",
                pharmacy_id=pharmacy_a.id,
                medicine_name="amlodipine besylate tablets",
                stock_quantity=120,
                delivery_options=["delivery", "pickup"],
                safety_note="Stock exists; purchase still requires confirmation.",
            ),
            PharmacyInventory(
                id="inventory-anhe-tcm",
                pharmacy_id=pharmacy_b.id,
                medicine_name="TCM granules",
                stock_quantity=50,
                delivery_options=["delivery"],
                safety_note="Stock exists; purchase still requires confirmation.",
            ),
        ]
    )

    documents = [
        (
            "Refill SOP",
            "refill_sop",
            "internal_sop:v1",
            "Refill flow organizes prescription, purchase record and remaining medicine before user confirmation and doctor review.",
            ["refill", "prescription", "confirmation"],
        ),
        (
            "Human Confirmation Rule",
            "human_confirmation",
            "safety_policy:v1",
            "Consultation draft, purchase plan and reminder creation must wait for user confirmation.",
            ["confirmation", "draft", "reminder"],
        ),
        (
            "Medical Safety Boundary",
            "medical_safety",
            "safety_policy:v1",
            "The system does not diagnose, auto-prescribe or modify prescriptions.",
            ["safety", "boundary", "doctor"],
        ),
    ]
    for index, (title, category, source, content, keywords) in enumerate(documents):
        document = KnowledgeDocument(
            id=f"doc-{index}",
            title=title,
            category=category,
            source=source,
            content=content,
            safety_level="medical_boundary" if category == "medical_safety" else "general",
        )
        session.add(document)
        session.flush()
        session.add(
            KnowledgeChunk(
                id=f"chunk-{index}",
                document_id=document.id,
                chunk_index=0,
                content=content,
                keywords=keywords,
            )
        )

    session.commit()


def test_seed_data_queryable_by_service_layer(db_session: Session) -> None:
    profile = get_health_profile_context(db_session, USER_ID, FATHER_ID)
    prescriptions = get_prescription_context(db_session, FATHER_ID)
    box = get_medicine_box_context(db_session, FATHER_ID)
    inventory = get_pharmacy_inventory_context(
        db_session,
        "amlodipine",
        "Shanghai",
    )
    knowledge = search_safety_knowledge_context(db_session, "refill confirmation")

    assert profile is not None and profile["profile"]["relationship"] == "father"
    assert prescriptions is not None and prescriptions["prescriptions"]
    assert box is not None and box["items"][0]["estimated_remaining_days"] == 3
    assert inventory is not None and inventory["inventory_items"][0]["stock_quantity"] == 120
    assert knowledge is not None and knowledge["sources"]


def test_query_health_profile_father_and_mother(registry: ToolRegistry) -> None:
    father_result = registry.call(
        "query_health_profile",
        {"user_id": USER_ID, "member_id": FATHER_ID},
        context_for("ProfileAgent", FATHER_ID, ["query_health_profile"]),
    )
    mother_result = registry.call(
        "query_health_profile",
        {"user_id": USER_ID, "member_id": MOTHER_ID},
        context_for("ProfileAgent", MOTHER_ID, ["query_health_profile"]),
    )

    assert father_result.success is True
    assert mother_result.success is True
    assert father_result.tool_output["profile"]["relationship"] == "father"
    assert mother_result.tool_output["profile"]["relationship"] == "mother"


def test_query_prescriptions_father_bp_and_mother_tcm(registry: ToolRegistry) -> None:
    father_result = registry.call(
        "query_prescriptions",
        {"member_id": FATHER_ID},
        context_for("RefillAgent", FATHER_ID, ["query_prescriptions"]),
    )
    mother_result = registry.call(
        "query_prescriptions",
        {"member_id": MOTHER_ID},
        context_for("RefillAgent", MOTHER_ID, ["query_prescriptions"]),
    )

    father_output = _require_output(father_result.tool_output)
    mother_output = _require_output(mother_result.tool_output)
    assert father_result.success is True
    assert mother_result.success is True
    assert "amlodipine" in str(father_output["prescriptions"]).lower()
    assert "tcm granules" in str(mother_output["prescriptions"]).lower()


def test_query_medicine_box_returns_remaining_days(registry: ToolRegistry) -> None:
    result = registry.call(
        "query_medicine_box",
        {"member_id": FATHER_ID},
        context_for("RefillAgent", FATHER_ID, ["query_medicine_box"]),
    )

    output = _require_output(result.tool_output)
    assert result.success is True
    assert output["items"][0]["estimated_remaining_days"] == 3


def test_check_pharmacy_inventory_returns_seed_stock(registry: ToolRegistry) -> None:
    result = registry.call(
        "check_pharmacy_inventory",
        {"medicine_name": "amlodipine", "city": "Shanghai"},
        context_for("PharmacyAgent", FATHER_ID, ["check_pharmacy_inventory"]),
    )

    output = _require_output(result.tool_output)
    assert result.success is True
    assert output["inventory_items"][0]["stock_quantity"] == 120
    assert output["inventory_items"][0]["supports_delivery"] is True


def test_search_safety_knowledge_returns_sop_confirmation_and_boundary(
    registry: ToolRegistry,
) -> None:
    result = registry.call(
        "search_safety_knowledge",
        {"query": "refill confirmation safety boundary"},
        context_for("SafetyAgent", FATHER_ID, ["search_safety_knowledge"]),
    )

    output = _require_output(result.tool_output)
    categories = {source["category"] for source in output["sources"]}
    assert result.success is True
    assert {"refill_sop", "human_confirmation", "medical_safety"} <= categories


def test_nonexistent_member_returns_not_found_without_fabrication(
    registry: ToolRegistry,
) -> None:
    result = registry.call(
        "query_health_profile",
        {"user_id": USER_ID, "member_id": "member-missing"},
        context_for("ProfileAgent", "member-missing", ["query_health_profile"]),
    )

    assert result.success is False
    assert result.error_type == "not_found"
    assert result.fallback_action == "ask_user_clarification"
    assert result.tool_output is None
    assert result.evidence_present is False


def test_nonexistent_medicine_returns_not_found_without_fabrication(
    registry: ToolRegistry,
) -> None:
    result = registry.call(
        "check_pharmacy_inventory",
        {"medicine_name": "unknown medicine", "city": "Shanghai"},
        context_for("PharmacyAgent", FATHER_ID, ["check_pharmacy_inventory"]),
    )

    assert result.success is False
    assert result.error_type == "not_found"
    assert result.fallback_action == "manual_review"
    assert result.tool_output is None


def test_db_tools_are_registered_and_called_through_tool_registry(
    registry: ToolRegistry,
) -> None:
    assert "query_health_profile" in registry.list_tool_names()

    result = registry.call(
        "query_health_profile",
        {"user_id": USER_ID, "member_id": FATHER_ID},
        context_for("ProfileAgent", FATHER_ID, ["query_health_profile"]),
    )
    assert result.success is True
    assert result.permission_scope == "health_profile:read"


def test_input_schema_error_fails(registry: ToolRegistry) -> None:
    result = registry.call(
        "query_health_profile",
        {"user_id": USER_ID},
        context_for("ProfileAgent", FATHER_ID, ["query_health_profile"]),
    )

    assert result.success is False
    assert result.schema_valid is False
    assert result.error_type == "input_schema_error"


def test_output_schema_error_fails() -> None:
    class BrokenOutput(ToolContractModel):
        required_text: str = Field(min_length=1)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="broken_tool",
            description="Tool with invalid handler output.",
            input_schema=HealthProfileInput,
            output_schema=BrokenOutput,
            permission_scope="broken:read",
            allowed_agent_roles=("ProfileAgent",),
        ),
        lambda _tool_input, _context: {"unexpected": "value"},
    )

    result = registry.call(
        "broken_tool",
        {"user_id": USER_ID, "member_id": FATHER_ID},
        context_for("ProfileAgent", FATHER_ID, ["broken_tool"]),
    )

    assert result.success is False
    assert result.schema_valid is False
    assert result.error_type == "output_schema_error"


def test_permissions_still_work(registry: ToolRegistry) -> None:
    result = registry.call(
        "query_prescriptions",
        {"member_id": FATHER_ID},
        context_for("ProfileAgent", FATHER_ID, ["query_prescriptions"]),
    )

    assert result.success is False
    assert result.error_type == "permission_denied"


def test_allowed_tools_exclusion_fails(registry: ToolRegistry) -> None:
    result = registry.call(
        "query_medicine_box",
        {"member_id": FATHER_ID},
        context_for("RefillAgent", FATHER_ID, ["query_prescriptions"]),
    )

    assert result.success is False
    assert result.error_type == "tool_not_allowed"


def test_tool_output_has_no_unsafe_medical_action_content(
    registry: ToolRegistry,
) -> None:
    result = registry.call(
        "query_prescriptions",
        {"member_id": FATHER_ID},
        context_for("RefillAgent", FATHER_ID, ["query_prescriptions"]),
    )

    rendered_output = str(result.tool_output).lower()
    banned_action_phrases = [
        "increase your dose",
        "stop taking",
        "switch medicine yourself",
        "auto order success",
        "order placed",
    ]
    assert result.success is True
    assert all(phrase not in rendered_output for phrase in banned_action_phrases)


def test_tool_result_maps_to_tool_call_trace(registry: ToolRegistry) -> None:
    result = registry.call(
        "query_medicine_box",
        {"member_id": FATHER_ID},
        context_for("RefillAgent", FATHER_ID, ["query_medicine_box"]),
    )

    trace = result.to_tool_call_trace()
    assert trace.tool_name == "query_medicine_box"
    assert trace.member_id == FATHER_ID
    assert trace.success is True
    assert trace.schema_valid is True
    assert trace.evidence_present is True
    assert trace.source_name == "medicine_box_items"


def test_db_read_tools_keep_read_only_permissions(
    registry: ToolRegistry,
) -> None:
    """Read tools stay read-only even after runtime persistence is added."""
    assert all(spec.read_only for spec in registry.list_specs())
    assert all("write" not in spec.permission_scope for spec in registry.list_specs())


def test_db_read_stage_does_not_register_write_confirmation_tool(
    registry: ToolRegistry,
) -> None:
    assert "create_confirmation_draft" not in registry.list_tool_names()
    assert all(spec.read_only for spec in registry.list_specs())


def _require_output(output: dict[str, Any] | None) -> dict[str, Any]:
    assert output is not None
    return output

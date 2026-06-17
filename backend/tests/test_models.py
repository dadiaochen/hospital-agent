import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.database import Base
from app.models import AgentRun, AgentToolCall, FamilyMember, HealthProfile, KnowledgeDocument, MedicineBoxItem, User
from scripts.seed import seed_agent_audit_example, seed_knowledge, seed_medication_context, seed_pharmacy, seed_user_and_family


CORE_TABLES = {
    "users",
    "family_members",
    "health_profiles",
    "medicine_box_items",
    "prescriptions",
    "purchase_records",
    "pharmacies",
    "pharmacy_inventory",
    "refill_plans",
    "consultation_drafts",
    "purchase_plans",
    "medication_reminders",
    "follow_up_tasks",
    "knowledge_documents",
    "knowledge_chunks",
    "agent_memories",
    "agent_runs",
    "agent_tool_calls",
}


def test_models_import_and_metadata_has_core_tables() -> None:
    assert app.models.User.__tablename__ == "users"
    assert CORE_TABLES.issubset(set(Base.metadata.tables))


def test_all_core_tables_have_common_columns() -> None:
    for table_name in CORE_TABLES:
        columns = Base.metadata.tables[table_name].columns
        assert {"id", "created_at", "updated_at"}.issubset(set(columns.keys()))


def test_agent_log_columns_exist() -> None:
    agent_run_columns = set(AgentRun.__table__.columns.keys())
    assert {
        "user_id",
        "member_id",
        "user_goal",
        "intent",
        "status",
        "final_answer",
        "need_human_confirmation",
        "safety_result",
        "raw_state",
        "started_at",
        "ended_at",
        "duration_ms",
        "step_count",
        "task_success",
        "groundedness_score",
        "hallucination_flag",
        "human_confirmation_rate",
    }.issubset(agent_run_columns)

    tool_call_columns = set(AgentToolCall.__table__.columns.keys())
    assert {
        "run_id",
        "agent_role",
        "tool_name",
        "tool_input",
        "tool_output",
        "latency_ms",
        "success",
        "error_message",
        "error_type",
        "fallback_action",
        "schema_valid",
    }.issubset(tool_call_columns)


def test_medical_safety_banned_columns_do_not_exist() -> None:
    banned_columns = {"auto_prescribe", "diagnosis_by_ai", "ai_dosage_change"}
    for table in Base.metadata.tables.values():
        assert banned_columns.isdisjoint(set(table.columns.keys()))


def test_human_confirmation_columns_on_critical_action_tables() -> None:
    critical_tables = {
        "refill_plans",
        "consultation_drafts",
        "purchase_plans",
        "medication_reminders",
        "follow_up_tasks",
    }
    for table_name in critical_tables:
        columns = Base.metadata.tables[table_name].columns
        assert {"status", "need_human_confirmation", "confirmed_at"}.issubset(set(columns.keys()))


def test_seed_functions_are_repeatable_against_memory_database() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with TestingSession() as session:
        for _ in range(2):
            family = seed_user_and_family(session)
            seed_medication_context(session, family["father"], family["mother"])
            seed_pharmacy(session)
            seed_knowledge(session)
            seed_agent_audit_example(session, family["user"], family["father"])
            session.commit()

        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(FamilyMember)) == 3
        assert session.scalar(select(func.count()).select_from(HealthProfile)) == 3
        assert session.scalar(select(func.count()).select_from(MedicineBoxItem)) == 2
        assert session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 4
        assert session.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert session.scalar(select(func.count()).select_from(AgentToolCall)) == 2

        run = session.scalars(select(AgentRun)).one()
        assert run.started_at is not None
        assert run.ended_at is not None
        assert run.duration_ms == 180
        assert run.step_count == 4
        assert run.task_success is True
        assert run.groundedness_score == 1.0
        assert run.hallucination_flag is False
        assert run.human_confirmation_rate == 1.0

        medicine_box_call = session.scalars(
            select(AgentToolCall).where(AgentToolCall.tool_name == "get_medicine_box")
        ).one()
        assert medicine_box_call.agent_role == "RefillAgent"
        assert medicine_box_call.schema_valid is True
        assert medicine_box_call.fallback_action == "not_required"
        assert medicine_box_call.error_type is None

        pharmacy_call = session.scalars(
            select(AgentToolCall).where(AgentToolCall.tool_name == "check_pharmacy_inventory")
        ).one()
        assert pharmacy_call.agent_role == "PharmacyAgent"
        assert pharmacy_call.schema_valid is True
        assert pharmacy_call.success is False
        assert pharmacy_call.error_type == "tool_unavailable"
        assert pharmacy_call.fallback_action == "use_prescription_material_draft_only"


def test_agent_harness_migration_file_is_present() -> None:
    project_root = Path(__file__).resolve().parents[2]
    migration_file = project_root / "backend" / "alembic" / "versions" / "0002_add_agent_harness_trace_fields.py"
    assert migration_file.exists()

    migration_text = migration_file.read_text(encoding="utf-8")
    assert 'revision: str = "0002_add_agent_harness_trace_fields"' in migration_text
    assert 'down_revision: Union[str, None] = "0001_initial_schema"' in migration_text
    assert "def upgrade()" in migration_text
    assert "def downgrade()" in migration_text

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.database import Base
from app.models import (
    BusinessTask,
    HealthRecordEvent,
    MedicalDocument,
    SourceReference,
)
from scripts.seed import seed_runtime_examples, seed_user_and_family


RUNTIME_TABLES = {
    "business_tasks",
    "provider_calls",
    "source_references",
    "medical_documents",
    "health_record_events",
}


def test_runtime_tables_are_registered_and_timestamped() -> None:
    assert RUNTIME_TABLES.issubset(Base.metadata.tables)

    for table_name in RUNTIME_TABLES:
        columns = set(Base.metadata.tables[table_name].columns.keys())
        assert {"id", "created_at", "updated_at"} <= columns


def test_runtime_models_keep_scope_and_confirmation_boundaries() -> None:
    business_task_columns = set(BusinessTask.__table__.columns.keys())
    assert {
        "user_id",
        "member_id",
        "status",
        "need_human_confirmation",
        "confirmed_at",
    } <= business_task_columns

    source_columns = set(SourceReference.__table__.columns.keys())
    assert {
        "user_id",
        "task_id",
        "source_id",
        "document_id",
        "document_version",
        "retrieval_mode",
    } <= source_columns

    document_columns = set(MedicalDocument.__table__.columns.keys())
    assert {
        "user_id",
        "member_id",
        "status",
        "need_human_confirmation",
        "confirmed_at",
    } <= document_columns

    event_columns = set(HealthRecordEvent.__table__.columns.keys())
    assert {
        "user_id",
        "member_id",
        "source_document_id",
        "status",
        "need_human_confirmation",
        "confirmed_at",
        "external_action_status",
    } <= event_columns


def test_runtime_seed_is_repeatable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with testing_session() as session:
        for _ in range(2):
            family = seed_user_and_family(session)
            seed_runtime_examples(session, family["user"], family["mother"])
            session.commit()

        assert session.scalar(select(func.count()).select_from(MedicalDocument)) == 1
        assert session.scalar(select(func.count()).select_from(BusinessTask)) == 1
        assert session.scalar(select(func.count()).select_from(SourceReference)) == 1
        assert session.scalar(select(func.count()).select_from(HealthRecordEvent)) == 1

        task = session.scalars(select(BusinessTask)).one()
        assert task.status == "needs_confirmation"
        assert task.need_human_confirmation is True

        event = session.scalars(select(HealthRecordEvent)).one()
        assert event.status == "draft"
        assert event.need_human_confirmation is True

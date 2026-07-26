from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def test_alembic_has_one_linear_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())

    assert script.get_heads() == ["0006_vector_search_index"]
    assert script.get_revision("0006_vector_search_index").down_revision == (
        "0005_knowledge_metadata"
    )
    assert script.get_revision("0005_knowledge_metadata").down_revision == (
        "0004_business_task_runtime"
    )
    assert script.get_revision("0004_business_task_runtime").down_revision == (
        "0003_lightweight_vector_rag"
    )
    assert script.get_revision("0003_lightweight_vector_rag").down_revision == (
        "0002_add_agent_harness_trace_fields"
    )


def test_alembic_upgrade_head_creates_unified_schema(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migration-chain.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")

    command.upgrade(_alembic_config(), "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    knowledge_columns = {
        column["name"] for column in inspector.get_columns("knowledge_chunks")
    }
    document_columns = {
        column["name"] for column in inspector.get_columns("knowledge_documents")
    }

    assert {
        "embedding",
        "embedding_model",
        "embedding_content_hash",
        "embedded_at",
        "chunk_version",
    }.issubset(knowledge_columns)
    assert "version" in document_columns
    assert {
        "business_tasks",
        "provider_calls",
        "source_references",
        "medical_documents",
        "health_record_events",
    }.issubset(set(inspector.get_table_names()))

    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))

    assert revision == "0006_vector_search_index"

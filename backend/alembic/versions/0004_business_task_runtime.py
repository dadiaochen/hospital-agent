"""add business task runtime tables

Revision ID: 0004_business_task_runtime
Revises: 0003_lightweight_vector_rag
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_business_task_runtime"
down_revision: Union[str, None] = "0003_lightweight_vector_rag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "business_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        *timestamp_columns(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("business_domain", sa.String(length=40), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column(
            "need_human_confirmation",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "degraded",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["current_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_business_tasks_user_idempotency",
        ),
    )
    op.create_index("ix_business_tasks_user_id", "business_tasks", ["user_id"])
    op.create_index("ix_business_tasks_member_id", "business_tasks", ["member_id"])
    op.create_index(
        "ix_business_tasks_business_domain",
        "business_tasks",
        ["business_domain"],
    )
    op.create_index("ix_business_tasks_intent", "business_tasks", ["intent"])
    op.create_index(
        "ix_business_tasks_current_run_id",
        "business_tasks",
        ["current_run_id"],
    )

    op.create_table(
        "provider_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        *timestamp_columns(),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_mode", sa.String(length=20), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("success", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=160), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["business_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_calls_task_id", "provider_calls", ["task_id"])
    op.create_index("ix_provider_calls_run_id", "provider_calls", ["run_id"])
    op.create_index(
        "ix_provider_calls_provider_name",
        "provider_calls",
        ["provider_name"],
    )

    op.create_table(
        "source_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        *timestamp_columns(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.String(length=120), nullable=True),
        sa.Column("document_version", sa.String(length=40), nullable=True),
        sa.Column("chunk_id", sa.String(length=120), nullable=True),
        sa.Column("retrieval_mode", sa.String(length=40), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("member_id", sa.String(length=36), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["business_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_references_user_id", "source_references", ["user_id"])
    op.create_index("ix_source_references_task_id", "source_references", ["task_id"])
    op.create_index("ix_source_references_run_id", "source_references", ["run_id"])
    op.create_index("ix_source_references_source_id", "source_references", ["source_id"])
    op.create_index(
        "ix_source_references_document_id",
        "source_references",
        ["document_id"],
    )
    op.create_index(
        "ix_source_references_member_id",
        "source_references",
        ["member_id"],
    )

    op.create_table(
        "medical_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        *timestamp_columns(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("object_uri", sa.String(length=500), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("parser_provider", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("extracted_content", sa.JSON(), nullable=False),
        sa.Column(
            "document_version",
            sa.String(length=40),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column(
            "need_human_confirmation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_documents_user_id", "medical_documents", ["user_id"])
    op.create_index("ix_medical_documents_member_id", "medical_documents", ["member_id"])
    op.create_index(
        "ix_medical_documents_document_type",
        "medical_documents",
        ["document_type"],
    )

    op.create_table(
        "health_record_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        *timestamp_columns(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column(
            "need_human_confirmation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "external_action_status",
            sa.String(length=40),
            server_default="not_submitted",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["medical_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "member_id",
            "idempotency_key",
            name="uq_health_record_events_member_idempotency",
        ),
    )
    op.create_index("ix_health_record_events_user_id", "health_record_events", ["user_id"])
    op.create_index(
        "ix_health_record_events_member_id",
        "health_record_events",
        ["member_id"],
    )
    op.create_index(
        "ix_health_record_events_source_document_id",
        "health_record_events",
        ["source_document_id"],
    )
    op.create_index(
        "ix_health_record_events_event_type",
        "health_record_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_health_record_events_event_type", table_name="health_record_events")
    op.drop_index(
        "ix_health_record_events_source_document_id",
        table_name="health_record_events",
    )
    op.drop_index("ix_health_record_events_member_id", table_name="health_record_events")
    op.drop_index("ix_health_record_events_user_id", table_name="health_record_events")
    op.drop_table("health_record_events")

    op.drop_index("ix_medical_documents_document_type", table_name="medical_documents")
    op.drop_index("ix_medical_documents_member_id", table_name="medical_documents")
    op.drop_index("ix_medical_documents_user_id", table_name="medical_documents")
    op.drop_table("medical_documents")

    op.drop_index("ix_source_references_member_id", table_name="source_references")
    op.drop_index("ix_source_references_document_id", table_name="source_references")
    op.drop_index("ix_source_references_source_id", table_name="source_references")
    op.drop_index("ix_source_references_run_id", table_name="source_references")
    op.drop_index("ix_source_references_task_id", table_name="source_references")
    op.drop_index("ix_source_references_user_id", table_name="source_references")
    op.drop_table("source_references")

    op.drop_index("ix_provider_calls_provider_name", table_name="provider_calls")
    op.drop_index("ix_provider_calls_run_id", table_name="provider_calls")
    op.drop_index("ix_provider_calls_task_id", table_name="provider_calls")
    op.drop_table("provider_calls")

    op.drop_index("ix_business_tasks_current_run_id", table_name="business_tasks")
    op.drop_index("ix_business_tasks_intent", table_name="business_tasks")
    op.drop_index("ix_business_tasks_business_domain", table_name="business_tasks")
    op.drop_index("ix_business_tasks_member_id", table_name="business_tasks")
    op.drop_index("ix_business_tasks_user_id", table_name="business_tasks")
    op.drop_table("business_tasks")

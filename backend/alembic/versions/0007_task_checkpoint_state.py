"""add authoritative task checkpoints, confirmation records, and preferences

Revision ID: 0007_task_checkpoint_state
Revises: 0006_vector_search_index
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_task_checkpoint_state"
down_revision: Union[str, None] = "0006_vector_search_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
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
    op.add_column(
        "business_tasks",
        sa.Column("provider_mode", sa.String(length=20), server_default=sa.text("'mock'"), nullable=False),
    )
    op.add_column(
        "business_tasks",
        sa.Column("thread_id", sa.String(length=120), server_default=sa.text("'legacy'"), nullable=False),
    )
    op.add_column(
        "business_tasks",
        sa.Column("checkpoint_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "business_tasks",
        sa.Column("confirmation_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index("ix_business_tasks_thread_id", "business_tasks", ["thread_id"])

    op.add_column(
        "agent_runs",
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
    )
    # SQLite cannot ALTER TABLE to add a standalone constraint.  PostgreSQL
    # receives the explicit self-FK; SQLite still gets the column and model
    # metadata creates the FK for fresh test schemas.
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_agent_runs_parent_run_id",
            "agent_runs",
            "agent_runs",
            ["parent_run_id"],
            ["id"],
        )
    op.create_index("ix_agent_runs_parent_run_id", "agent_runs", ["parent_run_id"])

    op.create_table(
        "task_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confirmation_state", sa.String(length=40), nullable=False),
        sa.Column("confirmation_version", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("step_progress", sa.JSON(), nullable=False),
        sa.Column("run_summary", sa.JSON(), nullable=False),
        sa.Column("frozen_artifacts", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["business_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["parent_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "checkpoint_version",
            name="uq_task_checkpoints_task_version",
        ),
        sa.UniqueConstraint(
            "task_id",
            "run_id",
            name="uq_task_checkpoints_task_run",
        ),
    )
    op.create_index("ix_task_checkpoints_user_id", "task_checkpoints", ["user_id"])
    op.create_index("ix_task_checkpoints_member_id", "task_checkpoints", ["member_id"])
    op.create_index("ix_task_checkpoints_task_id", "task_checkpoints", ["task_id"])
    op.create_index("ix_task_checkpoints_thread_id", "task_checkpoints", ["thread_id"])
    op.create_index("ix_task_checkpoints_run_id", "task_checkpoints", ["run_id"])
    op.create_index("ix_task_checkpoints_parent_run_id", "task_checkpoints", ["parent_run_id"])
    op.create_index("ix_task_checkpoints_status", "task_checkpoints", ["status"])

    op.create_table(
        "task_confirmation_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=120), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("confirmation_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("previous_state", sa.String(length=40), nullable=False),
        sa.Column("next_state", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("actor_member_id", sa.String(length=36), nullable=False),
        sa.Column("human_confirmation_present", sa.Boolean(), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["business_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["actor_member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "action",
            "idempotency_key",
            "draft_version",
            name="uq_task_confirmation_action_idempotency",
        ),
    )
    op.create_index("ix_task_confirmation_records_user_id", "task_confirmation_records", ["user_id"])
    op.create_index("ix_task_confirmation_records_member_id", "task_confirmation_records", ["member_id"])
    op.create_index("ix_task_confirmation_records_task_id", "task_confirmation_records", ["task_id"])
    op.create_index("ix_task_confirmation_records_run_id", "task_confirmation_records", ["run_id"])
    op.create_index("ix_task_confirmation_records_draft_id", "task_confirmation_records", ["draft_id"])

    op.create_table(
        "confirmed_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_run_id", sa.String(length=36), nullable=False),
        sa.Column("confirmation_record_id", sa.String(length=36), nullable=False),
        sa.Column("preference_type", sa.String(length=80), nullable=False),
        sa.Column("preference_value", sa.JSON(), nullable=False),
        sa.Column("preference_version", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("revocable", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["business_tasks.id"]),
        sa.ForeignKeyConstraint(["created_by_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["confirmation_record_id"], ["task_confirmation_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_confirmed_preferences_user_idempotency",
        ),
        sa.UniqueConstraint(
            "user_id",
            "member_id",
            "preference_type",
            "preference_version",
            name="uq_confirmed_preferences_member_type_version",
        ),
    )
    op.create_index("ix_confirmed_preferences_user_id", "confirmed_preferences", ["user_id"])
    op.create_index("ix_confirmed_preferences_member_id", "confirmed_preferences", ["member_id"])
    op.create_index("ix_confirmed_preferences_task_id", "confirmed_preferences", ["task_id"])
    op.create_index("ix_confirmed_preferences_created_by_run_id", "confirmed_preferences", ["created_by_run_id"])
    op.create_index("ix_confirmed_preferences_confirmation_record_id", "confirmed_preferences", ["confirmation_record_id"])
    op.create_index("ix_confirmed_preferences_preference_type", "confirmed_preferences", ["preference_type"])
    op.create_index("ix_confirmed_preferences_source_id", "confirmed_preferences", ["source_id"])
    op.create_index("ix_confirmed_preferences_status", "confirmed_preferences", ["status"])


def downgrade() -> None:
    op.drop_index("ix_confirmed_preferences_status", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_source_id", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_preference_type", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_confirmation_record_id", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_created_by_run_id", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_task_id", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_member_id", table_name="confirmed_preferences")
    op.drop_index("ix_confirmed_preferences_user_id", table_name="confirmed_preferences")
    op.drop_table("confirmed_preferences")

    op.drop_index("ix_task_confirmation_records_draft_id", table_name="task_confirmation_records")
    op.drop_index("ix_task_confirmation_records_run_id", table_name="task_confirmation_records")
    op.drop_index("ix_task_confirmation_records_task_id", table_name="task_confirmation_records")
    op.drop_index("ix_task_confirmation_records_member_id", table_name="task_confirmation_records")
    op.drop_index("ix_task_confirmation_records_user_id", table_name="task_confirmation_records")
    op.drop_table("task_confirmation_records")

    op.drop_index("ix_task_checkpoints_status", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_parent_run_id", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_run_id", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_thread_id", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_task_id", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_member_id", table_name="task_checkpoints")
    op.drop_index("ix_task_checkpoints_user_id", table_name="task_checkpoints")
    op.drop_table("task_checkpoints")

    op.drop_index("ix_agent_runs_parent_run_id", table_name="agent_runs")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_agent_runs_parent_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "parent_run_id")

    op.drop_index("ix_business_tasks_thread_id", table_name="business_tasks")
    op.drop_column("business_tasks", "confirmation_version")
    op.drop_column("business_tasks", "checkpoint_version")
    op.drop_column("business_tasks", "thread_id")
    op.drop_column("business_tasks", "provider_mode")

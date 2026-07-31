"""add agent harness trace fields

Revision ID: 0002_add_agent_harness_trace_fields
Revises: 0001_initial_schema
Create Date: 2026-06-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_agent_harness_trace_fields"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alembic creates version_num as VARCHAR(32), but this migration's
    # descriptive revision ID is longer. Expanding it here also fixes
    # PostgreSQL databases that were already migrated through revision 0001.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )

    op.add_column(
        "agent_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.add_column("agent_runs", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("step_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("agent_runs", sa.Column("task_success", sa.Boolean(), nullable=True))
    op.add_column("agent_runs", sa.Column("groundedness_score", sa.Float(), nullable=True))
    op.add_column("agent_runs", sa.Column("hallucination_flag", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("agent_runs", sa.Column("human_confirmation_rate", sa.Float(), nullable=True))

    op.add_column("agent_tool_calls", sa.Column("agent_role", sa.String(length=80), server_default="unknown", nullable=False))
    op.add_column("agent_tool_calls", sa.Column("error_type", sa.String(length=80), nullable=True))
    op.add_column("agent_tool_calls", sa.Column("fallback_action", sa.String(length=120), nullable=True))
    op.add_column("agent_tool_calls", sa.Column("schema_valid", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_index("ix_agent_tool_calls_agent_role", "agent_tool_calls", ["agent_role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_tool_calls_agent_role", table_name="agent_tool_calls")
    op.drop_column("agent_tool_calls", "schema_valid")
    op.drop_column("agent_tool_calls", "fallback_action")
    op.drop_column("agent_tool_calls", "error_type")
    op.drop_column("agent_tool_calls", "agent_role")

    op.drop_column("agent_runs", "human_confirmation_rate")
    op.drop_column("agent_runs", "hallucination_flag")
    op.drop_column("agent_runs", "groundedness_score")
    op.drop_column("agent_runs", "task_success")
    op.drop_column("agent_runs", "step_count")
    op.drop_column("agent_runs", "duration_ms")
    op.drop_column("agent_runs", "ended_at")
    op.drop_column("agent_runs", "started_at")

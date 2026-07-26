"""add knowledge document and chunk version metadata

Revision ID: 0005_knowledge_metadata
Revises: 0004_business_task_runtime
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_knowledge_metadata"
down_revision: Union[str, None] = "0004_business_task_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "version",
            sa.String(length=40),
            server_default=sa.text("'1.0'"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "chunk_version",
            sa.String(length=40),
            server_default=sa.text("'1.0'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "chunk_version")
    op.drop_column("knowledge_documents", "version")

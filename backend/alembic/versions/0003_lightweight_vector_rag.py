"""add lightweight pgvector knowledge embeddings

Revision ID: 0003_lightweight_vector_rag
Revises: 0002_add_agent_harness_trace_fields
Create Date: 2026-07-20 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "0003_lightweight_vector_rag"
down_revision: Union[str, None] = "0002_add_agent_harness_trace_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    embedding_type = (
        Vector(512)
        if op.get_bind().dialect.name == "postgresql"
        else sa.JSON()
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", embedding_type, nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "embedded_at")
    op.drop_column("knowledge_chunks", "embedding_content_hash")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_chunks", "embedding")

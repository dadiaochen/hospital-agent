"""add the native pgvector search index for the unified RAG path

Revision ID: 0006_vector_search_index
Revises: 0005_knowledge_metadata
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_vector_search_index"
down_revision: Union[str, None] = "0005_knowledge_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_knowledge_chunks_embedding_hnsw"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
            "ON knowledge_chunks USING hnsw "
            "(embedding vector_cosine_ops) "
            "WHERE embedding IS NOT NULL"
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))

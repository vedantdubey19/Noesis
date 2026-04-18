"""add chunks table

Revision ID: 001_add_chunks_table
Revises:
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "001_add_chunks_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "chunks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("doc_title", sa.String(length=512), nullable=False),
        sa.Column("doc_url", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_source", "chunks", ["source"])

    conn = op.get_bind()
    row_count = conn.execute(sa.text("SELECT COUNT(*) FROM chunks")).scalar_one()
    if row_count >= 100:
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_chunks_embedding_ivfflat "
            "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    else:
        print("WARNING: chunks has fewer than 100 rows, skipping ivfflat index creation.")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_ivfflat")
    op.drop_index("ix_chunks_source", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")

"""add pipeline_logs table

Revision ID: 002_add_pipeline_logs
Revises: 001_add_chunks_table
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa


revision = "002_add_pipeline_logs"
down_revision = "001_add_chunks_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("page_title", sa.String(length=1024), nullable=False),
        sa.Column("observe_topic", sa.String(length=256), nullable=True),
        sa.Column("extract_content_type", sa.String(length=64), nullable=True),
        sa.Column("stage1_latency_ms", sa.Integer(), nullable=True),
        sa.Column("stage2_latency_ms", sa.Integer(), nullable=True),
        sa.Column("stage3_latency_ms", sa.Integer(), nullable=True),
        sa.Column("stage4_latency_ms", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("num_cards_returned", sa.Integer(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("error_stage", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pipeline_logs")

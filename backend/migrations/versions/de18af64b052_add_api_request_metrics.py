"""add API request performance metrics

Revision ID: de18af64b052
Revises: c41e6a7d903b
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "de18af64b052"
down_revision: Union[str, None] = "c41e6a7d903b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_request_metrics",
        sa.Column("metric_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("metric_id"),
    )
    op.create_index(op.f("ix_api_request_metrics_path"), "api_request_metrics", ["path"], unique=False)
    op.create_index(op.f("ix_api_request_metrics_created_at"), "api_request_metrics", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_api_request_metrics_created_at"), table_name="api_request_metrics")
    op.drop_index(op.f("ix_api_request_metrics_path"), table_name="api_request_metrics")
    op.drop_table("api_request_metrics")

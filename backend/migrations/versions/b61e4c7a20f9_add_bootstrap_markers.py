"""add durable bootstrap markers

Revision ID: b61e4c7a20f9
Revises: 7a3d912bc440
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b61e4c7a20f9"
down_revision: Union[str, None] = "7a3d912bc440"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_markers",
        sa.Column("marker_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("marker_key"),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_markers")

"""add user authentication source

Revision ID: c41e6a7d903b
Revises: 8b7d4c2a91ef
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c41e6a7d903b"
down_revision: Union[str, None] = "8b7d4c2a91ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_source", sa.String(length=20), nullable=False, server_default="local"),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_source")

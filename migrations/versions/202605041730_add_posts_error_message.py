"""add posts error message

Revision ID: 202605041730
Revises: 202605041700
Create Date: 2026-05-04 17:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202605041730"
down_revision: str | None = "202605041700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "error_message")

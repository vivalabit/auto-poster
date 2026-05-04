"""add posts scheduled at

Revision ID: 202605041700
Revises: 202605041630
Create Date: 2026-05-04 17:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202605041700"
down_revision: str | None = "202605041630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_posts_scheduled_at"),
        "posts",
        ["scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_posts_scheduled_at"), table_name="posts")
    op.drop_column("posts", "scheduled_at")

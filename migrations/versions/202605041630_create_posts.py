"""create posts

Revision ID: 202605041630
Revises: 202605041600
Create Date: 2026-05-04 16:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202605041630"
down_revision: str | None = "202605041600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("hashtags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=True),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('draft', 'scheduled', 'publishing', 'published', 'failed', "
            "'cancelled')",
            name="ck_posts_status",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media_assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["social_account_id"],
            ["social_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_posts_media_id"), "posts", ["media_id"], unique=False)
    op.create_index(
        op.f("ix_posts_social_account_id"),
        "posts",
        ["social_account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_posts_social_account_id"), table_name="posts")
    op.drop_index(op.f("ix_posts_media_id"), table_name="posts")
    op.drop_table("posts")

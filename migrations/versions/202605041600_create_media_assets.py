"""create media assets

Revision ID: 202605041600
Revises: 202605041530
Create Date: 2026-05-04 16:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202605041600"
down_revision: str | None = "202605041530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "storage_provider",
            sa.String(length=32),
            server_default="local",
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="ready",
            nullable=False,
        ),
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
            "status in ('ready')",
            name="ck_media_assets_status",
        ),
        sa.CheckConstraint(
            "storage_provider in ('local')",
            name="ck_media_assets_storage_provider",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_media_assets_size_positive",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_media_assets_checksum_sha256"),
        "media_assets",
        ["checksum_sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_media_assets_user_id"),
        "media_assets",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_media_assets_user_id"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_checksum_sha256"), table_name="media_assets")
    op.drop_table("media_assets")

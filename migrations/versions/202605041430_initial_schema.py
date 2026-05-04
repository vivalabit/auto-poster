"""initial schema

Revision ID: 202605041430
Revises:
Create Date: 2026-05-04 14:30:00.000000

"""
from collections.abc import Sequence


revision: str = "202605041430"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

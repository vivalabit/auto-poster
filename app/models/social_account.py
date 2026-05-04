from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.post import Post
    from app.models.user import User

TIKTOK_PLATFORM = "tiktok"
SOCIAL_ACCOUNT_STATUSES = ("connected", "expired", "revoked")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        CheckConstraint(
            f"platform = '{TIKTOK_PLATFORM}'",
            name="ck_social_accounts_platform_tiktok",
        ),
        CheckConstraint(
            "status in ('connected', 'expired', 'revoked')",
            name="ck_social_accounts_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        String(32),
        default=TIKTOK_PLATFORM,
        server_default=TIKTOK_PLATFORM,
    )
    account_name: Mapped[str] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32),
        default="connected",
        server_default="connected",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="social_accounts")
    posts: Mapped[list[Post]] = relationship(
        back_populates="social_account",
        cascade="all, delete-orphan",
    )

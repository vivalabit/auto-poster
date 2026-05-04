from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.media_asset import MediaAsset
    from app.models.social_account import SocialAccount

POST_STATUSES = (
    "draft",
    "scheduled",
    "publishing",
    "published",
    "failed",
    "cancelled",
)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'scheduled', 'publishing', 'published', 'failed', "
            "'cancelled')",
            name="ck_posts_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    media_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    social_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("social_accounts.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default="draft",
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

    media: Mapped[MediaAsset | None] = relationship(back_populates="posts")
    social_account: Mapped[SocialAccount] = relationship(back_populates="posts")

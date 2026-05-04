from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.post import Post
    from app.models.user import User

LOCAL_STORAGE_PROVIDER = "local"
MEDIA_ASSET_STATUSES = ("ready",)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "status in ('ready')",
            name="ck_media_assets_status",
        ),
        CheckConstraint(
            "storage_provider in ('local')",
            name="ck_media_assets_storage_provider",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="ck_media_assets_size_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_extension: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[float] = mapped_column(Float)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_provider: Mapped[str] = mapped_column(
        String(32),
        default=LOCAL_STORAGE_PROVIDER,
        server_default=LOCAL_STORAGE_PROVIDER,
    )
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(
        String(32),
        default="ready",
        server_default="ready",
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

    user: Mapped[User] = relationship(back_populates="media_assets")
    posts: Mapped[list[Post]] = relationship(back_populates="media")

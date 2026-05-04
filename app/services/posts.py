from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.media_asset import MediaAsset
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User


class PostError(RuntimeError):
    pass


class PostNotFoundError(PostError):
    pass


class PostValidationError(PostError):
    pass


def create_scheduled_post(
    db: Session,
    *,
    user: User,
    text: str,
    hashtags: list[str],
    media_id: UUID | None,
    social_account_id: UUID,
    scheduled_at: datetime,
) -> Post:
    scheduled_at = normalize_datetime(scheduled_at)
    if scheduled_at <= datetime.now(UTC):
        raise PostValidationError("scheduled_at must be in the future")

    social_account = get_user_social_account(
        db,
        user_id=user.id,
        social_account_id=social_account_id,
    )
    if social_account is None:
        raise PostNotFoundError("Social account was not found")

    if media_id is not None:
        media_asset = get_user_media_asset(db, user_id=user.id, media_id=media_id)
        if media_asset is None:
            raise PostNotFoundError("Media asset was not found")

    post = Post(
        text=text,
        hashtags=normalize_hashtags(hashtags),
        media_id=media_id,
        social_account_id=social_account.id,
        status="scheduled",
        scheduled_at=scheduled_at,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def list_user_posts(db: Session, *, user: User) -> list[Post]:
    return list(
        db.scalars(
            select(Post)
            .join(SocialAccount)
            .where(SocialAccount.user_id == user.id)
            .order_by(Post.created_at.desc())
        )
    )


def cancel_post(db: Session, *, user: User, post_id: UUID) -> Post:
    post = db.scalar(
        select(Post)
        .join(SocialAccount)
        .where(Post.id == post_id, SocialAccount.user_id == user.id)
    )
    if post is None:
        raise PostNotFoundError("Post was not found")
    if post.status == "cancelled":
        return post
    if post.status not in {"draft", "scheduled"}:
        raise PostValidationError(f"Cannot cancel post with status {post.status}")

    post.status = "cancelled"
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def get_user_social_account(
    db: Session,
    *,
    user_id: UUID,
    social_account_id: UUID,
) -> SocialAccount | None:
    return db.scalar(
        select(SocialAccount).where(
            SocialAccount.id == social_account_id,
            SocialAccount.user_id == user_id,
        )
    )


def get_user_media_asset(
    db: Session,
    *,
    user_id: UUID,
    media_id: UUID,
) -> MediaAsset | None:
    return db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == media_id,
            MediaAsset.user_id == user_id,
        )
    )


def normalize_hashtags(hashtags: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for hashtag in hashtags:
        value = hashtag.strip().lstrip("#")
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

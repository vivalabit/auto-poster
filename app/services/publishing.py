from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.integrations.tiktok.oauth import ensure_fresh_tiktok_tokens
from app.integrations.tiktok.publishing import (
    TikTokFileUploadSource,
    TikTokPostInfo,
    TikTokPublishStatus,
    TikTokPublishingClient,
)
from app.models.post import Post

PUBLISHABLE_STATUSES = {"draft", "scheduled", "failed"}
FINAL_STATUSES = {"published", "cancelled"}


class PublishPostError(RuntimeError):
    pass


def publish_post_by_id(db: Session, post_id: UUID) -> str:
    post = load_post_for_publishing(db, post_id)
    if post is None:
        return "not_found"
    if post.status in FINAL_STATUSES:
        return post.status
    if post.status == "publishing":
        return "publishing"
    if post.status not in PUBLISHABLE_STATUSES:
        return post.status

    try:
        mark_post_publishing(db, post)
        status = publish_post_to_tiktok(db, post)
        if is_success_status(status.status):
            mark_post_published(db, post)
            return "published"
        if is_failed_status(status.status):
            fail_post(db, post, status.fail_reason or f"TikTok status: {status.status}")
            return "failed"

        return post.status
    except Exception as exc:
        fail_post(db, post, str(exc))
        return "failed"


def load_post_for_publishing(db: Session, post_id: UUID) -> Post | None:
    return db.scalar(
        select(Post)
        .options(
            joinedload(Post.media),
            joinedload(Post.social_account),
        )
        .where(Post.id == post_id)
        .with_for_update()
    )


def mark_post_publishing(db: Session, post: Post) -> None:
    post.status = "publishing"
    post.error_message = None
    db.add(post)
    db.commit()
    db.refresh(post)


def mark_post_published(db: Session, post: Post) -> None:
    post.status = "published"
    post.error_message = None
    db.add(post)
    db.commit()
    db.refresh(post)


def fail_post(db: Session, post: Post, error_message: str) -> None:
    post.status = "failed"
    post.error_message = truncate_error_message(error_message)
    db.add(post)
    db.commit()
    db.refresh(post)


def publish_post_to_tiktok(db: Session, post: Post) -> TikTokPublishStatus:
    if post.media is None:
        raise PublishPostError("Post does not have media attached")

    social_account = ensure_fresh_tiktok_tokens(db, post.social_account)
    settings = get_settings()
    media_path = Path(settings.media_storage_dir) / post.media.storage_key
    if not media_path.exists():
        raise PublishPostError("Post media file was not found in local storage")

    media_size = media_path.stat().st_size
    client = TikTokPublishingClient(social_account.access_token)
    init_result = client.publish(
        post_info=TikTokPostInfo(
            privacy_level=settings.tiktok_publish_default_privacy_level,
            title=build_tiktok_title(post),
        ),
        source=TikTokFileUploadSource(
            video_size=media_size,
            chunk_size=media_size,
            total_chunk_count=1,
        ),
    )
    if init_result.upload_url is None:
        raise PublishPostError("TikTok did not return an upload URL")

    with media_path.open("rb") as media_file:
        client.upload_media(
            upload_url=init_result.upload_url,
            media=media_file,
            byte_start=0,
            byte_end=media_size - 1,
            total_byte_length=media_size,
            content_type=post.media.content_type,
        )

    return wait_for_publish_status(client, init_result.publish_id)


def wait_for_publish_status(
    client: TikTokPublishingClient,
    publish_id: str,
) -> TikTokPublishStatus:
    settings = get_settings()
    status = client.get_status(publish_id)
    for _ in range(max(settings.tiktok_publish_status_poll_attempts - 1, 0)):
        if is_terminal_status(status.status):
            return status
        time.sleep(settings.tiktok_publish_status_poll_interval_seconds)
        status = client.get_status(publish_id)
    return status


def build_tiktok_title(post: Post) -> str:
    hashtags = " ".join(f"#{hashtag}" for hashtag in post.hashtags)
    return " ".join(part for part in [post.text.strip(), hashtags] if part).strip()


def is_terminal_status(status: str) -> bool:
    return is_success_status(status) or is_failed_status(status)


def is_success_status(status: str) -> bool:
    return status.upper() in {"PUBLISH_COMPLETE", "SUCCESS", "SUCCEEDED", "PUBLISHED"}


def is_failed_status(status: str) -> bool:
    normalized = status.upper()
    return "FAIL" in normalized or normalized in {"ERROR", "REJECTED"}


def truncate_error_message(error_message: str, max_length: int = 2000) -> str:
    return error_message[:max_length]

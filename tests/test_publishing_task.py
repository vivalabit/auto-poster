from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.integrations.tiktok.publishing import TikTokPublishInitResult, TikTokPublishStatus
from app.models.media_asset import MediaAsset
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.services import publishing
from app.services.publishing import (
    PublishPostError,
    build_tiktok_title,
    publish_post_by_id,
    publish_post_to_tiktok,
)
from app.worker import tasks
from app.worker.tasks import publish_post


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.refreshed = []

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        self.refreshed.append(value)


class FakeSessionContext(FakeSession):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def make_account() -> SocialAccount:
    return SocialAccount(
        id=uuid4(),
        user_id=uuid4(),
        account_name="@owner",
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        status="connected",
    )


def make_media(tmp_path: Path | None = None) -> MediaAsset:
    user_id = uuid4()
    storage_key = f"{user_id}/clip.mp4"
    if tmp_path is not None:
        path = tmp_path / storage_key
        path.parent.mkdir(parents=True)
        path.write_bytes(b"video")

    return MediaAsset(
        id=uuid4(),
        user_id=user_id,
        original_filename="clip.mp4",
        content_type="video/mp4",
        file_extension=".mp4",
        size_bytes=5,
        duration_seconds=12,
        checksum_sha256="a" * 64,
        storage_provider="local",
        storage_key=storage_key,
        status="ready",
    )


def make_post(
    *,
    status: str = "scheduled",
    tmp_path: Path | None = None,
) -> Post:
    return Post(
        id=uuid4(),
        text="Caption",
        hashtags=["launch", "tiktok"],
        media=make_media(tmp_path),
        social_account=make_account(),
        status=status,
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_publish_post_by_id_marks_post_published(monkeypatch) -> None:
    db = FakeSession()
    post = make_post()
    calls = []

    monkeypatch.setattr(publishing, "load_post_for_publishing", lambda db, post_id: post)

    def fake_publish_post_to_tiktok(db, post):
        calls.append(post.status)
        return TikTokPublishStatus(
            status="PUBLISH_COMPLETE",
            fail_reason=None,
            publicly_available_post_ids=["post-id"],
            uploaded_bytes=5,
        )

    monkeypatch.setattr(publishing, "publish_post_to_tiktok", fake_publish_post_to_tiktok)

    assert publish_post_by_id(db, post.id) == "published"
    assert calls == ["publishing"]
    assert post.status == "published"
    assert post.error_message is None
    assert db.commits == 2


def test_publish_post_by_id_skips_already_published(monkeypatch) -> None:
    db = FakeSession()
    post = make_post(status="published")

    monkeypatch.setattr(publishing, "load_post_for_publishing", lambda db, post_id: post)
    monkeypatch.setattr(
        publishing,
        "publish_post_to_tiktok",
        lambda db, post: pytest.fail("published post should not publish again"),
    )

    assert publish_post_by_id(db, post.id) == "published"
    assert db.commits == 0


def test_publish_post_by_id_skips_in_flight_post(monkeypatch) -> None:
    db = FakeSession()
    post = make_post(status="publishing")

    monkeypatch.setattr(publishing, "load_post_for_publishing", lambda db, post_id: post)
    monkeypatch.setattr(
        publishing,
        "publish_post_to_tiktok",
        lambda db, post: pytest.fail("publishing post should not publish again"),
    )

    assert publish_post_by_id(db, post.id) == "publishing"
    assert db.commits == 0


def test_publish_post_by_id_saves_error_on_failure(monkeypatch) -> None:
    db = FakeSession()
    post = make_post()

    monkeypatch.setattr(publishing, "load_post_for_publishing", lambda db, post_id: post)

    def fake_publish_post_to_tiktok(db, post):
        raise PublishPostError("TikTok rejected media")

    monkeypatch.setattr(publishing, "publish_post_to_tiktok", fake_publish_post_to_tiktok)

    assert publish_post_by_id(db, post.id) == "failed"
    assert post.status == "failed"
    assert post.error_message == "TikTok rejected media"
    assert db.commits == 2


def test_publish_post_by_id_saves_tiktok_fail_reason(monkeypatch) -> None:
    db = FakeSession()
    post = make_post()

    monkeypatch.setattr(publishing, "load_post_for_publishing", lambda db, post_id: post)
    monkeypatch.setattr(
        publishing,
        "publish_post_to_tiktok",
        lambda db, post: TikTokPublishStatus(
            status="FAILED",
            fail_reason="Daily post limit reached",
            publicly_available_post_ids=[],
            uploaded_bytes=None,
        ),
    )

    assert publish_post_by_id(db, post.id) == "failed"
    assert post.status == "failed"
    assert post.error_message == "Daily post limit reached"


def test_publish_post_to_tiktok_uploads_local_media(monkeypatch, tmp_path) -> None:
    db = FakeSession()
    post = make_post(tmp_path=tmp_path)
    calls = {}

    monkeypatch.setattr(
        publishing,
        "get_settings",
        lambda: Settings(
            media_storage_dir=str(tmp_path),
            tiktok_publish_status_poll_attempts=1,
        ),
    )
    monkeypatch.setattr(
        publishing,
        "ensure_fresh_tiktok_tokens",
        lambda db, social_account: social_account,
    )

    class FakeTikTokClient:
        def __init__(self, access_token: str) -> None:
            calls["access_token"] = access_token

        def publish(self, *, post_info, source):
            calls["title"] = post_info.title
            calls["privacy_level"] = post_info.privacy_level
            calls["source"] = source
            return TikTokPublishInitResult(
                publish_id="publish-id",
                upload_url="https://upload",
            )

        def upload_media(self, **kwargs):
            calls["upload"] = kwargs

        def get_status(self, publish_id: str):
            calls["publish_id"] = publish_id
            return TikTokPublishStatus(
                status="PUBLISH_COMPLETE",
                fail_reason=None,
                publicly_available_post_ids=["post-id"],
                uploaded_bytes=5,
            )

    monkeypatch.setattr(publishing, "TikTokPublishingClient", FakeTikTokClient)

    status = publish_post_to_tiktok(db, post)

    assert status.status == "PUBLISH_COMPLETE"
    assert calls["access_token"] == "access"
    assert calls["title"] == "Caption #launch #tiktok"
    assert calls["privacy_level"] == "SELF_ONLY"
    assert calls["source"].video_size == 5
    assert calls["upload"]["byte_start"] == 0
    assert calls["upload"]["byte_end"] == 4
    assert calls["upload"]["total_byte_length"] == 5
    assert calls["upload"]["content_type"] == "video/mp4"
    assert calls["publish_id"] == "publish-id"


def test_publish_post_to_tiktok_requires_media() -> None:
    post = make_post()
    post.media = None

    with pytest.raises(PublishPostError, match="media"):
        publish_post_to_tiktok(FakeSession(), post)


def test_build_tiktok_title_combines_text_and_hashtags() -> None:
    post = make_post()

    assert build_tiktok_title(post) == "Caption #launch #tiktok"


def test_publish_post_task_opens_session(monkeypatch) -> None:
    post_id = uuid4()
    db = FakeSessionContext()
    captured = {}

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    def fake_publish_post_by_id(session, task_post_id):
        captured["session"] = session
        captured["post_id"] = task_post_id
        return "published"

    monkeypatch.setattr(tasks, "publish_post_by_id", fake_publish_post_by_id)

    assert publish_post.run(str(post_id)) == "published"
    assert captured == {"session": db, "post_id": post_id}

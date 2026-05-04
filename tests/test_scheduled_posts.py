from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import posts as posts_api
from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.media_asset import MediaAsset
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User
from app.services import posts
from app.services.posts import (
    PostNotFoundError,
    PostValidationError,
    cancel_post,
    create_scheduled_post,
    list_user_posts,
    normalize_hashtags,
)


class FakeSession:
    def __init__(self, scalar_value=None, scalar_values=None) -> None:
        self.scalar_value = scalar_value
        self.scalar_values = scalar_values or []
        self.added = []
        self.committed = False
        self.refreshed = []

    def scalar(self, statement):
        return self.scalar_value

    def scalars(self, statement):
        return self.scalar_values

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, value) -> None:
        self.refreshed.append(value)


def make_user() -> User:
    return User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_account(user: User) -> SocialAccount:
    return SocialAccount(
        id=uuid4(),
        user_id=user.id,
        account_name="@owner",
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        status="connected",
    )


def make_media(user: User) -> MediaAsset:
    return MediaAsset(
        id=uuid4(),
        user_id=user.id,
        original_filename="clip.mp4",
        content_type="video/mp4",
        file_extension=".mp4",
        size_bytes=128,
        duration_seconds=12,
        checksum_sha256="a" * 64,
        storage_provider="local",
        storage_key=f"{user.id}/clip.mp4",
        status="ready",
    )


def make_post(account: SocialAccount, *, status: str = "scheduled") -> Post:
    return Post(
        id=uuid4(),
        text="Caption",
        hashtags=["launch"],
        media_id=None,
        social_account_id=account.id,
        status=status,
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_create_scheduled_post_persists_scheduled_status(monkeypatch) -> None:
    user = make_user()
    account = make_account(user)
    media = make_media(user)
    db = FakeSession()

    monkeypatch.setattr(posts, "get_user_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr(posts, "get_user_media_asset", lambda *args, **kwargs: media)

    scheduled_at = datetime.now(UTC) + timedelta(hours=2)
    post = create_scheduled_post(
        db,
        user=user,
        text=" Launch ",
        hashtags=["#launch", "launch", " tiktok "],
        media_id=media.id,
        social_account_id=account.id,
        scheduled_at=scheduled_at,
    )

    assert post.status == "scheduled"
    assert post.scheduled_at == scheduled_at
    assert post.text == " Launch "
    assert post.hashtags == ["launch", "tiktok"]
    assert post.media_id == media.id
    assert post.social_account_id == account.id
    assert db.added == [post]
    assert db.committed is True
    assert db.refreshed == [post]


def test_create_scheduled_post_rejects_past_time(monkeypatch) -> None:
    user = make_user()
    db = FakeSession()

    with pytest.raises(PostValidationError, match="future"):
        create_scheduled_post(
            db,
            user=user,
            text="Past",
            hashtags=[],
            media_id=None,
            social_account_id=uuid4(),
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        )


def test_create_scheduled_post_rejects_unknown_social_account(monkeypatch) -> None:
    user = make_user()
    monkeypatch.setattr(posts, "get_user_social_account", lambda *args, **kwargs: None)

    with pytest.raises(PostNotFoundError, match="Social account"):
        create_scheduled_post(
            FakeSession(),
            user=user,
            text="Caption",
            hashtags=[],
            media_id=None,
            social_account_id=uuid4(),
            scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        )


def test_create_scheduled_post_rejects_unknown_media(monkeypatch) -> None:
    user = make_user()
    account = make_account(user)
    monkeypatch.setattr(posts, "get_user_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr(posts, "get_user_media_asset", lambda *args, **kwargs: None)

    with pytest.raises(PostNotFoundError, match="Media asset"):
        create_scheduled_post(
            FakeSession(),
            user=user,
            text="Caption",
            hashtags=[],
            media_id=uuid4(),
            social_account_id=account.id,
            scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        )


def test_list_user_posts_returns_scalar_results() -> None:
    user = make_user()
    account = make_account(user)
    existing = [make_post(account), make_post(account, status="published")]

    assert list_user_posts(FakeSession(scalar_values=existing), user=user) == existing


def test_cancel_post_marks_scheduled_post_cancelled() -> None:
    user = make_user()
    account = make_account(user)
    post = make_post(account)
    db = FakeSession(scalar_value=post)

    cancelled = cancel_post(db, user=user, post_id=post.id)

    assert cancelled.status == "cancelled"
    assert db.added == [post]
    assert db.committed is True
    assert db.refreshed == [post]


def test_cancel_post_rejects_published_post() -> None:
    user = make_user()
    account = make_account(user)
    post = make_post(account, status="published")

    with pytest.raises(PostValidationError, match="Cannot cancel"):
        cancel_post(FakeSession(scalar_value=post), user=user, post_id=post.id)


def test_normalize_hashtags_strips_hashes_and_duplicates() -> None:
    assert normalize_hashtags(["#one", "one", " two ", "", "#two"]) == ["one", "two"]


def test_create_scheduled_publication_endpoint(monkeypatch) -> None:
    user = make_user()
    account = make_account(user)
    post = make_post(account)
    captured = {}

    def fake_create_scheduled_post(db, **kwargs):
        captured.update(kwargs)
        return post

    monkeypatch.setattr(posts_api, "create_scheduled_post", fake_create_scheduled_post)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/posts/scheduled",
            json={
                "text": "Caption",
                "hashtags": ["launch"],
                "media_id": None,
                "social_account_id": str(account.id),
                "scheduled_at": post.scheduled_at.isoformat(),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == str(post.id)
    assert response.json()["status"] == "scheduled"
    assert captured["user"] == user
    assert captured["social_account_id"] == account.id


def test_list_publications_endpoint(monkeypatch) -> None:
    user = make_user()
    account = make_account(user)
    post = make_post(account)

    monkeypatch.setattr(posts_api, "list_user_posts", lambda db, user: [post])
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/posts")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(post.id)


def test_cancel_publication_endpoint(monkeypatch) -> None:
    user = make_user()
    account = make_account(user)
    post = make_post(account, status="cancelled")

    monkeypatch.setattr(posts_api, "cancel_post", lambda db, user, post_id: post)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).post(f"/posts/{post.id}/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_publication_endpoint_returns_validation_error(monkeypatch) -> None:
    user = make_user()

    def fake_cancel_post(db, user, post_id):
        raise PostValidationError("Cannot cancel post with status published")

    monkeypatch.setattr(posts_api, "cancel_post", fake_cancel_post)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).post(f"/posts/{uuid4()}/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot cancel post with status published"

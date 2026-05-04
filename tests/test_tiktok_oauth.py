from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.api import tiktok_oauth as tiktok_oauth_api
from app.core.config import Settings
from app.db.session import get_db
from app.integrations.tiktok import oauth
from app.integrations.tiktok.oauth import (
    TikTokOAuthError,
    TikTokTokenData,
    build_authorization_url,
    ensure_fresh_tiktok_tokens,
    fetch_tiktok_account_name,
    verify_oauth_state,
)
from app.main import app
from app.models.social_account import SocialAccount
from app.models.user import User


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False
        self.refreshed = []

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, value) -> None:
        self.refreshed.append(value)


def test_build_authorization_url_contains_signed_state(monkeypatch) -> None:
    user_id = uuid4()
    monkeypatch.setattr(
        oauth,
        "get_settings",
        lambda: Settings(
            tiktok_client_key="client-key",
            tiktok_client_secret="client-secret",
            tiktok_redirect_uri="https://example.com/tiktok/oauth/callback",
            tiktok_oauth_state_secret="state-secret",
        ),
    )

    authorization_url = build_authorization_url(user_id)

    assert authorization_url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "client_key=client-key" in authorization_url
    assert "scope=user.info.basic" in authorization_url
    state = authorization_url.split("state=", 1)[1]
    assert verify_oauth_state(state) == user_id


def test_callback_saves_tiktok_tokens(monkeypatch) -> None:
    user_id = uuid4()
    user = User(
        id=user_id,
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    saved = {}

    monkeypatch.setattr(tiktok_oauth_api, "verify_oauth_state", lambda state: user_id)
    monkeypatch.setattr(
        tiktok_oauth_api,
        "exchange_code_for_tokens",
        lambda code: TikTokTokenData(
            open_id="open-id",
            account_name="Tik Toker",
            access_token="access",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scope="user.info.basic",
        ),
    )

    def fake_save_tiktok_tokens(db, callback_user_id, token_data):
        saved["user_id"] = callback_user_id
        saved["token_data"] = token_data
        return SocialAccount(
            id=uuid4(),
            user_id=callback_user_id,
            account_name=token_data.open_id,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            expires_at=token_data.expires_at,
            status="connected",
        )

    monkeypatch.setattr(tiktok_oauth_api, "save_tiktok_tokens", fake_save_tiktok_tokens)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/tiktok/oauth/callback?code=abc&state=signed")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert saved["user_id"] == user_id
    assert saved["token_data"].open_id == "open-id"
    assert saved["token_data"].account_name == "Tik Toker"


def test_refreshes_expired_tiktok_token(monkeypatch) -> None:
    account = SocialAccount(
        user_id=uuid4(),
        account_name="open-id",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        status="expired",
    )
    db = FakeSession()
    monkeypatch.setattr(
        oauth,
        "get_settings",
        lambda: Settings(tiktok_client_key="client-key", tiktok_client_secret="secret"),
    )
    monkeypatch.setattr(
        oauth.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "open_id": "open-id",
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 86400,
                "scope": "user.info.basic",
            },
        ),
    )

    refreshed = ensure_fresh_tiktok_tokens(db, account)

    assert refreshed.access_token == "new-access"
    assert refreshed.refresh_token == "new-refresh"
    assert refreshed.account_name == "open-id"
    assert refreshed.status == "connected"
    assert db.committed is True


def test_refresh_marks_account_expired_on_tiktok_error(monkeypatch) -> None:
    account = SocialAccount(
        user_id=uuid4(),
        account_name="open-id",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        status="connected",
    )
    db = FakeSession()
    monkeypatch.setattr(
        oauth,
        "get_settings",
        lambda: Settings(tiktok_client_key="client-key", tiktok_client_secret="secret"),
    )
    monkeypatch.setattr(
        oauth.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Refresh token expired"},
        ),
    )

    with pytest.raises(TikTokOAuthError):
        ensure_fresh_tiktok_tokens(db, account)

    assert account.status == "expired"
    assert db.committed is True


def test_fetch_tiktok_account_name_uses_display_name(monkeypatch) -> None:
    monkeypatch.setattr(
        oauth.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"data": {"user": {"open_id": "open-id", "display_name": "Tik Toker"}}},
        ),
    )

    assert fetch_tiktok_account_name("access-token", fallback="open-id") == "Tik Toker"

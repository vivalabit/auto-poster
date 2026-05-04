from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.tokens import create_session_token, hash_session_token
from app.auth.dependencies import get_current_user
from app.main import app
from app.models.user import User


def test_hash_session_token_is_stable_sha256() -> None:
    assert (
        hash_session_token("personal-token")
        == "f5e79647e5f68d52ce5c65d6f6ca08783f3845bc1a33bf4cada2e2f6cf307d46"
    )


def test_create_session_token_returns_urlsafe_token() -> None:
    token = create_session_token()

    assert len(token) >= 32
    assert "\n" not in token


def test_auth_me_returns_current_user() -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash=hash_session_token("token"),
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = TestClient(app).get(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"


def test_auth_me_rejects_missing_token() -> None:
    response = TestClient(app).get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

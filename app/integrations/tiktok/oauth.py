from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.tiktok.publishing import TikTokPublishingClient
from app.models.social_account import TIKTOK_PLATFORM, SocialAccount

TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TOKEN_REFRESH_SKEW = timedelta(minutes=5)


class TikTokOAuthError(RuntimeError):
    pass


class TikTokOAuthConfigError(TikTokOAuthError):
    pass


@dataclass(frozen=True)
class TikTokTokenData:
    open_id: str
    account_name: str
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str


def build_authorization_url(user_id: UUID) -> str:
    settings = get_settings()
    ensure_tiktok_configured()
    query = {
        "client_key": settings.tiktok_client_key,
        "response_type": "code",
        "scope": ",".join(settings.tiktok_scope_list),
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": create_oauth_state(user_id),
    }
    return f"{TIKTOK_AUTHORIZE_URL}?{urlencode(query)}"


def create_oauth_state(user_id: UUID) -> str:
    settings = get_settings()
    payload = {
        "user_id": str(user_id),
        "nonce": token_urlsafe(16),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        settings.tiktok_oauth_state_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    return ".".join(
        [
            encode_urlsafe(payload_bytes),
            encode_urlsafe(signature),
        ]
    )


def verify_oauth_state(state: str, max_age: timedelta = timedelta(minutes=10)) -> UUID:
    settings = get_settings()
    try:
        payload_part, signature_part = state.split(".", 1)
        payload_bytes = decode_urlsafe(payload_part)
        signature = decode_urlsafe(signature_part)
    except ValueError as exc:
        raise TikTokOAuthError("Invalid OAuth state") from exc

    expected_signature = hmac.new(
        settings.tiktok_oauth_state_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise TikTokOAuthError("Invalid OAuth state")

    payload = json.loads(payload_bytes)
    issued_at = datetime.fromtimestamp(payload["iat"], UTC)
    if datetime.now(UTC) - issued_at > max_age:
        raise TikTokOAuthError("Expired OAuth state")

    return UUID(payload["user_id"])


def exchange_code_for_tokens(code: str) -> TikTokTokenData:
    settings = get_settings()
    ensure_tiktok_configured()
    response = httpx.post(
        TIKTOK_TOKEN_URL,
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.tiktok_redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    token_data = parse_token_response(response)
    return replace(
        token_data,
        account_name=fetch_tiktok_account_name(
            token_data.access_token,
            fallback=token_data.open_id,
        ),
    )


def validate_tiktok_publishing_access(token_data: TikTokTokenData) -> None:
    settings = get_settings()
    requested_scopes = set(settings.tiktok_scope_list)
    if not requested_scopes.intersection({"video.publish", "video.upload"}):
        return

    TikTokPublishingClient(token_data.access_token).check_publishing_access(token_data.scope)


def refresh_tiktok_tokens(db: Session, social_account: SocialAccount) -> SocialAccount:
    settings = get_settings()
    ensure_tiktok_configured()
    response = httpx.post(
        TIKTOK_TOKEN_URL,
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": social_account.refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )

    try:
        token_data = replace(
            parse_token_response(response, fallback_open_id=social_account.account_name),
            account_name=social_account.account_name,
        )
    except TikTokOAuthError:
        social_account.status = "expired"
        db.add(social_account)
        db.commit()
        raise

    apply_token_data(social_account, token_data)
    db.add(social_account)
    db.commit()
    db.refresh(social_account)
    return social_account


def ensure_fresh_tiktok_tokens(db: Session, social_account: SocialAccount) -> SocialAccount:
    if social_account.expires_at > datetime.now(UTC) + TOKEN_REFRESH_SKEW:
        return social_account

    return refresh_tiktok_tokens(db, social_account)


def save_tiktok_tokens(
    db: Session,
    user_id: UUID,
    token_data: TikTokTokenData,
) -> SocialAccount:
    social_account = db.scalar(
        select(SocialAccount).where(
            SocialAccount.user_id == user_id,
            SocialAccount.platform == TIKTOK_PLATFORM,
        )
    )
    if social_account is None:
        social_account = SocialAccount(
            user_id=user_id,
            platform=TIKTOK_PLATFORM,
            account_name=token_data.account_name,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            expires_at=token_data.expires_at,
            status="connected",
        )
    else:
        apply_token_data(social_account, token_data)

    db.add(social_account)
    db.commit()
    db.refresh(social_account)
    return social_account


def fetch_tiktok_account_name(access_token: str, fallback: str) -> str:
    response = httpx.get(
        TIKTOK_USER_INFO_URL,
        params={"fields": "open_id,display_name"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if response.status_code >= 400:
        return fallback

    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        return fallback

    user = payload.get("data", {}).get("user", {})
    return user.get("display_name") or user.get("open_id") or fallback


def parse_token_response(
    response: httpx.Response,
    fallback_open_id: str | None = None,
) -> TikTokTokenData:
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise TikTokOAuthError("TikTok returned an invalid token response") from exc

    if response.status_code >= 400 or "error" in payload:
        error = payload.get("error_description") or payload.get("error") or response.text
        raise TikTokOAuthError(f"TikTok token request failed: {error}")

    open_id = payload.get("open_id") or fallback_open_id
    if not open_id:
        raise TikTokOAuthError("TikTok token response did not include open_id")

    expires_in = int(payload["expires_in"])
    return TikTokTokenData(
        open_id=open_id,
        account_name=open_id,
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or "",
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        scope=payload.get("scope", ""),
    )


def apply_token_data(social_account: SocialAccount, token_data: TikTokTokenData) -> None:
    social_account.account_name = token_data.account_name
    social_account.access_token = token_data.access_token
    if token_data.refresh_token:
        social_account.refresh_token = token_data.refresh_token
    social_account.expires_at = token_data.expires_at
    social_account.status = "connected"


def ensure_tiktok_configured() -> None:
    settings = get_settings()
    if not settings.tiktok_client_key or not settings.tiktok_client_secret:
        raise TikTokOAuthConfigError("TikTok OAuth client key and secret are not configured")


def encode_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_urlsafe(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

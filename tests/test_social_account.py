from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.social_account import (
    SOCIAL_ACCOUNT_STATUSES,
    TIKTOK_PLATFORM,
    SocialAccount,
)


def test_social_account_defaults_to_tiktok_connected() -> None:
    account = SocialAccount(
        user_id=uuid4(),
        account_name="@owner",
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    assert account.platform is None or account.platform == TIKTOK_PLATFORM
    assert account.status is None or account.status == "connected"


def test_social_account_table_enforces_tiktok_only() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in SocialAccount.__table__.constraints
        if constraint.name
    }

    assert constraints["ck_social_accounts_platform_tiktok"] == "platform = 'tiktok'"


def test_social_account_status_values_are_minimal() -> None:
    assert SOCIAL_ACCOUNT_STATUSES == ("connected", "expired", "revoked")

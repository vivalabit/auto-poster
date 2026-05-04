from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.post import POST_STATUSES, Post
from app.models.social_account import SocialAccount


def test_post_defaults_to_draft_with_empty_content() -> None:
    post = Post(social_account_id=uuid4())

    assert post.text is None or post.text == ""
    assert post.hashtags is None or post.hashtags == []
    assert post.status is None or post.status == "draft"
    assert post.media_id is None
    assert post.scheduled_at is None


def test_post_status_values_match_workflow() -> None:
    assert POST_STATUSES == (
        "draft",
        "scheduled",
        "publishing",
        "published",
        "failed",
        "cancelled",
    )


def test_post_table_constraints_and_foreign_keys() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Post.__table__.constraints
        if constraint.name
    }
    foreign_keys = {
        foreign_key.parent.name: (
            foreign_key.column.table.name,
            foreign_key.column.name,
            foreign_key.ondelete,
        )
        for foreign_key in Post.__table__.foreign_keys
    }

    assert constraints["ck_posts_status"] == (
        "status in ('draft', 'scheduled', 'publishing', 'published', 'failed', "
        "'cancelled')"
    )
    assert foreign_keys["media_id"] == ("media_assets", "id", "SET NULL")
    assert foreign_keys["social_account_id"] == ("social_accounts", "id", "CASCADE")


def test_social_account_has_posts_relationship() -> None:
    account = SocialAccount(
        user_id=uuid4(),
        account_name="@owner",
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    post = Post(
        text="Hello",
        hashtags=["launch", "tiktok"],
        social_account=account,
    )

    assert post.social_account is account
    assert account.posts == [post]

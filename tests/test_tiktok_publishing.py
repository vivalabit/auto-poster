import httpx
import pytest

from app.integrations.tiktok.publishing import (
    TikTokFileUploadSource,
    TikTokPostInfo,
    TikTokPublishingAuthError,
    TikTokPublishingClient,
    TikTokPublishingPermissionError,
    TikTokPublishingRateLimitError,
    TikTokPublishingValidationError,
)


def test_check_publishing_access_queries_creator_info(monkeypatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={
                "data": {
                    "creator_username": "creator",
                    "creator_nickname": "Creator",
                    "privacy_level_options": ["SELF_ONLY"],
                    "comment_disabled": False,
                    "duet_disabled": True,
                    "stitch_disabled": True,
                    "max_video_post_duration_sec": 300,
                },
                "error": {"code": "ok", "message": "", "log_id": "log"},
            },
        )

    monkeypatch.setattr("app.integrations.tiktok.publishing.httpx.post", fake_post)

    creator = TikTokPublishingClient("access").check_publishing_access(
        "video.upload,video.publish"
    )

    assert creator.username == "creator"
    assert creator.privacy_level_options == ["SELF_ONLY"]
    assert calls[0][0].endswith("/v2/post/publish/creator_info/query/")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer access"


def test_check_publishing_access_rejects_missing_scope() -> None:
    client = TikTokPublishingClient("access")

    with pytest.raises(TikTokPublishingPermissionError, match="video.publish"):
        client.check_publishing_access("user.info.basic,video.upload")


def test_publish_initializes_direct_video_post(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "data": {"publish_id": "v_pub_file~123", "upload_url": "https://upload"},
                "error": {"code": "ok", "message": "", "log_id": "log"},
            },
        )

    monkeypatch.setattr("app.integrations.tiktok.publishing.httpx.post", fake_post)

    result = TikTokPublishingClient("access").publish(
        post_info=TikTokPostInfo(
            privacy_level="SELF_ONLY",
            title="Caption",
            disable_comment=True,
        ),
        source=TikTokFileUploadSource(
            video_size=10_000_000,
            chunk_size=10_000_000,
            total_chunk_count=1,
        ),
    )

    assert result.publish_id == "v_pub_file~123"
    assert result.upload_url == "https://upload"
    assert captured["url"].endswith("/v2/post/publish/video/init/")
    assert captured["json"] == {
        "post_info": {
            "privacy_level": "SELF_ONLY",
            "title": "Caption",
            "disable_comment": True,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": 10_000_000,
            "chunk_size": 10_000_000,
            "total_chunk_count": 1,
        },
    }


def test_init_upload_initializes_inbox_video_upload(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "data": {"publish_id": "v_inbox_file~123", "upload_url": "https://upload"},
                "error": {"code": "ok", "message": "", "log_id": "log"},
            },
        )

    monkeypatch.setattr("app.integrations.tiktok.publishing.httpx.post", fake_post)

    result = TikTokPublishingClient("access").init_upload(
        source=TikTokFileUploadSource(
            video_size=5_000_000,
            chunk_size=5_000_000,
            total_chunk_count=1,
        ),
    )

    assert result.publish_id == "v_inbox_file~123"
    assert captured["url"].endswith("/v2/post/publish/inbox/video/init/")
    assert captured["json"]["source_info"]["source"] == "FILE_UPLOAD"


def test_upload_media_sends_content_range(monkeypatch) -> None:
    captured = {}

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["content"] = kwargs["content"]
        return httpx.Response(206)

    monkeypatch.setattr("app.integrations.tiktok.publishing.httpx.put", fake_put)

    TikTokPublishingClient("access").upload_media(
        upload_url="https://upload",
        media=b"abc",
        byte_start=0,
        byte_end=2,
        total_byte_length=10,
    )

    assert captured["url"] == "https://upload"
    assert captured["content"] == b"abc"
    assert captured["headers"]["Content-Length"] == "3"
    assert captured["headers"]["Content-Range"] == "bytes 0-2/10"


def test_get_status_normalizes_public_post_ids_typo(monkeypatch) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "PUBLISH_COMPLETE",
                    "publicaly_available_post_id": ["post-id"],
                    "uploaded_bytes": 100,
                },
                "error": {"code": "ok", "message": "", "log_id": "log"},
            },
        )

    monkeypatch.setattr("app.integrations.tiktok.publishing.httpx.post", fake_post)

    status = TikTokPublishingClient("access").get_status("publish-id")

    assert status.status == "PUBLISH_COMPLETE"
    assert status.publicly_available_post_ids == ["post-id"]
    assert status.uploaded_bytes == 100


@pytest.mark.parametrize(
    ("response", "error_type", "message"),
    [
        (
            httpx.Response(
                200,
                json={
                    "data": {},
                    "error": {
                        "code": "scope_not_authorized",
                        "message": "missing scope",
                        "log_id": "log",
                    },
                },
            ),
            TikTokPublishingPermissionError,
            "required publishing scope",
        ),
        (
            httpx.Response(
                401,
                json={
                    "error": {
                        "code": "access_token_invalid",
                        "message": "bad token",
                        "log_id": "log",
                    }
                },
            ),
            TikTokPublishingAuthError,
            "invalid or expired",
        ),
        (
            httpx.Response(
                429,
                json={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "slow down",
                        "log_id": "log",
                    }
                },
            ),
            TikTokPublishingRateLimitError,
            "rate limit",
        ),
        (
            httpx.Response(
                200,
                json={
                    "error": {
                        "code": "privacy_level_option_mismatch",
                        "message": "bad privacy",
                        "log_id": "log",
                    }
                },
            ),
            TikTokPublishingValidationError,
            "privacy level",
        ),
    ],
)
def test_tiktok_api_errors_are_normalized(
    monkeypatch,
    response,
    error_type,
    message,
) -> None:
    monkeypatch.setattr(
        "app.integrations.tiktok.publishing.httpx.post",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(error_type, match=message):
        TikTokPublishingClient("access").get_status("publish-id")

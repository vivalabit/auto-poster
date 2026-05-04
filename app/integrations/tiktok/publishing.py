from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO

import httpx

TIKTOK_API_BASE_URL = "https://open.tiktokapis.com"
TIKTOK_CREATOR_INFO_PATH = "/v2/post/publish/creator_info/query/"
TIKTOK_DIRECT_VIDEO_INIT_PATH = "/v2/post/publish/video/init/"
TIKTOK_INBOX_VIDEO_INIT_PATH = "/v2/post/publish/inbox/video/init/"
TIKTOK_STATUS_FETCH_PATH = "/v2/post/publish/status/fetch/"

DIRECT_POST_SCOPE = "video.publish"
UPLOAD_SCOPE = "video.upload"
PUBLISHING_SCOPES = frozenset({DIRECT_POST_SCOPE, UPLOAD_SCOPE})


class TikTokPublishingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        log_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.log_id = log_id


class TikTokPublishingPermissionError(TikTokPublishingError):
    pass


class TikTokPublishingAuthError(TikTokPublishingPermissionError):
    pass


class TikTokPublishingRateLimitError(TikTokPublishingError):
    pass


class TikTokPublishingValidationError(TikTokPublishingError):
    pass


class TikTokPublishingTemporaryError(TikTokPublishingError):
    pass


class TikTokMediaUploadError(TikTokPublishingError):
    pass


@dataclass(frozen=True)
class TikTokCreatorInfo:
    username: str
    nickname: str
    privacy_level_options: list[str]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool
    max_video_post_duration_sec: int | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TikTokCreatorInfo:
        return cls(
            username=str(payload.get("creator_username") or ""),
            nickname=str(payload.get("creator_nickname") or ""),
            privacy_level_options=list(payload.get("privacy_level_options") or []),
            comment_disabled=bool(payload.get("comment_disabled", False)),
            duet_disabled=bool(payload.get("duet_disabled", False)),
            stitch_disabled=bool(payload.get("stitch_disabled", False)),
            max_video_post_duration_sec=payload.get("max_video_post_duration_sec"),
        )


@dataclass(frozen=True)
class TikTokPostInfo:
    privacy_level: str
    title: str | None = None
    disable_comment: bool | None = None
    disable_duet: bool | None = None
    disable_stitch: bool | None = None
    video_cover_timestamp_ms: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"privacy_level": self.privacy_level}
        optional_fields = {
            "title": self.title,
            "disable_comment": self.disable_comment,
            "disable_duet": self.disable_duet,
            "disable_stitch": self.disable_stitch,
            "video_cover_timestamp_ms": self.video_cover_timestamp_ms,
        }
        payload.update(
            {key: value for key, value in optional_fields.items() if value is not None}
        )
        return payload


@dataclass(frozen=True)
class TikTokFileUploadSource:
    video_size: int
    chunk_size: int
    total_chunk_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": "FILE_UPLOAD",
            "video_size": self.video_size,
            "chunk_size": self.chunk_size,
            "total_chunk_count": self.total_chunk_count,
        }


@dataclass(frozen=True)
class TikTokPullFromUrlSource:
    video_url: str

    def to_payload(self) -> dict[str, Any]:
        return {"source": "PULL_FROM_URL", "video_url": self.video_url}


@dataclass(frozen=True)
class TikTokPublishInitResult:
    publish_id: str
    upload_url: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TikTokPublishInitResult:
        publish_id = payload.get("publish_id")
        if not publish_id:
            raise TikTokPublishingError("TikTok response did not include publish_id")
        return cls(publish_id=str(publish_id), upload_url=payload.get("upload_url"))


@dataclass(frozen=True)
class TikTokPublishStatus:
    status: str
    fail_reason: str | None
    publicly_available_post_ids: list[str]
    uploaded_bytes: int | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TikTokPublishStatus:
        return cls(
            status=str(payload.get("status") or ""),
            fail_reason=payload.get("fail_reason"),
            publicly_available_post_ids=list(
                payload.get("publicly_available_post_id")
                or payload.get("publicaly_available_post_id")
                or []
            ),
            uploaded_bytes=payload.get("uploaded_bytes"),
        )


class TikTokPublishingClient:
    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = TIKTOK_API_BASE_URL,
        timeout: float = 30,
    ) -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_publishing_access(
        self,
        granted_scopes: str | list[str],
    ) -> TikTokCreatorInfo:
        scopes = normalize_scopes(granted_scopes)
        missing_scopes = PUBLISHING_SCOPES - scopes
        if missing_scopes:
            missing = ", ".join(sorted(missing_scopes))
            raise TikTokPublishingPermissionError(
                f"TikTok account did not grant required publishing scope(s): {missing}",
                code="scope_not_granted",
            )

        return self.query_creator_info()

    def query_creator_info(self) -> TikTokCreatorInfo:
        payload = self._post_json(TIKTOK_CREATOR_INFO_PATH, json={})
        return TikTokCreatorInfo.from_payload(payload)

    def init_upload(
        self,
        *,
        source: TikTokFileUploadSource | TikTokPullFromUrlSource,
    ) -> TikTokPublishInitResult:
        payload = self._post_json(
            TIKTOK_INBOX_VIDEO_INIT_PATH,
            json={"source_info": source.to_payload()},
        )
        return TikTokPublishInitResult.from_payload(payload)

    def publish(
        self,
        *,
        post_info: TikTokPostInfo,
        source: TikTokFileUploadSource | TikTokPullFromUrlSource,
    ) -> TikTokPublishInitResult:
        payload = self._post_json(
            TIKTOK_DIRECT_VIDEO_INIT_PATH,
            json={
                "post_info": post_info.to_payload(),
                "source_info": source.to_payload(),
            },
        )
        return TikTokPublishInitResult.from_payload(payload)

    def upload_media(
        self,
        *,
        upload_url: str,
        media: bytes | BinaryIO,
        byte_start: int,
        byte_end: int,
        total_byte_length: int,
        content_type: str = "video/mp4",
    ) -> None:
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(byte_end - byte_start + 1),
            "Content-Range": f"bytes {byte_start}-{byte_end}/{total_byte_length}",
        }
        try:
            response = httpx.put(
                upload_url,
                content=media,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise TikTokMediaUploadError("TikTok media upload failed") from exc

        if response.status_code not in (201, 206):
            raise normalize_tiktok_upload_error(response)

    def get_status(self, publish_id: str) -> TikTokPublishStatus:
        payload = self._post_json(
            TIKTOK_STATUS_FETCH_PATH,
            json={"publish_id": publish_id},
        )
        return TikTokPublishStatus.from_payload(payload)

    def _post_json(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                json=json,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise TikTokPublishingTemporaryError("TikTok API request failed") from exc

        payload = parse_tiktok_response(response)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise TikTokPublishingError("TikTok returned an invalid response")
        return data


def normalize_scopes(scopes: str | list[str]) -> set[str]:
    if isinstance(scopes, str):
        return {
            scope.strip()
            for scope in scopes.replace(",", " ").split()
            if scope.strip()
        }
    return {scope.strip() for scope in scopes if scope.strip()}


def parse_tiktok_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise TikTokPublishingError(
            "TikTok returned an invalid response",
            status_code=response.status_code,
        ) from exc

    error = payload.get("error")
    error_code = error.get("code") if isinstance(error, dict) else None
    if response.status_code >= 400 or (error_code and error_code != "ok"):
        raise normalize_tiktok_api_error(response, payload)

    return payload


def normalize_tiktok_api_error(
    response: httpx.Response,
    payload: dict[str, Any],
) -> TikTokPublishingError:
    error = payload.get("error")
    code = None
    message = None
    log_id = None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        log_id = error.get("log_id")

    normalized_message = normalize_tiktok_error_message(
        code=code,
        message=message,
        fallback=response.text,
    )
    error_class = classify_tiktok_api_error(code, response.status_code)
    return error_class(
        normalized_message,
        code=code,
        status_code=response.status_code,
        log_id=log_id,
    )


def normalize_tiktok_upload_error(response: httpx.Response) -> TikTokPublishingError:
    messages = {
        400: "TikTok rejected the uploaded media chunk headers or size",
        403: "TikTok upload URL expired or is not authorized",
        404: "TikTok upload task was not found",
        416: "TikTok upload byte range does not match current upload progress",
    }
    message = messages.get(response.status_code)
    if message is None and response.status_code >= 500:
        return TikTokPublishingTemporaryError(
            "TikTok media upload is temporarily unavailable",
            status_code=response.status_code,
        )
    return TikTokMediaUploadError(
        message or "TikTok media upload failed",
        status_code=response.status_code,
    )


def classify_tiktok_api_error(
    code: str | None,
    status_code: int,
) -> type[TikTokPublishingError]:
    permission_codes = {
        "scope_not_authorized",
        "unaudited_client_can_only_post_to_private_accounts",
        "reached_active_user_cap",
        "spam_risk_user_banned_from_posting",
    }
    validation_codes = {
        "privacy_level_option_mismatch",
        "url_ownership_unverified",
        "spam_risk_too_many_posts",
    }
    if status_code == 401 or code == "access_token_invalid":
        return TikTokPublishingAuthError
    if status_code == 429 or code == "rate_limit_exceeded":
        return TikTokPublishingRateLimitError
    if status_code >= 500:
        return TikTokPublishingTemporaryError
    if code in permission_codes:
        return TikTokPublishingPermissionError
    if code in validation_codes:
        return TikTokPublishingValidationError
    return TikTokPublishingError


def normalize_tiktok_error_message(
    *,
    code: str | None,
    message: str | None,
    fallback: str,
) -> str:
    friendly_messages = {
        "access_token_invalid": "TikTok access token is invalid or expired",
        "scope_not_authorized": (
            "TikTok account did not authorize the required publishing scope"
        ),
        "unaudited_client_can_only_post_to_private_accounts": (
            "TikTok app is not audited for public Direct Post publishing"
        ),
        "reached_active_user_cap": "TikTok app reached the daily active publishing user cap",
        "spam_risk_too_many_posts": "TikTok account reached the daily posting limit",
        "spam_risk_user_banned_from_posting": "TikTok account is blocked from creating posts",
        "privacy_level_option_mismatch": (
            "TikTok privacy level is not available for this creator"
        ),
        "url_ownership_unverified": "TikTok requires verified ownership for this media URL",
        "rate_limit_exceeded": "TikTok API rate limit exceeded",
    }
    if code in friendly_messages:
        return friendly_messages[code]
    if message:
        return message
    if code:
        return f"TikTok API request failed: {code}"
    return fallback or "TikTok API request failed"

from datetime import UTC, datetime
from io import BytesIO
import struct
from uuid import uuid4

from fastapi.testclient import TestClient
from fastapi import UploadFile
from starlette.datastructures import Headers
import pytest

from app.api import media as media_api
from app.auth.dependencies import get_current_user
from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.media_asset import (
    LOCAL_STORAGE_PROVIDER,
    MEDIA_ASSET_STATUSES,
    MediaAsset,
)
from app.models.user import User
from app.services import media_assets
from app.services.media_assets import (
    MediaValidationError,
    create_media_asset,
    parse_mp4_duration_seconds,
)


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


def atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def make_mp4(duration_seconds: int = 12, timescale: int = 1000) -> bytes:
    duration = duration_seconds * timescale
    mvhd_payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">IIII", 0, 0, timescale, duration)
        + b"\x00" * 80
    )
    return (
        atom(b"ftyp", b"isom\x00\x00\x00\x01isom")
        + atom(b"moov", atom(b"mvhd", mvhd_payload))
        + atom(b"mdat", b"video")
    )


def upload_file(
    content: bytes,
    *,
    filename: str = "clip.mp4",
    content_type: str = "video/mp4",
) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def test_media_asset_table_shape() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in MediaAsset.__table__.constraints
        if constraint.name
    }

    assert MEDIA_ASSET_STATUSES == ("ready",)
    assert LOCAL_STORAGE_PROVIDER == "local"
    assert constraints["ck_media_assets_status"] == "status in ('ready')"
    assert constraints["ck_media_assets_storage_provider"] == "storage_provider in ('local')"
    assert constraints["ck_media_assets_size_positive"] == "size_bytes > 0"


def test_parse_mp4_duration_seconds(tmp_path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(make_mp4(duration_seconds=42))

    assert parse_mp4_duration_seconds(path) == 42


def test_create_media_asset_stores_video_locally(monkeypatch, tmp_path) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db = FakeSession()
    monkeypatch.setattr(
        media_assets,
        "get_settings",
        lambda: Settings(media_storage_dir=str(tmp_path), media_max_video_size_bytes=1024 * 1024),
    )

    asset = create_media_asset(
        db=db,
        user=user,
        upload=upload_file(make_mp4(duration_seconds=30)),
    )

    assert asset.user_id == user.id
    assert asset.original_filename == "clip.mp4"
    assert asset.content_type == "video/mp4"
    assert asset.file_extension == ".mp4"
    assert asset.duration_seconds == 30
    assert asset.storage_provider == "local"
    assert asset.status == "ready"
    assert (tmp_path / asset.storage_key).exists()
    assert db.added == [asset]
    assert db.committed is True
    assert db.refreshed == [asset]


def test_create_media_asset_rejects_unsupported_format(monkeypatch, tmp_path) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        media_assets,
        "get_settings",
        lambda: Settings(media_storage_dir=str(tmp_path)),
    )

    with pytest.raises(MediaValidationError, match="Unsupported video extension"):
        create_media_asset(
            db=FakeSession(),
            user=user,
            upload=upload_file(b"not-video", filename="clip.avi", content_type="video/avi"),
        )


def test_create_media_asset_rejects_oversized_video(monkeypatch, tmp_path) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        media_assets,
        "get_settings",
        lambda: Settings(media_storage_dir=str(tmp_path), media_max_video_size_bytes=16),
    )

    with pytest.raises(MediaValidationError, match="exceeds"):
        create_media_asset(
            db=FakeSession(),
            user=user,
            upload=upload_file(make_mp4(duration_seconds=1)),
        )


def test_create_media_asset_rejects_long_video(monkeypatch, tmp_path) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        media_assets,
        "get_settings",
        lambda: Settings(
            media_storage_dir=str(tmp_path),
            media_max_video_duration_seconds=10,
        ),
    )

    with pytest.raises(MediaValidationError, match="duration exceeds"):
        create_media_asset(
            db=FakeSession(),
            user=user,
            upload=upload_file(make_mp4(duration_seconds=11)),
        )


def test_upload_media_asset_endpoint(monkeypatch) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    asset = MediaAsset(
        id=uuid4(),
        user_id=user.id,
        original_filename="clip.mp4",
        content_type="video/mp4",
        file_extension=".mp4",
        size_bytes=128,
        duration_seconds=12,
        checksum_sha256="a" * 64,
        storage_provider="local",
        storage_key=f"{user.id}/asset.mp4",
        status="ready",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    captured = {}

    def fake_create_media_asset(db, user, upload):
        captured["db"] = db
        captured["user"] = user
        captured["filename"] = upload.filename
        return asset

    monkeypatch.setattr(media_api, "create_media_asset", fake_create_media_asset)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/media/assets",
            files={"file": ("clip.mp4", make_mp4(), "video/mp4")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == str(asset.id)
    assert response.json()["storage_provider"] == "local"
    assert captured["user"] == user
    assert captured["filename"] == "clip.mp4"


def test_upload_media_asset_endpoint_returns_validation_error(monkeypatch) -> None:
    user = User(
        id=uuid4(),
        email="owner@example.com",
        session_token_hash="hash",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    def fake_create_media_asset(db, user, upload):
        raise MediaValidationError("Unsupported video extension")

    monkeypatch.setattr(media_api, "create_media_asset", fake_create_media_asset)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/media/assets",
            files={"file": ("clip.avi", b"invalid", "video/avi")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported video extension"

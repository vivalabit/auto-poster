from __future__ import annotations

import hashlib
import shutil
import struct
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.media_asset import LOCAL_STORAGE_PROVIDER, MediaAsset
from app.models.user import User

READ_CHUNK_SIZE = 1024 * 1024
MP4_CONTAINER_TYPES = {"moov", "trak", "mdia", "minf", "stbl", "edts"}


class MediaAssetError(RuntimeError):
    pass


class MediaValidationError(MediaAssetError):
    pass


def create_media_asset(db: Session, user: User, upload: UploadFile) -> MediaAsset:
    settings = get_settings()
    original_filename = Path(upload.filename or "").name
    extension = Path(original_filename).suffix.lower()
    content_type = (upload.content_type or "").lower()

    validate_upload_metadata(
        original_filename=original_filename,
        extension=extension,
        content_type=content_type,
    )

    storage_dir = Path(settings.media_storage_dir)
    temporary_dir = storage_dir / "tmp"
    temporary_dir.mkdir(parents=True, exist_ok=True)

    asset_id = uuid4()
    temporary_path = temporary_dir / f"{asset_id}.upload"
    final_path: Path | None = None

    try:
        size_bytes, checksum_sha256 = write_upload_to_temporary_file(
            upload=upload,
            destination=temporary_path,
            max_size_bytes=settings.media_max_video_size_bytes,
        )
        validate_video_signature(temporary_path)
        duration_seconds = parse_mp4_duration_seconds(temporary_path)
        if duration_seconds is None:
            raise MediaValidationError("Could not determine video duration")
        if duration_seconds > settings.media_max_video_duration_seconds:
            raise MediaValidationError(
                "Video duration exceeds "
                f"{settings.media_max_video_duration_seconds} seconds"
            )

        storage_key = f"{user.id}/{asset_id}{extension}"
        final_path = storage_dir / storage_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_path), final_path)

        media_asset = MediaAsset(
            id=asset_id,
            user_id=user.id,
            original_filename=original_filename,
            content_type=content_type,
            file_extension=extension,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            checksum_sha256=checksum_sha256,
            storage_provider=LOCAL_STORAGE_PROVIDER,
            storage_key=storage_key,
            status="ready",
        )
        db.add(media_asset)
        db.commit()
        db.refresh(media_asset)
        return media_asset
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise


def validate_upload_metadata(
    *,
    original_filename: str,
    extension: str,
    content_type: str,
) -> None:
    settings = get_settings()
    if not original_filename:
        raise MediaValidationError("Media filename is required")
    if extension not in settings.media_allowed_extension_list:
        allowed = ", ".join(settings.media_allowed_extension_list)
        raise MediaValidationError(f"Unsupported video extension. Allowed: {allowed}")
    if content_type not in settings.media_allowed_content_type_list:
        allowed = ", ".join(settings.media_allowed_content_type_list)
        raise MediaValidationError(f"Unsupported video content type. Allowed: {allowed}")


def write_upload_to_temporary_file(
    *,
    upload: UploadFile,
    destination: Path,
    max_size_bytes: int,
) -> tuple[int, str]:
    size_bytes = 0
    checksum = hashlib.sha256()
    upload.file.seek(0)

    with destination.open("wb") as output:
        while chunk := upload.file.read(READ_CHUNK_SIZE):
            size_bytes += len(chunk)
            if size_bytes > max_size_bytes:
                raise MediaValidationError(
                    f"Video file exceeds {max_size_bytes} bytes"
                )
            checksum.update(chunk)
            output.write(chunk)

    if size_bytes == 0:
        raise MediaValidationError("Video file is empty")

    return size_bytes, checksum.hexdigest()


def validate_video_signature(path: Path) -> None:
    with path.open("rb") as file:
        header = file.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise MediaValidationError("Unsupported or invalid video container")


def parse_mp4_duration_seconds(path: Path) -> float | None:
    with path.open("rb") as file:
        file_size = path.stat().st_size
        return find_mvhd_duration(file, file_size)


def find_mvhd_duration(file, limit: int) -> float | None:
    while file.tell() + 8 <= limit:
        atom_start = file.tell()
        header = file.read(8)
        if len(header) < 8:
            return None

        atom_size, atom_type_bytes = struct.unpack(">I4s", header)
        atom_type = atom_type_bytes.decode("latin1")
        header_size = 8
        if atom_size == 1:
            largesize_bytes = file.read(8)
            if len(largesize_bytes) < 8:
                return None
            atom_size = struct.unpack(">Q", largesize_bytes)[0]
            header_size = 16
        elif atom_size == 0:
            atom_size = limit - atom_start

        atom_end = atom_start + atom_size
        if atom_size < header_size or atom_end > limit:
            return None

        if atom_type == "mvhd":
            return parse_mvhd_atom(file, atom_end)
        if atom_type in MP4_CONTAINER_TYPES:
            duration = find_mvhd_duration(file, atom_end)
            if duration is not None:
                return duration

        file.seek(atom_end)

    return None


def parse_mvhd_atom(file, atom_end: int) -> float | None:
    version_flags = file.read(4)
    if len(version_flags) < 4:
        return None

    version = version_flags[0]
    if version == 1:
        payload = file.read(28)
        if len(payload) < 28:
            return None
        timescale = struct.unpack(">I", payload[16:20])[0]
        duration = struct.unpack(">Q", payload[20:28])[0]
    elif version == 0:
        payload = file.read(16)
        if len(payload) < 16:
            return None
        timescale = struct.unpack(">I", payload[8:12])[0]
        duration = struct.unpack(">I", payload[12:16])[0]
    else:
        return None

    file.seek(atom_end)
    if timescale == 0:
        return None
    return duration / timescale

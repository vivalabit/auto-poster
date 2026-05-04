from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    content_type: str
    file_extension: str
    size_bytes: int
    duration_seconds: float
    checksum_sha256: str
    storage_provider: str
    storage_key: str
    status: str
    created_at: datetime

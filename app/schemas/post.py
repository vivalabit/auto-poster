from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScheduledPostCreate(BaseModel):
    text: str = ""
    hashtags: list[str] = Field(default_factory=list)
    media_id: UUID | None = None
    social_account_id: UUID
    scheduled_at: datetime


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    hashtags: list[str]
    media_id: UUID | None
    social_account_id: UUID
    status: str
    scheduled_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

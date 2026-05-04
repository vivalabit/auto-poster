from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Auto Posting API"
    app_env: str = "local"
    debug: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "auto_posting"
    postgres_user: str = "auto_posting"
    postgres_password: str = Field(default="auto_posting", repr=False)

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    tiktok_client_key: str = ""
    tiktok_client_secret: str = Field(default="", repr=False)
    tiktok_redirect_uri: str = "https://localhost:8000/tiktok/oauth/callback"
    tiktok_scopes: str = "user.info.basic,video.upload,video.publish"
    tiktok_oauth_state_secret: str = Field(default="change-me", repr=False)

    media_storage_dir: str = "storage/media"
    media_max_video_size_bytes: int = 512 * 1024 * 1024
    media_max_video_duration_seconds: int = 600
    media_allowed_video_extensions: str = ".mp4,.mov"
    media_allowed_video_content_types: str = "video/mp4,video/quicktime"
    tiktok_publish_default_privacy_level: str = "SELF_ONLY"
    tiktok_publish_status_poll_attempts: int = 5
    tiktok_publish_status_poll_interval_seconds: float = 2

    @property
    def database_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def tiktok_scope_list(self) -> list[str]:
        return [scope.strip() for scope in self.tiktok_scopes.split(",") if scope.strip()]

    @property
    def media_allowed_extension_list(self) -> list[str]:
        return [
            extension.strip().lower()
            for extension in self.media_allowed_video_extensions.split(",")
            if extension.strip()
        ]

    @property
    def media_allowed_content_type_list(self) -> list[str]:
        return [
            content_type.strip().lower()
            for content_type in self.media_allowed_video_content_types.split(",")
            if content_type.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

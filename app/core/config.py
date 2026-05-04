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


@lru_cache
def get_settings() -> Settings:
    return Settings()

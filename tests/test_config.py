from app.core.config import Settings


def test_database_url_uses_postgres_settings() -> None:
    settings = Settings(
        postgres_host="postgres",
        postgres_port=5433,
        postgres_db="app_db",
        postgres_user="app_user",
        postgres_password="secret",
    )

    assert (
        settings.database_url
        == "postgresql+psycopg://app_user:secret@postgres:5433/app_db"
    )

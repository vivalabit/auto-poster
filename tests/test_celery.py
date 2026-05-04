from app.core.config import Settings
from app.commands import run_worker
import app.commands as commands
from app.worker.celery_app import celery_app
from app.worker.tasks import ping


def test_redis_url_uses_redis_settings() -> None:
    settings = Settings(redis_host="redis", redis_port=6380, redis_db=2)

    assert settings.redis_url == "redis://redis:6380/2"


def test_celery_uses_redis_for_broker_and_backend() -> None:
    assert celery_app.conf.broker_url == "redis://localhost:6379/0"
    assert celery_app.conf.result_backend == "redis://localhost:6379/0"


def test_ping_task_returns_pong() -> None:
    assert ping.run() == "pong"


def test_worker_command_starts_celery_worker(monkeypatch) -> None:
    worker_args = []

    def fake_worker_main(args: list[str]) -> None:
        worker_args.extend(args)

    monkeypatch.setattr(commands.celery_app, "worker_main", fake_worker_main)

    run_worker()

    assert worker_args == ["worker", "--loglevel=info"]

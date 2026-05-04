import uvicorn

from app.core.config import get_settings
from app.worker.celery_app import celery_app


def run_api() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


def run_worker() -> None:
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=info",
        ]
    )

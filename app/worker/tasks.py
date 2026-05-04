from uuid import UUID

from app.worker.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.publishing import publish_post_by_id


@celery_app.task(name="debug.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="posts.publish")
def publish_post(post_id: str) -> str:
    with SessionLocal() as db:
        return publish_post_by_id(db, UUID(post_id))

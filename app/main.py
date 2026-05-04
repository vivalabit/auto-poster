from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.media import router as media_router
from app.api.posts import router as posts_router
from app.api.tiktok_oauth import router as tiktok_oauth_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(media_router)
    app.include_router(posts_router)
    app.include_router(tiktok_oauth_router)
    return app


app = create_app()

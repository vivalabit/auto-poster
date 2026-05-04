from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.post import PostRead, ScheduledPostCreate
from app.services.posts import (
    PostNotFoundError,
    PostValidationError,
    cancel_post,
    create_scheduled_post,
    list_user_posts,
)

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("/scheduled", response_model=PostRead, status_code=status.HTTP_201_CREATED)
def create_scheduled_publication(
    payload: ScheduledPostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_scheduled_post(
            db,
            user=current_user,
            text=payload.text,
            hashtags=payload.hashtags,
            media_id=payload.media_id,
            social_account_id=payload.social_account_id,
            scheduled_at=payload.scheduled_at,
        )
    except PostNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PostValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[PostRead])
def list_publications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_posts(db, user=current_user)


@router.post("/{post_id}/cancel", response_model=PostRead)
def cancel_publication(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return cancel_post(db, user=current_user, post_id=post_id)
    except PostNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PostValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

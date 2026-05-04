from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.media import MediaAssetRead
from app.services.media_assets import MediaValidationError, create_media_asset

router = APIRouter(prefix="/media/assets", tags=["media-assets"])


@router.post("", response_model=MediaAssetRead, status_code=status.HTTP_201_CREATED)
def upload_media_asset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_media_asset(db=db, user=current_user, upload=file)
    except MediaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

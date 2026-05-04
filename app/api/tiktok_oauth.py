from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.integrations.tiktok.oauth import (
    TikTokOAuthConfigError,
    TikTokOAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    save_tiktok_tokens,
    verify_oauth_state,
)
from app.models.user import User

router = APIRouter(prefix="/tiktok/oauth", tags=["tiktok-oauth"])


@router.get("/start")
def start_tiktok_oauth(current_user: User = Depends(get_current_user)) -> RedirectResponse:
    try:
        authorization_url = build_authorization_url(current_user.id)
    except TikTokOAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return RedirectResponse(authorization_url)


@router.get("/callback")
def handle_tiktok_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str | UUID]:
    try:
        user_id = verify_oauth_state(state)
        token_data = exchange_code_for_tokens(code)
        social_account = save_tiktok_tokens(db, user_id, token_data)
    except TikTokOAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except TikTokOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": social_account.status, "account_id": social_account.id}

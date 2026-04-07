"""
Google OAuth 授權路由
GET  /v1/auth/google          — 取得授權 URL
GET  /v1/auth/callback        — OAuth callback
POST /v1/auth/session-bind    — 綁定 credentials 到 session
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()

# 暫存 state → session_id 對應（生產環境應用 Redis）
_pending: dict[str, str] = {}


@router.get("/google")
async def google_auth(session_id: str):
    """產生 Google 授權 URL"""
    from backend.integrations.auth_manager import get_authorization_url
    url, state = get_authorization_url()
    _pending[state] = session_id
    return {"auth_url": url, "state": state}


@router.get("/callback")
async def oauth_callback(code: str, state: str):
    """Google OAuth callback"""
    from backend.integrations.auth_manager import exchange_code
    from .session import get_session_store

    session_id = _pending.pop(state, None)
    if not session_id:
        raise HTTPException(status_code=400, detail="無效的 state 參數")

    try:
        creds = exchange_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"授權碼兌換失敗：{e}") from e

    sessions = get_session_store()
    sess = sessions.get(session_id)
    if sess:
        sess["calendar_credentials"] = creds

    return {"status": "ok", "message": "Google Calendar 已成功連結！可以關閉此頁面。"}

"""
Google OAuth 2.0 授權管理
"""
import os

from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_authorization_url() -> tuple[str, str]:
    """產生 Google OAuth 授權 URL，回傳 (url, state)"""
    flow = _create_flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    return url, state


def exchange_code(code: str, state: str) -> dict:
    """用授權碼換取 access token，回傳 credentials dict"""
    flow = _create_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }


def _create_flow() -> Flow:
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/v1/auth/callback")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

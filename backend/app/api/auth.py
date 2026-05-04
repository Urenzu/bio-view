from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import RedirectResponse

from app.config import settings
from app.storage.ledger import User, session_scope

router = APIRouter()

_ALGO = "HS256"
_EXPIRE_DAYS = 30


def _make_token(user_id: int) -> str:
    exp = datetime.utcnow() + timedelta(days=_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.secret_key, algorithm=_ALGO)


def decode_user_id(token: str | None) -> int | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGO])
        return int(payload["sub"])
    except Exception:
        return None


@router.get("/auth/me")
def auth_me(session_token: str | None = Cookie(default=None)):
    uid = decode_user_id(session_token)
    if uid is None:
        return {"user": None}
    with session_scope() as s:
        user = s.get(User, uid)
        if not user:
            return {"user": None}
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture,
            }
        }


@router.get("/auth/google")
def google_login():
    if not settings.google_client_id:
        raise HTTPException(501, "Google OAuth not configured — set GOOGLE_CLIENT_ID")
    params = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/auth/google/callback")
async def google_callback(code: str):
    if not settings.google_client_id:
        raise HTTPException(501, "Google OAuth not configured")

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, f"Token exchange failed: {token_data.get('error')}")

        info_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info = info_res.json()

    email = info.get("email")
    if not email:
        raise HTTPException(400, "No email returned from Google")

    with session_scope() as s:
        user = s.query(User).filter_by(google_sub=info["sub"]).first()
        if user is None:
            # Check if an account with this email already exists (e.g. future provider)
            user = s.query(User).filter_by(email=email).first()
        if user is None:
            user = User(
                email=email,
                name=info.get("name", ""),
                picture=info.get("picture", ""),
                google_sub=info.get("sub", ""),
            )
            s.add(user)
            s.flush()
        else:
            user.google_sub = info.get("sub", user.google_sub)
            user.name = info.get("name", user.name)
            user.picture = info.get("picture", user.picture)
        uid = user.id

    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie(
        "session_token",
        _make_token(uid),
        max_age=_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("session_token", samesite="lax")
    return {"ok": True}

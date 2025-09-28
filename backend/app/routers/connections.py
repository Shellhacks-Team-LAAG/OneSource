# app/routers/connections.py
from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_crypto, SessionLocal
from app.models import Connection, User

router = APIRouter(prefix="/connections", tags=["connections"])

# ---------- ENV ----------
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_CALLBACK_URL = os.getenv("GITHUB_CALLBACK_URL")

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_CALLBACK_URL = os.getenv("SLACK_CALLBACK_URL")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_CALLBACK_URL = os.getenv("GOOGLE_CALLBACK_URL")


# ---------- Helpers ----------
def _make_state() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(24)).decode().rstrip("=")

async def _get_or_create_demo_user(db: AsyncSession) -> int:
    """Hackathon-simple: ensure a demo user exists; return its id."""
    demo_email = os.getenv("DEMO_USER_EMAIL", "demo@onesource.local")
    res = await db.execute(select(User).where(User.email == demo_email))
    user = res.scalar_one_or_none()
    if user:
        return user.id
    user = User(email=demo_email)  # created_at default in model
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id

async def _upsert_connection(
    db: AsyncSession,
    provider: str,
    access_token: Optional[str],
    refresh_token: Optional[str],
    scopes: str = "",
    expires_at_dt: Optional[datetime] = None,
    user_id: Optional[int] = None,
) -> None:
    """
    Encrypt tokens (to strings) and upsert into connections for (user_id, provider).
    Matches models.py:
      - access_token_enc / refresh_token_enc are String columns
      - user_id is NOT NULL
      - expires_at is a datetime
    """
    if user_id is None:
        user_id = await _get_or_create_demo_user(db)

    fernet = get_crypto()
    access_token_enc = fernet.encrypt(access_token.encode()).decode() if access_token else None
    refresh_token_enc = fernet.encrypt(refresh_token.encode()).decode() if refresh_token else None

    res = await db.execute(
        select(Connection).where(Connection.provider == provider, Connection.user_id == user_id)
    )
    row = res.scalar_one_or_none()
    now = datetime.utcnow()

    if row:
        if access_token_enc:
            row.access_token_enc = access_token_enc
        row.refresh_token_enc = refresh_token_enc
        row.scopes = scopes
        row.expires_at = expires_at_dt
        row.updated_at = now
    else:
        row = Connection(
            user_id=user_id,
            provider=provider,
            access_token_enc=access_token_enc,
            refresh_token_enc=refresh_token_enc,
            scopes=scopes,
            expires_at=expires_at_dt,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    await db.commit()


# ===========================
# Slack OAuth
# ===========================
@router.post("/slack/authorize")
async def slack_authorize():
    if not (SLACK_CLIENT_ID and SLACK_CALLBACK_URL):
        raise HTTPException(500, "Slack env not configured")
    state = _make_state()
    scopes = "channels:read,groups:read,channels:history,groups:history,pins:read,users:read"
    url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&redirect_uri={SLACK_CALLBACK_URL}"
        f"&scope={scopes}"
        f"&state={state}"
    )
    return {"authorize_url": url, "state": state}

@router.get("/slack/callback")
async def slack_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    if not (SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_CALLBACK_URL):
        raise HTTPException(500, "Slack env not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_CALLBACK_URL,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(400, f"Slack OAuth failed: {data}")

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    scopes = data.get("scope", "")
    expires_in = data.get("expires_in")
    expires_at_dt = datetime.utcnow() + timedelta(seconds=int(expires_in)) if expires_in else None

    await _upsert_connection(
        db,
        provider="slack",
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        expires_at_dt=expires_at_dt,
        user_id=None,
    )
    return JSONResponse({"ok": True})

# Dev-only helper to load a token you already have
@router.post("/slack/dev-set-token")
async def slack_dev_set_token(payload: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(400, "access_token required")
    refresh_token = payload.get("refresh_token")
    scopes = payload.get("scopes", "")
    expires_in = int(payload.get("expires_in") or 0)
    expires_at_dt = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    await _upsert_connection(
        db,
        provider="slack",
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        expires_at_dt=expires_at_dt,
        user_id=None,
    )
    return {"ok": True}


# ===========================
# Google Drive OAuth
# ===========================
@router.post("/drive/authorize")
async def drive_authorize():
    import httpx as _hx  # just for QueryParams encoding
    if not (GOOGLE_CLIENT_ID and GOOGLE_CALLBACK_URL):
        raise HTTPException(500, "Google env not configured")

    state = _make_state()
    scope = "https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/documents.readonly"
    qp = _hx.QueryParams({"scope": scope}).get("scope")  # encodes spaces as '+'
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_CALLBACK_URL}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&include_granted_scopes=true"
        f"&scope={qp}"
        f"&state={state}"
        f"&prompt=consent"
    )
    return {"authorize_url": url, "state": state}

@router.get("/drive/callback")
async def drive_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_CALLBACK_URL):
        raise HTTPException(500, "Google env not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_CALLBACK_URL,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(400, f"Google OAuth failed: {data}")

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token")
    scopes = data.get("scope", "")
    expires_in = int(data.get("expires_in") or 0)
    expires_at_dt = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    await _upsert_connection(
        db,
        provider="drive",
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        expires_at_dt=expires_at_dt,
        user_id=None,
    )
    return JSONResponse({"ok": True})


# ===========================
# GitHub OAuth
# ===========================
@router.post("/github/authorize")
async def github_authorize():
    if not (GITHUB_CLIENT_ID and GITHUB_CALLBACK_URL):
        raise HTTPException(500, "GitHub OAuth not configured")
    scope = "repo read:user"
    state = _make_state()
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_CALLBACK_URL}"
        f"&scope={scope}"
        f"&state={state}"
    )
    return {"authorize_url": url, "state": state}

@router.get("/github/callback")
async def github_callback(code: str = Query(...), state: str | None = None, db: AsyncSession = Depends(get_db)):
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and GITHUB_CALLBACK_URL):
        raise HTTPException(500, "GitHub OAuth not configured")

    token_url = "https://github.com/login/oauth/access_token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_url,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_CALLBACK_URL,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Token exchange failed: {resp.text}")

    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(502, f"No access token returned: {token_data}")

    scopes = token_data.get("scope", "")

    await _upsert_connection(
        db,
        provider="github",
        access_token=access_token,
        refresh_token=None,
        scopes=scopes,
        expires_at_dt=None,
        user_id=None,
    )
    return {"ok": True, "provider": "github"}


# ===========================
# Connections status
# ===========================
@router.get("")
async def get_connections_status(user_id: int | None = None):
    uid = user_id or 1
    providers = {"slack": False, "drive": False, "github": False}
    async with SessionLocal() as db:
        q = await db.execute(
            select(Connection.provider, Connection.access_token_enc)
            .where(Connection.user_id == uid)
        )
        rows = q.fetchall()
        for prov, enc in rows:
            # Only true if a real encrypted token string is saved
            if enc and isinstance(enc, str) and enc.strip() and enc != "FAKE_ENCRYPTED":
                providers[prov] = True
    return providers

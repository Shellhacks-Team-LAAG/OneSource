# app/routers/connections.py
from fastapi import APIRouter, HTTPException, Request, Query
from sqlalchemy import select
from app.deps import SessionLocal
from app.models import Connection
from app.services import crypto
import httpx
import os

router = APIRouter(prefix="/connections", tags=["connections"])

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_CALLBACK_URL = os.getenv("GITHUB_CALLBACK_URL")

@router.get("")
async def get_connections_status(user_id: int | None = None):
    uid = user_id or 1
    providers = {"slack": False, "drive": False, "github": False}
    async with SessionLocal() as db:
        q = await db.execute(select(Connection.provider).where(Connection.user_id == uid))
        rows = q.fetchall()
        for (prov,) in rows:
            providers[prov] = True
    return providers

@router.post("/{provider}/authorize")
async def start_authorize(provider: str, user_id: int | None = None):
    if provider not in ("slack", "drive", "github"):
        raise HTTPException(400, "Unknown provider")

    if provider == "github":
        if not (GITHUB_CLIENT_ID and GITHUB_CALLBACK_URL):
            raise HTTPException(500, "GitHub OAuth not configured")
        scope = "repo read:user"
        state = "onelogin"  # TODO: make dynamic for security
        url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={GITHUB_CLIENT_ID}"
            f"&redirect_uri={GITHUB_CALLBACK_URL}"
            f"&scope={scope}"
            f"&state={state}"
        )
        return {"authorize_url": url}

    return {"authorize_url": f"https://example.com/oauth/{provider}/start"}

@router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str = Query(...), state: str | None = None, user_id: int | None = None):
    uid = user_id or 1

    if provider == "github":
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

        enc_token = crypto.enc(access_token)

        async with SessionLocal() as db:
            existing = await db.execute(
                select(Connection).where(Connection.user_id == uid, Connection.provider == provider)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.access_token_enc = enc_token
            else:
                c = Connection(
                    user_id=uid,
                    provider=provider,
                    access_token_enc=enc_token,
                    refresh_token_enc=None,
                    scopes=token_data.get("scope"),
                    expires_at=None,
                )
                db.add(c)
            await db.commit()

        return {"ok": True, "provider": provider}

    # fallback for other providers
    async with SessionLocal() as db:
        existing = await db.execute(
            select(Connection).where(Connection.user_id == uid, Connection.provider == provider)
        )
        row = existing.scalar_one_or_none()
        if row:
            row.access_token_enc = "FAKE_ENCRYPTED"
        else:
            c = Connection(
                user_id=uid,
                provider=provider,
                access_token_enc="FAKE_ENCRYPTED",
                refresh_token_enc=None,
                scopes=None,
                expires_at=None,
            )
            db.add(c)
        await db.commit()

    return {"ok": True}

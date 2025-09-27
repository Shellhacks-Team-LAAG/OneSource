# app/routers/connections.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.deps import SessionLocal
from app.models import Connection

router = APIRouter(prefix="/connections", tags=["connections"])

@router.get("")
async def get_connections_status(user_id: int | None = None):
    # hackathon: no auth, use user_id=None or 1
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
    # Hackathon placeholder: return the URL frontend should open (teammates fill for their providers)
    if provider not in ("slack", "drive", "github"):
        raise HTTPException(400, "Unknown provider")
    # TODO: construct real OAuth URL with state
    return {"authorize_url": f"https://example.com/oauth/{provider}/start"}

@router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str | None = None, user_id: int | None = None):
    # TODO: exchange code for tokens, encrypt and store in connections table
    # Placeholder stores a fake token so UI can show 'connected'
    uid = user_id or 1
    async with SessionLocal() as db:
        # upsert by (user_id, provider)
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

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# ---- Load .env early (once) ----
try:
    from dotenv import load_dotenv
    # backend/.env relative to this file
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
except Exception:
    # If python-dotenv isn't installed, env may be provided by the shell; that's OK.
    pass

# ---- DB config ----
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

class Base(DeclarativeBase):
    pass

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

# ---- Crypto dep (import AFTER .env is loaded) ----
from app.services.crypto import get_fernet as _get_fernet_singleton  # noqa: E402

def get_crypto():
    """Return process-wide Fernet/MultiFernet instance (lazy)."""
    return _get_fernet_singleton()

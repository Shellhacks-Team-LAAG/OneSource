# app/services/crypto.py
from __future__ import annotations

import base64
import os
from typing import List
from cryptography.fernet import Fernet, MultiFernet

_FERNET = None  # singleton

def _coerce_to_fernet_key(raw: str) -> bytes:
    """Accepts either a urlsafe base64 Fernet key (44 chars) or a passphrase."""
    raw = raw.strip()
    if len(raw) == 44:
        return raw.encode()
    b = raw.encode("utf-8")
    if len(b) < 32:
        b = b.ljust(32, b"0")
    elif len(b) > 32:
        b = b[:32]
    return base64.urlsafe_b64encode(b)

def get_fernet():
    """
    Lazily construct a Fernet (or MultiFernet) from APP_ENCRYPTION_KEY.
    Never read env at module import; only when this function is called.
    """
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    key_env = os.getenv("APP_ENCRYPTION_KEY")
    if not key_env:
        raise RuntimeError("APP_ENCRYPTION_KEY not set")

    parts: List[str] = [p for p in key_env.split(",") if p.strip()]
    fernets = [Fernet(_coerce_to_fernet_key(p)) for p in parts]
    _FERNET = MultiFernet(fernets) if len(fernets) > 1 else fernets[0]
    return _FERNET

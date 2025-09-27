# app/services/crypto.py
import os
from cryptography.fernet import Fernet, InvalidToken

_key = os.getenv("APP_ENCRYPTION_KEY")
if not _key:
    raise RuntimeError("APP_ENCRYPTION_KEY not set")

fernet = Fernet(_key.encode() if not _key.startswith("gAAAA") else _key)  # tolerate string

def enc(plain: str | None) -> str | None:
    if plain is None:
        return None
    return fernet.encrypt(plain.encode()).decode()

def dec(token: str | None) -> str | None:
    if token is None:
        return None
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None

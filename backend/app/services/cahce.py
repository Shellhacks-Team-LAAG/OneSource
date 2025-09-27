# app/services/cache.py
import time
from typing import Any, Dict, Tuple

class TTLCache:
    def __init__(self, ttl_seconds: int = 180):
        self.ttl = ttl_seconds
        self.store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.time()
        item = self.store.get(key)
        if not item:
            return None
        expires_at, value = item
        if now > expires_at:
            self.store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any):
        self.store[key] = (time.time() + self.ttl, value)

# Per-provider caches (use keys like f"{user_id}:{hash(query)}")
drive_cache = TTLCache(ttl_seconds=180)   # 3 min
github_cache = TTLCache(ttl_seconds=180)
slack_cache = TTLCache(ttl_seconds=120)

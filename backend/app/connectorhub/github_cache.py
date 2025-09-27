# app/connectorhub/github_cache.py
import time

CACHE = {}
CACHE_EXPIRY = 300  # seconds

def get_from_cache(key):
    entry = CACHE.get(key)
    if entry:
        value, expiry = entry
        if time.time() < expiry:
            print(f"[CACHE HIT] Key: {key}")
            return value
        else:
            print(f"[CACHE EXPIRED] Key: {key}")
            CACHE.pop(key)
    print(f"[CACHE MISS] Key: {key}")
    return None

def set_to_cache(key, value):
    expiry = time.time() + CACHE_EXPIRY
    CACHE[key] = (value, expiry)
    print(f"[CACHE SET] Key: {key}, expires in {CACHE_EXPIRY} seconds")

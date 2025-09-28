# app/connectorhub/slack.py
from __future__ import annotations
from typing import List, Optional
from datetime import datetime, timezone
import os, httpx, re, logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Connection
from app.deps import get_crypto
from app.schemas import NormalizedCandidate

SLACK_CHANNELS = os.getenv("SLACK_CHANNELS", "")   # e.g., "C123,C456"
SLACK_FAST = os.getenv("SLACK_FAST", "0") == "1"   # pins-only fast path

_HEADING_RE = re.compile(r"^[\*\_\~\s]*([^:\n]{1,200}):\s*$")

async def _get_token(db: AsyncSession) -> Optional[str]:
    row = (await db.execute(
        select(Connection).where(Connection.provider == "slack")
    )).scalar_one_or_none()
    if not row or not row.access_token_enc:
        return None
    try:
        return get_crypto().decrypt(row.access_token_enc.encode()).decode()
    except Exception:
        logging.exception("slack_token_decrypt_failed")
        return None

def _dt_from_ts(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)

async def _slack_get(client: httpx.AsyncClient, token: str, path: str, params: dict | None = None) -> dict:
    r = await client.get(
        f"https://slack.com/api/{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    try:
        data = r.json()
    except Exception:
        return {"ok": False, "error": f"http_{r.status_code}"}
    # Treat rate limit explicitly so hub can tag it if needed (we just return empty here)
    if data.get("error") in {"ratelimited"}:
        return {"ok": False, "error": "ratelimited"}
    return data

def _preview(text: str) -> str:
    """
    Build a compact preview:
    - take the first non-empty line
    - if it ends with a colon, append the next non-empty line
    - soft-trim to ~240 chars
    """
    if not text:
        return ""
    # normalize newlines and strip
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # all non-empty logical lines (no paragraph restriction)
    lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]
    if not lines:
        return ""

    first = lines[0]
    # include second line if the first looks like a heading (ends with ':')
    if first.endswith(":") and len(lines) > 1:
        combined = f"{first} {lines[1]}"
        return (combined[:240]).rstrip()

    # otherwise just the first line
    return (first[:240]).rstrip()


async def _pins_fast(client: httpx.AsyncClient, token: str, cid: str, query: str, limit: int) -> List[NormalizedCandidate]:
    pins = await _slack_get(client, token, "pins.list", {"channel": cid})
    if not pins.get("ok"):
        return []
    out: List[NormalizedCandidate] = []
    matched: List[NormalizedCandidate] = []
    # cache permalinks per ts to avoid double calls if you like (kept simple here)
    for it in pins.get("items", []):
        msg = it.get("message") or {}
        text = msg.get("text") or ""
        ts = msg.get("ts")
        if not text or not ts:
            continue
        pl = await _slack_get(client, token, "chat.getPermalink", {"channel": cid, "message_ts": ts})
        if not pl.get("ok"):
            continue
        cand = NormalizedCandidate(
            source="slack",
            doc_id=f"{cid}:{ts}",
            url=pl.get("permalink",""),
            title="Slack thread",
            snippet=_preview(text),
            last_modified=_dt_from_ts(ts),
            owner="slack",
            signals={"pinned": True, "accepted": ("✅" in text)},
        )
        if query and query.lower() in text.lower():
            matched.append(cand)
        else:
            out.append(cand)
        if len(matched) >= limit:
            return matched[:limit]
    return (matched or out)[:limit]

async def search_corpus(user_id: int | None, query: str, limit: int, db: AsyncSession) -> List[NormalizedCandidate]:
    token = await _get_token(db)
    if not token:
        return []

    channels = [c.strip() for c in SLACK_CHANNELS.split(",") if c.strip()]
    out: List[NormalizedCandidate] = []
    matched: List[NormalizedCandidate] = []

    async with httpx.AsyncClient() as client:
        # FAST mode (pins on single channel) with auto-fallback
        if SLACK_FAST:
            if not channels or len(channels) != 1:
                logging.info("slack_fast_requires_single_channel")
            else:
                cands = await _pins_fast(client, token, channels[0], query, limit)
                if cands:
                    return cands
                # no pins or no match → fall back to normal mode below
                logging.info("slack_fast_empty_falling_back")

        # NORMAL mode: discover channels if not provided, scan recent history + pins
        if not channels:
            res = await _slack_get(client, token, "conversations.list",
                                   {"limit": 60, "types": "public_channel,private_channel"})
            if not res.get("ok"):
                logging.info("slack_conversations_list_failed error=%s", res.get("error"))
                return []
            channels = [ch["id"] for ch in res.get("channels", [])]

        for cid in channels:
            pins = await _slack_get(client, token, "pins.list", {"channel": cid})
            pinned_ts = set()
            if pins.get("ok"):
                for it in pins.get("items", []):
                    msg = it.get("message") or {}
                    if "ts" in msg:
                        pinned_ts.add(msg["ts"])

            hist = await _slack_get(client, token, "conversations.history", {"channel": cid, "limit": 120})
            if not hist.get("ok"):
                continue
            for m in hist.get("messages", []):
                text = m.get("text") or ""
                ts = m.get("ts")
                if not text or not ts:
                    continue
                accepted = "✅" in text
                pinned = ts in pinned_ts
                if not (accepted or pinned):
                    continue
                if query and query.lower() not in text.lower():
                    continue
                pl = await _slack_get(client, token, "chat.getPermalink", {"channel": cid, "message_ts": ts})
                if not pl.get("ok"):
                    continue
                cand = NormalizedCandidate(
                    source="slack",
                    doc_id=f"{cid}:{ts}",
                    url=pl.get("permalink",""),
                    title="Slack thread",
                    snippet=_preview(text),
                    last_modified=_dt_from_ts(ts),
                    owner="slack",
                    signals={"pinned": pinned, "accepted": accepted},
                )
                matched.append(cand)
                if len(matched) >= limit:
                    return matched[:limit]

        return matched[:limit] if matched else out[:limit]

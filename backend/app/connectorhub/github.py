from __future__ import annotations
import os, asyncio, httpx
from datetime import datetime, timezone
from typing import List, Optional, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.deps import get_crypto
from app.models import Connection
from app.schemas import NormalizedCandidate

GITHUB_API_URL = "https://api.github.com"
GITHUB_ORG = os.getenv("GITHUB_ORG", "").strip()
GITHUB_REPOS = [r.strip() for r in os.getenv("GITHUB_REPOS", "").split(",") if r.strip()]


async def _get_token(db: AsyncSession) -> Optional[str]:
    row = (await db.execute(
        select(Connection).where(Connection.provider == "github")
    )).scalar_one_or_none()
    if not row or not row.access_token_enc:
        return None
    return get_crypto().decrypt(row.access_token_enc.encode()).decode()


def _iso(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _build_q(user_q: str) -> str:
    """
    Scope the search to your org or repos to avoid public GitHub noise.
    """
    parts: List[str] = []
    uq = (user_q or "").strip()
    if uq:
        parts.append(uq)
    # doc-like bias
    parts += ["in:file", "path:/docs", "filename:README.md"]

    if GITHUB_ORG:
        parts.append(f"org:{GITHUB_ORG}")
    elif GITHUB_REPOS:
        for repo in GITHUB_REPOS:
            parts.append(f"repo:{repo}")
    else:
        # Nothing to scope → skip adapter
        return ""
    return " ".join(parts)


async def search_corpus(
    user_id: int | None,
    query: str,
    limit: int,
    db: AsyncSession
) -> List[NormalizedCandidate]:
    token = await _get_token(db)
    if not token:
        return []

    q = _build_q(query)
    if not q:
        return []  # not scoped → do nothing

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {"q": q, "per_page": max(1, min(50, limit * 2))}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await asyncio.wait_for(
                client.get(f"{GITHUB_API_URL}/search/code", headers=headers, params=params),
                timeout=1.5,
            )
        except asyncio.TimeoutError:
            return []
    if resp.status_code != 200:
        return []

    items = resp.json().get("items", [])
    out: List[NormalizedCandidate] = []
    for it in items:
        repo = it.get("repository") or {}
        repo_full = repo.get("full_name", "")
        path = it.get("path", "")
        html_url = it.get("html_url", "")

        title = f"{repo_full}/{path}" if repo_full and path else (html_url or path or "doc")
        snippet = title[:240]

        out.append(NormalizedCandidate(
            source="github",
            doc_id=f"{repo_full}:{path}",
            url=html_url or (f"https://github.com/{repo_full}/blob/main/{path}" if repo_full and path else ""),
            title=title,
            snippet=snippet,
            last_modified=_iso(repo.get("updated_at")),
            owner=(repo.get("owner", {}) or {}).get("login", "") or (repo_full.split("/")[0] if repo_full else ""),
            signals={
                "path_hint": "/docs" if "/docs/" in f"/{path}" else "",
                "approved_pr": 0,  # optional enrichment later
            },
        ))
        if len(out) >= limit:
            break
    return out

import asyncio
import httpx
from typing import List, Dict
from sqlalchemy import select
from app.deps import SessionLocal
from app.models import Connection
from app.services import crypto
from app.connectorhub.github_normalize import normalize_github_result

GITHUB_API_URL = "https://api.github.com"


async def search_corpus(user_id: int, query: str, limit: int = 10) -> List[Dict]:
    """
    Search GitHub repos for relevant documentation files.
    Returns a list of NormalizedCandidate objects.
    """
    async with SessionLocal() as db:
        conn = await db.execute(
            select(Connection).where(Connection.user_id == user_id, Connection.provider == "github")
        )
        row = conn.scalar_one_or_none()
        if not row:
            return []

        token = crypto.dec(row.access_token_enc)
        if not token:
            return []

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    params = {"q": f"{query} in:file path:/docs filename:README.md"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await asyncio.wait_for(
                client.get(f"{GITHUB_API_URL}/search/code", headers=headers, params=params),
                timeout=1.5
            )
        except asyncio.TimeoutError:
            return []

    if resp.status_code == 429:
        return [{"rate_limited": 1}]

    if resp.status_code != 200:
        return []

    results = resp.json().get("items", [])[:limit]
    normalized_results = [normalize_github_result(item) for item in results]

    return normalized_results


async def fetch_doc(user_id: int, repo_full_name: str, path: str) -> Dict:
    """
    Fetch the full content of a specific file in a repo.
    """
    async with SessionLocal() as db:
        conn = await db.execute(
            select(Connection).where(Connection.user_id == user_id, Connection.provider == "github")
        )
        row = conn.scalar_one_or_none()
        if not row:
            return {}

        token = crypto.dec(row.access_token_enc)
        if not token:
            return {}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await asyncio.wait_for(
                client.get(f"{GITHUB_API_URL}/repos/{repo_full_name}/contents/{path}"),
                timeout=1.5
            )
        except asyncio.TimeoutError:
            return {}

    if resp.status_code != 200:
        return {}

    return {
        "content": resp.text,
        "path": path,
        "repo": repo_full_name,
        "last_modified": resp.headers.get("Last-Modified")
    }

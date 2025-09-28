#drive.py
from __future__ import annotations
from typing import List, Optional
from datetime import datetime
import os, httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Connection
from app.deps import get_crypto
from app.schemas import NormalizedCandidate

DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "").strip()


async def _get_token(db: AsyncSession) -> Optional[str]:
    row = (await db.execute(
        select(Connection).where(Connection.provider == "drive")
    )).scalar_one_or_none()
    if not row or not row.access_token_enc:
        return None
    return get_crypto().decrypt(row.access_token_enc.encode()).decode()


def _parse_rfc3339(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


async def search_corpus(
    user_id: int | None,
    query: str,
    limit: int,
    db: AsyncSession
) -> List[NormalizedCandidate]:
    token = await _get_token(db)
    if not token or not DRIVE_FOLDER_ID:
        return []

    # Scope to a folder; minimal sanitize for the Drive query
    q_parts = [f"'{DRIVE_FOLDER_ID}' in parents", "trashed = false"]
    if query:
        safe = query.replace("'", " ")
        q_parts.append(f"(name contains '{safe}' or fullText contains '{safe}')")
    q = " and ".join(q_parts)
    params = {
    "q": q,
    "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners(emailAddress,displayName)),nextPageToken",
    "pageSize": 25,
    "orderBy": "modifiedTime desc",
    "supportsAllDrives": "true",
    "includeItemsFromAllDrives": "true",
    }
    fields = "files(id,name,mimeType,modifiedTime,webViewLink,owners(emailAddress,displayName)),nextPageToken"

    out: List[NormalizedCandidate] = []
    page_token = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            if page_token:
                params["pageToken"] = page_token

            r = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                break
            data = r.json()
            for f in data.get("files", []):
                owners = f.get("owners", [])
                owner = ""
                if owners:
                    owner = owners[0].get("emailAddress") or owners[0].get("displayName") or ""

                out.append(NormalizedCandidate(
                    source="drive",
                    doc_id=f["id"],
                    url=f.get("webViewLink", ""),
                    title=f.get("name", ""),
                    snippet=f"{f.get('name','')} — {f.get('mimeType','')}",
                    last_modified=_parse_rfc3339(f["modifiedTime"]),
                    owner=owner,
                    signals={"mime": f.get("mimeType", ""), "folder": "Runbooks"},
                ))
                if len(out) >= limit:
                    return out

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return out

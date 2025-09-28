# app/connectorhub/__init__.py
from __future__ import annotations
import asyncio, logging, time
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import NormalizedCandidate

# Adapters (optional if not present)
try:
    from app.connectorhub import slack as slack_adapter
except Exception:
    slack_adapter = None
try:
    from app.connectorhub import drive as drive_adapter
except Exception:
    drive_adapter = None
try:
    from app.connectorhub import github as github_adapter
except Exception:
    github_adapter = None


async def _call_with_timeout(coro, timeout_s: float):
    return await asyncio.wait_for(coro, timeout=timeout_s)


def _coerce_candidates(raw: List[Any]) -> List[NormalizedCandidate]:
    """
    Adapters should return List[NormalizedCandidate]. If any returns dicts with the same keys,
    coerce them, otherwise drop and log.
    """
    coerced: List[NormalizedCandidate] = []
    for item in raw or []:
        if isinstance(item, NormalizedCandidate):
            coerced.append(item)
        elif isinstance(item, dict) and "source" in item and "url" in item and "doc_id" in item:
            try:
                coerced.append(NormalizedCandidate(**item))
            except Exception as e:
                logging.warning("normalize_candidate_failed err=%s item_keys=%s", e.__class__.__name__, list(item.keys()))
        else:
            logging.warning("unexpected_candidate_type type=%s keys=%s", type(item).__name__, list(item.keys()) if isinstance(item, dict) else None)
    return coerced


async def gather_candidates(
    db: AsyncSession,
    user_id: int | None,
    query: str,
    limit: int = 5,
    timeout_each: float = 3.0,
) -> Tuple[List[NormalizedCandidate], Dict[str, dict]]:
    """
    Run Slack/Drive/GitHub adapters in parallel.
    Returns (candidates, timings/flags) where timings looks like:
    {
      "slack":  {"ms": 123, "timeout": 0, "error": "", "rate_limited": 0},
      "drive":  {"ms":  98, "timeout": 0, "error": "", "rate_limited": 0},
      "github": {"ms": 210, "timeout": 1, "error": "", "rate_limited": 0},
    }
    """
    providers = []
    if slack_adapter and hasattr(slack_adapter, "search_corpus"):
        providers.append(("slack", slack_adapter.search_corpus))
    if drive_adapter and hasattr(drive_adapter, "search_corpus"):
        providers.append(("drive", drive_adapter.search_corpus))
    if github_adapter and hasattr(github_adapter, "search_corpus"):
        providers.append(("github", github_adapter.search_corpus))

    timings: Dict[str, dict] = {}
    tasks = []

    for name, fn in providers:
        async def runner(_name=name, _fn=fn):
            info = {"ms": 0, "timeout": 0, "error": "", "rate_limited": 0}
            t0 = time.perf_counter()
            try:
                # Each adapter signature: (user_id, query, limit, db)
                res = await _call_with_timeout(_fn(user_id, query, limit, db), timeout_each)
                info["ms"] = int((time.perf_counter() - t0) * 1000)
                # Some adapters might return a sentinel for rate limit (e.g., [{"rate_limited":1}])
                if isinstance(res, list) and len(res) == 1 and isinstance(res[0], dict) and res[0].get("rate_limited"):
                    info["rate_limited"] = 1
                    res = []
                return _name, res or [], info
            except asyncio.TimeoutError:
                info["timeout"] = 1
                info["ms"] = int((time.perf_counter() - t0) * 1000)
                return _name, [], info
            except Exception as e:
                info["error"] = e.__class__.__name__
                info["ms"] = int((time.perf_counter() - t0) * 1000)
                logging.exception("provider_error name=%s", _name)
                return _name, [], info

        tasks.append(runner())

    results = await asyncio.gather(*tasks) if tasks else []

    merged: List[NormalizedCandidate] = []
    for name, res, info in results:
        # Coerce to NormalizedCandidate if adapter returned dicts
        coerced = _coerce_candidates(res)
        timings[name] = info | {"count": len(coerced)}
        merged.extend(coerced)

    # Helpful single-line summary in Uvicorn console
    logging.info(
        "connectorhub.summary %s",
        {k: {"ms": v["ms"], "timeout": v["timeout"], "error": v["error"], "rate_limited": v.get("rate_limited", 0), "count": v.get("count", 0)}
         for k, v in timings.items()}
    )

    # IMPORTANT: don't slice here; let Fusion see all candidates
    return merged, timings

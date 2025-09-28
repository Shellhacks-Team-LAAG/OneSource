# app/main.py
from __future__ import annotations

import logging
import time
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import engine, Base, get_db
from app.models import QueryLog
from app.schemas import AskResponse, Citation, NormalizedCandidate
from app.fusion.rank import rank as fusion_rank
from app.policy.guard import guard as policy_guard
from app.services.logging import (
    get_logger,
    new_trace_id,
    bind_trace_id,
    get_trace_id,
    log_kv,
)
from app.routers.connections import router as connections_router
from app.connectorhub import gather_candidates


# ---------- Lifespan (startup/shutdown) ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (hackathon-simple; Alembic optional)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # No shutdown hooks needed for now


app = FastAPI(title="OneSource Backend (Phase 4)", lifespan=lifespan)
LOG = get_logger("backend")
app.include_router(connections_router)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Per-request trace middleware ----------
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    tid = new_trace_id()
    bind_trace_id(tid)

    start = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_kv(
            LOG,
            logging.INFO,
            "request.complete",
            method=request.method,
            path=request.url.path,
            status=getattr(response, "status_code", 0) if response else 0,
            duration_ms=duration_ms,
        )

    if response:
        response.headers["X-Trace-Id"] = get_trace_id()
        return response

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error before response generation."},
        headers={"X-Trace-Id": get_trace_id()},
    )


# ---------- Health ----------
@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ---------- In-memory trace store ----------
TRACE_STORE: Dict[str, dict] = {}


# ---------- Request schema ----------
class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=256)


def _summarize_answer(snippet: str) -> str:
    """Prefer first paragraph, tidy heading lines, soft-trim ~240 chars."""
    para = snippet.strip().split("\n\n", 1)[0].strip()
    lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
    if lines and lines[0].endswith(":") and len(lines) > 1:
        text = f"{lines[0]} {lines[1]}"
    else:
        text = lines[0] if lines else snippet.strip()
    if len(text) > 240:
        text = re.sub(r"\s+\S*$", "", text[:240]) + "…"
    return text


# ---------- POST /ask (ConnectorHub → Fusion → Policy) ----------
@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(
    payload: AskRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # 1) Validate
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # 2) Trace id (from middleware)
    trace_id = get_trace_id()

    # 3) Start latency timer
    t0 = time.perf_counter()

    # 4) Fetch candidates from providers in parallel via ConnectorHub
    candidates: List[NormalizedCandidate]
    provider_meta: Dict[str, dict]
    candidates, provider_meta = await gather_candidates(
        db=db, user_id=None, query=query, limit=5
    )

    # If zero providers produced candidates, record a trace and raise 503 (with trace_id)
    if not candidates:
        TRACE_STORE[trace_id] = {
            "trace_id": trace_id,
            "query": query,
            "timings_ms": {
                "slack": provider_meta.get("slack", {}).get("ms", 0),
                "drive": provider_meta.get("drive", {}).get("ms", 0),
                "github": provider_meta.get("github", {}).get("ms", 0),
                "fusion": 0,
                "policy": 0,
            },
            "provider_flags": {
                "slack": {
                    "timeout": provider_meta.get("slack", {}).get("timeout", False),
                    "error": provider_meta.get("slack", {}).get("error"),
                    "rate_limited": provider_meta.get("slack", {}).get("rate_limited", 0),
                },
                "drive": {
                    "timeout": provider_meta.get("drive", {}).get("timeout", False),
                    "error": provider_meta.get("drive", {}).get("error"),
                    "rate_limited": provider_meta.get("drive", {}).get("rate_limited", 0),
                },
                "github": {
                    "timeout": provider_meta.get("github", {}).get("timeout", False),
                    "error": provider_meta.get("github", {}).get("error"),
                    "rate_limited": provider_meta.get("github", {}).get("rate_limited", 0),
                },
            },
            "candidates": [],
            "chosen": {"url": "", "score": 0.0, "explanations": ["no_providers"]},
            "policy": {"redactions": [], "conflict": False},
        }
        # include trace_id in the error payload so you can /trace it
        raise HTTPException(status_code=503, detail={"message": "No providers available", "trace_id": trace_id})

    # 5) Fusion: score and choose
    chosen, scores_by_id, reasons_by_id = fusion_rank(candidates, query)

    # 6) Sort by score (desc) for citations
    sorted_by_score = sorted(candidates, key=lambda c: scores_by_id[c.doc_id], reverse=True)

    # 7) Build citations (top 2–3 distinct URLs)
    citations: List[Citation] = []
    seen_urls = set()
    for c in sorted_by_score:
        if c.url in seen_urls:
            continue
        citations.append(Citation(label=c.source.capitalize(), url=c.url))
        seen_urls.add(c.url)
        if len(citations) >= 3:
            break

    # 8) Policy: redaction + conflict banner
    chosen_after_policy, redactions, conflict, banner = policy_guard(
        chosen, sorted_by_score, scores_by_id
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 9) Confidence (0..1) from chosen score
    chosen_score = float(scores_by_id[chosen_after_policy.doc_id])
    confidence = max(0.0, min(1.0, chosen_score))

    # 10) Freshness from chosen candidate
    freshness = chosen_after_policy.last_modified

    # 11) Answer text (summarized)
    answer_text = _summarize_answer(chosen_after_policy.snippet)

    resp = AskResponse(
        trace_id=trace_id,
        answer=answer_text,
        citations=citations,
        freshness=freshness,
        confidence=confidence,
        policy_banner=(banner or None),
    )

    # 12) Save enriched trace with provider timings/flags
    TRACE_STORE[trace_id] = {
        "trace_id": trace_id,
        "query": query,
        "timings_ms": {
            "slack": provider_meta.get("slack", {}).get("ms", 0),
            "drive": provider_meta.get("drive", {}).get("ms", 0),
            "github": provider_meta.get("github", {}).get("ms", 0),
            "fusion": 2,
            "policy": 1,
        },
        "provider_flags": {
            "slack": {
                "timeout": provider_meta.get("slack", {}).get("timeout", False),
                "error": provider_meta.get("slack", {}).get("error"),
                "rate_limited": provider_meta.get("slack", {}).get("rate_limited", 0),
            },
            "drive": {
                "timeout": provider_meta.get("drive", {}).get("timeout", False),
                "error": provider_meta.get("drive", {}).get("error"),
                "rate_limited": provider_meta.get("drive", {}).get("rate_limited", 0),
            },
            "github": {
                "timeout": provider_meta.get("github", {}).get("timeout", False),
                "error": provider_meta.get("github", {}).get("error"),
                "rate_limited": provider_meta.get("github", {}).get("rate_limited", 0),
            },
        },
        "candidates": [
            {
                "source": c.source,
                "url": str(c.url),
                "score": float(scores_by_id[c.doc_id]),
                "reasons": reasons_by_id[c.doc_id],
            }
            for c in sorted_by_score
        ],
        "chosen": {
            "url": str(chosen_after_policy.url),
            "score": confidence,
            "explanations": reasons_by_id[chosen_after_policy.doc_id],
        },
        "policy": {"redactions": redactions, "conflict": conflict},
    }

    # 13) QueryLog row (DB)
    top_sources = {c.source: float(scores_by_id[c.doc_id]) for c in sorted_by_score[:3]}
    ql = QueryLog(
        trace_id=trace_id,
        user_id=None,
        query=query,
        top_sources=top_sources,
        latency_ms=latency_ms,
    )
    db.add(ql)
    await db.commit()

    # 14) Log
    log_kv(
        LOG,
        logging.INFO,
        "ask.complete",
        route="/ask",
        chosen_source=chosen_after_policy.source,
        chosen_score=f"{confidence:.2f}",
        conflict=int(conflict),
        citations=len(citations),
        latency_ms=latency_ms,
    )

    return resp


# ---------- GET /trace/{trace_id} ----------
@app.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    trace = TRACE_STORE.get(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace

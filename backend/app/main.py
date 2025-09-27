# app/main.py
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from app.deps import engine, Base, get_db, SessionLocal
from app.models import QueryLog
from app.schemas import AskResponse, Citation, NormalizedCandidate  # your schemas
from app.fusion.rank import rank as fusion_rank
from app.policy.guard import guard as policy_guard
from app.services.logging import get_logger, new_trace_id, bind_trace_id, get_trace_id, log_kv
from app.routers.connections import router as connections_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables (hackathon-simple; Alembic optional)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: nothing for now

app = FastAPI(title="OneSource Backend (Phase 3)", lifespan=lifespan)
LOG = get_logger("backend")
app.include_router(connections_router)

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Per-request trace middleware ===
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

# === Health ===
@app.get("/healthz")
async def healthz():
    return {"ok": True}

# === In-memory trace store ===
TRACE_STORE: Dict[str, dict] = {}

# === Request schema ===
class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=256)

# === Mock candidates ===
def _mock_candidates(now: datetime) -> List[NormalizedCandidate]:
    return [
        NormalizedCandidate(
            source="drive",
            doc_id="drive-abc123",
            url="https://drive.google.com/file/d/abc123/view",
            title="Payments Deploy Runbook (Drive)",
            snippet="Deploys run at 3pm UTC via Pipeline X AKIA1234567890123456 should be hidden.",
            last_modified=now - timedelta(days=1),
            owner="Runbook Team",
            signals={"folder": "Runbooks", "owner_team": "Runbook"},
        ),
        NormalizedCandidate(
            source="github",
            doc_id="gh-docs-deploy",
            url="https://github.com/org/repo/blob/main/docs/deploy.md#schedule",
            title="deploy.md (GitHub Docs)",
            snippet="Deployment window: 4pm UTC for non-peak; rollback notes included.",
            last_modified=now - timedelta(days=2),
            owner="SRE",
            signals={"path_hint": "/docs", "approved_pr": 30},
        ),
        NormalizedCandidate(
            source="slack",
            doc_id="slack-thread-17123456.789",
            url="https://slack.com/app_redirect?channel=C123&t=17123456.789",
            title="Slack thread: #infra-help",
            snippet="✅ Accepted answer: follow the runbook; main window is 3pm UTC.",
            last_modified=now - timedelta(days=10),
            owner="alice@company.com",
            signals={"pinned": True, "accepted": True, "sme_author": True},
        ),
    ]

# === POST /ask ===
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

    # 2) Trace id from middleware
    trace_id = get_trace_id()

    # (optional) start time for latency
    t0 = time.perf_counter()

    # 3) Candidates (Phase 4 will call ConnectorHub)
    now = datetime.now(timezone.utc)
    candidates: List[NormalizedCandidate] = _mock_candidates(now)

    # 4) Fusion
    chosen, scores_by_id, reasons_by_id = fusion_rank(candidates, query)

    # 5) Sort by score for citations
    sorted_by_score = sorted(candidates, key=lambda c: scores_by_id[c.doc_id], reverse=True)

    # 6) Citations (top 2–3 unique urls)
    citations: List[Citation] = []
    seen_urls = set()
    for c in sorted_by_score:
        if c.url in seen_urls:
            continue
        citations.append(Citation(label=c.source.capitalize(), url=c.url))
        seen_urls.add(c.url)
        if len(citations) >= 3:
            break

    # 7) Policy
    chosen_after_policy, redactions, conflict, banner = policy_guard(
        chosen, sorted_by_score, scores_by_id
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if len(citations) < 1:
        # Save trace (no-citation path)
        TRACE_STORE[trace_id] = {
            "trace_id": trace_id,
            "query": query,
            "timings_ms": {"slack": 0, "drive": 0, "github": 0, "fusion": 1, "policy": 1},
            "candidates": [
                {
                    "source": c.source,
                    "url": str(c.url),
                    "score": float(scores_by_id[c.doc_id]),
                    "reasons": reasons_by_id[c.doc_id],
                }
                for c in sorted_by_score
            ],
            "chosen": {"url": "", "score": 0.0, "explanations": ["no_citation_gate"]},
            "policy": {"redactions": redactions, "conflict": conflict},
        }
        # Log query in DB (Phase 3)
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

        # Build response
        resp = AskResponse(
            trace_id=trace_id,
            answer="No authoritative answer found.",
            citations=[],
            freshness=now,
            confidence=0.0,
            policy_banner="Insufficient citations to justify an answer.",
        )
        log_kv(LOG, logging.INFO, "ask.complete", route="/ask", no_citation=1)
        return resp

    # 8) Confidence
    chosen_score = float(scores_by_id[chosen_after_policy.doc_id])
    confidence = max(0.0, min(1.0, chosen_score))

    # 9) Freshness
    freshness = chosen_after_policy.last_modified

    # 10) Answer text
    answer_text = chosen_after_policy.snippet.split(".")[0].strip() + "."

    resp = AskResponse(
        trace_id=trace_id,
        answer=answer_text,
        citations=citations,
        freshness=freshness,
        confidence=confidence,
        policy_banner=(banner or None),
    )

    # 11) Save trace
    TRACE_STORE[trace_id] = {
        "trace_id": trace_id,
        "query": query,
        "timings_ms": {"slack": 0, "drive": 0, "github": 0, "fusion": 2, "policy": 1},
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

    # 12) DB log
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

    # 13) Log
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

# === GET /trace/{trace_id} ===
@app.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    trace = TRACE_STORE.get(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace
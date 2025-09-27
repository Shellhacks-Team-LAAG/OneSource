from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------- Shared / Connector output ----------

Source = Literal["slack", "drive", "github"]


class NormalizedCandidate(BaseModel):
    """
    Unified shape emitted by each provider adapter (Slack/Drive/GitHub).
    Fusion/Policy operate on this structure only.
    """
    source: Source
    doc_id: str
    url: HttpUrl
    title: str
    snippet: str
    last_modified: datetime
    owner: str
    signals: Dict[str, object] = Field(
        default_factory=dict,
        description="Source-specific signals (e.g., pinned, approved_pr, path_hint).",
    )
    score_hint: float = Field(
        0.0, description="Optional adapter-provided hint; Fusion recomputes final score."
    )


# ---------- /ask response ----------

class Citation(BaseModel):
    label: str
    url: HttpUrl


class AskResponse(BaseModel):
    """
    What the frontend expects back from POST /ask.
    """
    trace_id: str
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    freshness: datetime
    confidence: float = Field(..., ge=0.0, le=1.0)
    policy_banner: Optional[str] = None


# ---------- /trace response (debug/visibility) ----------

class CandidateTraceEntry(BaseModel):
    source: Source
    url: HttpUrl
    score: float
    reasons: List[str] = Field(default_factory=list)


class ChosenEntry(BaseModel):
    url: HttpUrl
    score: float
    explanations: List[str] = Field(default_factory=list)


class PolicyTrace(BaseModel):
    redactions: List[str] = Field(default_factory=list)
    conflict: bool = False


class Trace(BaseModel):
    """
    What the frontend expects back from GET /trace/{trace_id}.
    Provides a timeline + scoring rationale for judges/users.
    """
    trace_id: str
    query: str
    timings_ms: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-component timings (e.g., slack, drive, github, fusion, policy).",
    )
    candidates: List[CandidateTraceEntry] = Field(default_factory=list)
    chosen: ChosenEntry
    policy: PolicyTrace
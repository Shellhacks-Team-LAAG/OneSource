from typing import List, Tuple, Dict
from datetime import datetime, timezone
from app.schemas import NormalizedCandidate
import math

def _freshness_score(dt: datetime) -> float:
    # newer → closer to 1.0
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds()/86400.0)
    # simple sigmoid-ish
    return 1.0 / (1.0 + (age_days / 7.0))

def _authority_score(c: NormalizedCandidate) -> float:
    s = c.signals or {}
    if c.source == "github":
        base = 0.25 if "/docs" in str(s.get("path_hint", "")) or "wiki" in str(s.get("path_hint", "")) else 0.0
        # Diminishing returns for approvals: up to +0.5
        apr = max(0, int(s.get("approved_pr", 0)))
        pr_bonus = min(0.5, 0.2 * math.log10(1 + apr))  # 0 → 0.0, 3 → ~0.12, 10 → ~0.2, 100 → ~0.4
        return base + pr_bonus
    if c.source == "drive":
        return (0.25 if s.get("owner_team") else 0.0) + (0.15 if s.get("folder") == "Runbooks" else 0.0)
    if c.source == "slack":
        return (0.25 if s.get("pinned") else 0.0) + (0.2 if s.get("accepted") else 0.0) + (0.1 if s.get("sme_author") else 0.0)
    return 0.0

def _specificity_score(c: NormalizedCandidate, query: str) -> float:
    q = query.lower()
    title_hit = 1.0 if q in c.title.lower() else 0.0
    body_hit = 1.0 if q in c.snippet.lower() else 0.0
    return 0.15*title_hit + 0.05*body_hit


def score_candidate(c: NormalizedCandidate, query: str) -> float:
    fresh = _freshness_score(c.last_modified)
    auth = _authority_score(c)
    spec = _specificity_score(c, query)
    # Rebalanced weights: fresh 0.5, auth 0.4, spec 0.2
    return 0.5*fresh + 0.4*auth + 0.2*spec

def rank(candidates: List[NormalizedCandidate], query: str) -> Tuple[NormalizedCandidate, Dict[str, float], Dict[str, List[str]]]:
    # returns: (chosen, scores_by_doc_id, reasons_by_doc_id)
    scores, reasons = {}, {}
    for c in candidates:
        s = score_candidate(c, query)
        scores[c.doc_id] = s
        reasons[c.doc_id] = []
        # minimal reasons for trace
        reasons[c.doc_id].append(f"fresh={_freshness_score(c.last_modified):.2f}")
        reasons[c.doc_id].append(f"auth={_authority_score(c):.2f}")
        reasons[c.doc_id].append(f"spec={_specificity_score(c, query):.2f}")
    # consensus bump (if same URL among sources)
    by_url = {}
    for c in candidates:
        by_url.setdefault(c.url, []).append(c.doc_id)
    for url, ids in by_url.items():
        if len(ids) >= 2:
            for did in ids:
                scores[did] += 0.05
                reasons[did].append("consensus=+0.05")
    chosen = max(candidates, key=lambda c: scores[c.doc_id])
    return chosen, scores, reasons
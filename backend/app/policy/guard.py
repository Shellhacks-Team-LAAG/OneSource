import re
from typing import List, Tuple, Dict
from app.schemas import NormalizedCandidate

# Token redaction patterns (same as before)
_TOKEN_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[pbar]-[0-9A-Za-z-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\._-]+"),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
]

# Simple time token (e.g., "3pm", "4 pm") for contradiction check
_TIME_RE = re.compile(r"\b(1[0-2]|[1-9])\s?pm\b", re.IGNORECASE)

def _extract_time_token(text: str) -> str:
    m = _TIME_RE.search(text or "")
    return m.group(0).lower() if m else ""

def redact(text: str) -> str:
    redacted = text or ""
    for pat in _TOKEN_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted

def guard(
    chosen: NormalizedCandidate,
    ranked_by_score: List[NormalizedCandidate],
    scores_by_id: Dict[str, float] | None = None,
) -> Tuple[NormalizedCandidate, List[str], bool, str]:
    """
    Returns: (sanitized_chosen, redactions[], conflict, policy_banner_or_empty)

    - Redacts all candidates' snippets in-place
    - Detects contradiction between the chosen and the best-scoring contradictor
    - Builds a banner that always references the actually chosen source
    """
    # 1) Redact all snippets used in trace
    redactions: List[str] = []
    for c in ranked_by_score:
        before = c.snippet
        after = redact(before)
        if after != before:
            redactions.append(c.doc_id)
            c.snippet = after

    # 2) Find contradiction partner FOR THE CHOSEN doc
    chosen_time = _extract_time_token(chosen.snippet)
    conflict = False
    banner = ""

    contradictor = None
    if chosen_time:
        # pick the highest-scoring *other* candidate that has a different time token
        for c in ranked_by_score:
            if c.doc_id == chosen.doc_id:
                continue
            t = _extract_time_token(c.snippet)
            if t and t != chosen_time:
                contradictor = c
                break  # ranked_by_score is sorted DESC by score
    else:
        # if chosen has no time token, still check others that disagree with each other
        times = [(c, _extract_time_token(c.snippet)) for c in ranked_by_score]
        times = [(c, t) for c, t in times if t]
        seen = {}
        for c, t in times:
            if t not in seen:
                seen[t] = c
            else:
                # at least two time tokens, but chosen might lack one; pick the first non-chosen as contradictor
                contradictor = c if c.doc_id != chosen.doc_id else seen[t]
                break

    if contradictor:
        conflict = True
        banner = f"Sources conflict ({chosen.source} vs {contradictor.source}). Chose {chosen.source} (higher score)."

    return chosen, redactions, conflict, banner
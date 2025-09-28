from typing import Dict
from datetime import datetime


def normalize_github_result(item: Dict) -> Dict:
    """
    Normalize a GitHub search result into the required NormalizedCandidate schema.
    Required fields:
      - source
      - doc_id
      - url
      - title
      - snippet
      - last_modified
      - owner
      - signals
    Signals for GitHub:
      {"path_hint": "/docs", "approved_pr": N, "codeowners_match": bool}
    """

    repo_full_name = item.get("repository", {}).get("full_name", "")
    path = item.get("path", "")
    html_url = item.get("html_url", "")

    # Last modified date fallback
    last_modified = None
    if "repository" in item and "pushed_at" in item["repository"]:
        last_modified = item["repository"]["pushed_at"]

    # Build signals
    signals = {
        "path_hint": "/docs" if "/docs" in path else None,
        "approved_pr": item.get("score", 0),  # Placeholder for PR approvals
        "codeowners_match": path.lower().endswith("readme.md")
    }

    return {
        "source": "github",
        "doc_id": f"{repo_full_name}/{path}",
        "url": html_url,
        "title": path.split("/")[-1] if path else "README",
        "snippet": item.get("name", ""),
        "last_modified": last_modified,
        "owner": repo_full_name.split("/")[0] if "/" in repo_full_name else "",
        "signals": signals
    }

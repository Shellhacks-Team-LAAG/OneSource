from typing import Dict


def normalize_github_result(item: Dict) -> Dict:
    """
    Normalize GitHub search results into a common format.
    """
    return {
        "source": "github",
        "doc_id": item.get("repository", {}).get("full_name", "") + "/" + item.get("path", ""),
        "url": item.get("html_url"),
        "title": item.get("name"),
        "snippet": item.get("repository", {}).get("description", "No snippet available"),
        "last_modified": item.get("git_url"),  # store git_url so fetch_doc can use it
        "owner": item.get("repository", {}).get("full_name", ""),
        "signals": {"pull_request_approval": 0}
    }

import base64
import os
import httpx
from typing import List, Dict
from app.connectorhub.github_cache import get_from_cache, set_to_cache
from app.connectorhub.github_normalize import normalize_github_result

GITHUB_API_URL = "https://api.github.com"


class GitHubConnector:
    def __init__(self, access_token: str):
        self.access_token = access_token or os.getenv("GITHUB_ACCESS_TOKEN")
        self.headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

    async def search_corpus(self, query: str) -> List[Dict]:
        cached = get_from_cache(query)
        if cached:
            return cached

        async with httpx.AsyncClient() as client:
            url = f"{GITHUB_API_URL}/search/code"
            params = {"q": query + " in:file path:/docs filename:README.md"}
            resp = await client.get(url, headers=self.headers, params=params)

            if resp.status_code != 200:
                print(f"[ERROR] GitHub search failed: {resp.status_code}")
                return []

            results = resp.json().get("items", [])
            normalized_results = [normalize_github_result(item) for item in results]

            set_to_cache(query, normalized_results)
            return normalized_results

    async def fetch_doc(self, git_url: str) -> Dict:
        """
        Fetch the full content of a specific file using git_url.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(git_url, headers=self.headers)

            if resp.status_code != 200:
                print(f"[ERROR] GitHub fetch_doc failed: {resp.status_code}")
                return {}

            data = resp.json()

            content = ""
            if "content" in data and data.get("encoding") == "base64":
                try:
                    content = base64.b64decode(data["content"]).decode("utf-8")
                except Exception as e:
                    print(f"[ERROR] Decoding failed: {e}")

            return {
                "content": content,
                "path": data.get("path"),
                "last_modified": data.get("git_url")
            }

    async def check_access(self, repo_full_name: str) -> bool:
        async with httpx.AsyncClient() as client:
            url = f"{GITHUB_API_URL}/repos/{repo_full_name}"
            resp = await client.get(url, headers=self.headers)
            if resp.status_code == 200:
                return True
            print(f"[ERROR] Access denied for repo {repo_full_name}")
            return False

# backend/app/main.py

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# connector
from app.connectorhub.github_connector import GitHubConnector
from app.connectorhub.github_oauth import router as oauth_router

load_dotenv()

app = FastAPI()

# Session configuration (must be set in .env)
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", "dev-session-secret-change-me")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "3600"))  # seconds

# Add session middleware BEFORE including routers that rely on request.session
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=SESSION_MAX_AGE,
    path="/",
    same_site="lax",
    https_only=False,  # set to True in production with HTTPS
)

# Include the OAuth router (it expects session middleware to be available at runtime)
app.include_router(oauth_router)


@app.get("/")
def root():
    return {"status": "running"}


def _get_token_from_request_or_env(request: Request):
    """
    Prefer token in user's session; fall back to environment token if present (for dev).
    """
    token = None
    if hasattr(request, "session"):
        token = request.session.get("github_token")
    if not token:
        token = os.getenv("GITHUB_ACCESS_TOKEN")
    return token


@app.get("/connections/github/search")
async def github_search(request: Request, q: str = Query(..., description="Search query")):
    token = _get_token_from_request_or_env(request)
    if not token:
        raise HTTPException(status_code=401, detail="Access token not available. Please authorize GitHub first.")
    connector = GitHubConnector(token)
    results = await connector.search_corpus(q)
    if not results:
        raise HTTPException(status_code=404, detail="No results found")
    return {"query": q, "results": results}


@app.get("/connections/github/fetch")
async def github_fetch(request: Request, doc_id: str = Query(..., description="doc_id from search results")):
    token = _get_token_from_request_or_env(request)
    if not token:
        raise HTTPException(status_code=401, detail="Access token not available. Please authorize GitHub first.")
    connector = GitHubConnector(token)
    doc = await connector.fetch_doc(doc_id)
    if not doc or not doc.get("content"):
        raise HTTPException(status_code=404, detail="Document not found or content empty")
    return {"doc_id": doc_id, "content": doc["content"], "path": doc.get("path")}


@app.get("/connections/github/check_access")
async def github_check_access(request: Request, repo_full_name: str = Query(..., description="owner/repo")):
    token = _get_token_from_request_or_env(request)
    if not token:
        raise HTTPException(status_code=401, detail="Access token not available. Please authorize GitHub first.")
    connector = GitHubConnector(token)
    ok = await connector.check_access(repo_full_name)
    return {"repo_full_name": repo_full_name, "access": ok}


@app.get("/connections/github/logout")
async def github_logout(request: Request):
    # clear session token
    if hasattr(request, "session"):
        request.session.pop("github_token", None)
        request.session.pop("github_token_type", None)
        request.session.pop("github_scope", None)
        request.session.pop("oauth_state", None)
    return {"status": "logged_out"}

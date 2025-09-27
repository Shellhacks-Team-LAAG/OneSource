# backend/app/connectorhub/github_oauth.py

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv
import os
import httpx
import secrets
from typing import Optional

load_dotenv()
router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_CALLBACK_URL = os.getenv("GITHUB_CALLBACK_URL")
FRONTEND_AFTER_AUTH = os.getenv("FRONTEND_AFTER_AUTH", "/")  # where to send the user after callback


def _missing_config_error():
    return JSONResponse(
        {"error": "GitHub OAuth not configured. Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_CALLBACK_URL in .env"},
        status_code=500,
    )


@router.get("/connections/github/authorize")
async def github_authorize(request: Request, force: bool = False):
    """
    Redirect the browser to GitHub's OAuth authorization page.
    Generates and stores a `state` token in the session for CSRF protection.
    """
    if not (GITHUB_CLIENT_ID and GITHUB_CALLBACK_URL):
        return _missing_config_error()

    # create CSRF state and store it in session
    state = secrets.token_urlsafe(16)
    if hasattr(request, "session"):
        request.session["oauth_state"] = state

    scope = "read:repo repo"
    prompt = "consent" if force else ""
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_CALLBACK_URL}"
        f"&scope={scope}"
        f"&state={state}"
    )
    if prompt:
        url += f"&prompt={prompt}"

    return RedirectResponse(url)


@router.get("/connections/github/callback")
async def github_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    """
    Exchange code for access token, verify state, store token in session.
    """
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET and GITHUB_CALLBACK_URL):
        return _missing_config_error()

    if code is None:
        return JSONResponse({"error": "Missing `code` in callback"}, status_code=400)

    # validate state
    saved_state = None
    if hasattr(request, "session"):
        saved_state = request.session.get("oauth_state")
    if (saved_state is not None) and (state != saved_state):
        return JSONResponse({"error": "Invalid state parameter"}, status_code=400)

    token_url = "https://github.com/login/oauth/access_token"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GITHUB_CALLBACK_URL,
                },
            )
        except Exception as e:
            return JSONResponse({"error": "Token exchange request failed", "details": str(e)}, status_code=502)

    if resp.status_code != 200:
        return JSONResponse(
            {"error": "Token exchange failed", "status": resp.status_code, "body": resp.text},
            status_code=502,
        )

    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return JSONResponse({"error": "No access_token returned", "details": token_data}, status_code=502)

    # Store token in session
    if hasattr(request, "session"):
        request.session["github_token"] = access_token
        request.session["github_token_type"] = token_data.get("token_type")
        request.session["github_scope"] = token_data.get("scope")
        # clear oauth_state once used
        request.session.pop("oauth_state", None)

    return RedirectResponse(FRONTEND_AFTER_AUTH)


@router.get("/connections/github/me")
async def github_me(request: Request):
    token = None
    if hasattr(request, "session"):
        token = request.session.get("github_token")
    if not token:
        return JSONResponse({"error": "Not authenticated with GitHub"}, status_code=401)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"token {token}"},
        )

    if resp.status_code != 200:
        return JSONResponse({"error": "Failed to fetch user", "status": resp.status_code, "body": resp.text}, status_code=resp.status_code)

    return resp.json()


@router.get("/connections/github/logout")
async def github_logout(request: Request):
    if hasattr(request, "session"):
        request.session.pop("github_token", None)
        request.session.pop("github_token_type", None)
        request.session.pop("github_scope", None)
        request.session.pop("oauth_state", None)
    return {"status": "logged_out"}

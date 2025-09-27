from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import os
import httpx

# Load .env variables
load_dotenv()

router = APIRouter()

@router.get("/connections/github/authorize")
async def github_authorize():
    client_id = os.getenv("GITHUB_CLIENT_ID")
    redirect_uri = os.getenv("GITHUB_CALLBACK_URL")

    # Debugging: print the callback URL
    print(f"[DEBUG] GITHUB_CALLBACK_URL = {redirect_uri}")

    if not redirect_uri or not client_id:
        return {"error": "Missing GITHUB_CALLBACK_URL or GITHUB_CLIENT_ID in .env"}

    scope = "read:repo repo"
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={scope}"
        f"&redirect_uri={redirect_uri}"
        f"&prompt=consent"
    )

    # Debugging: print the full GitHub URL
    print(f"[DEBUG] Redirecting to GitHub OAuth URL: {github_url}")

    return RedirectResponse(github_url)


@router.get("/connections/github/callback")
async def github_callback(code: str):
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code
            }
        )
        data = resp.json()
        access_token = data.get("access_token")

    return {"access_token": access_token}

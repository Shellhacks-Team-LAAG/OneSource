from fastapi import FastAPI
from app.connectorhub.github_oauth import router as github_router

app = FastAPI()

app.include_router(github_router)

@app.get("/")
async def root():
    return {"status": "Backend is running"}

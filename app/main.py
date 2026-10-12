"""FastAPI entrypoint. Routes are added per docs/05-architecture.md; static demo page is served from web/."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Intent Judge")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Mounted last so /api/* routes win.
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "web", html=True), name="web")

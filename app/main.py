"""OpenReach — a self-hosted HubSpot-style CRM and marketing hub."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import api, pages
from .seed import seed

app = FastAPI(
    title="OpenReach",
    description="Self-hosted HubSpot-style CRM + marketing hub. Contacts, companies, "
    "deals pipeline, email campaigns & sequences, web forms, landing pages, automation.",
    version="1.0.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(pages.router)
app.include_router(api.router)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    seed()

"""Praxia Marketing — FastAPI entrypoint. Serves the single-page UI + API."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import autopilot, scheduler
from .db import init_db
from .growth_routes import router as growth_router
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Praxia Marketing")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)
app.include_router(growth_router)

STATIC = Path(__file__).resolve().parent / "static"
(STATIC / "assets" / "posts").mkdir(parents=True, exist_ok=True)
# generated post graphics (and any other assets) served here
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    autopilot.cleanup_orphans()
    scheduler.start()


@app.get("/")
async def root():
    return FileResponse(STATIC / "index.html")

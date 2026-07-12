"""Praxia Marketing — FastAPI entrypoint. Serves the single-page UI + API."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .db import init_db
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Praxia Marketing")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)

STATIC = Path(__file__).resolve().parent / "static"


@app.on_event("startup")
async def _startup() -> None:
    init_db()


@app.get("/")
async def root():
    return FileResponse(STATIC / "index.html")

"""Open Foundry — Palantir-style platform backend for UMN Bar Traffic Prediction.

Run:   uvicorn platform.backend.main:app --reload --port 8001
Docs:  http://localhost:8001/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform.backend.api import pipeline, predict, signals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise DB. Shutdown: nothing to do."""
    from data.db import init_db

    log.info("Initialising database ...")
    init_db()
    log.info("Platform backend ready.")
    yield
    log.info("Platform backend shutting down.")


app = FastAPI(
    title="UMN Bar Traffic — Open Foundry Platform",
    description=(
        "Palantir Foundry-style pipeline backend. "
        "Wraps real data providers (weather, sports, events) and ML models "
        "via a DAG execution engine. "
        "See /docs for interactive API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8501"],  # Next.js + Streamlit
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict.router,  prefix="/api/v1")
app.include_router(signals.router,  prefix="/api/v1")
app.include_router(pipeline.router, prefix="/api/v1")


@app.get("/health")
def health():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "umn-bar-traffic-platform"}

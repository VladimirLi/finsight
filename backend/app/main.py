"""FastAPI application entry point."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup/shutdown lifecycle: ensure the upload dir + DB schema exist."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="finsight", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Return service health and the active LLM provider."""
    return {"status": "ok", "llm_provider": settings.llm_provider}


# Register API routers.
from app.api import companies, documents, ratios, upload  # noqa: E402

app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(ratios.router, prefix="/api", tags=["ratios"])

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import db
from .routers import etfs, industries


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="ETF Data API", lifespan=lifespan)

if settings.api_cors_origins:
    allow_all_origins = any(origin == "*" for origin in settings.api_cors_origins)
    allow_origins = ["*"] if allow_all_origins else list(settings.api_cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(etfs.router, prefix="/api")
app.include_router(industries.router, prefix="/api")


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

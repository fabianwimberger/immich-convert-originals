"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Immich Library Converter...")
    settings.ensure_directories()

    from app.database import init_db
    from app.services.lifecycle import seed_settings

    await init_db()
    await seed_settings()

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Immich Library Converter",
    description="Web UI for batch-transcoding an Immich library to JPEG XL and AV1",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes import settings as settings_routes  # noqa: E402

app.include_router(settings_routes.router, prefix="/api/settings", tags=["settings"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}


# Mount static frontend last so it doesn't shadow /api routes.
app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")

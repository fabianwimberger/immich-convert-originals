"""Shared fixtures for backend route/service tests.

FRONTEND_DIR/DATABASE_PATH/TEMP_DIR must be set before app.main is first
imported (StaticFiles validates its directory at construction time, and
app.database creates its engine at module-import time), so this happens at
collection time, before any test module runs.
"""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_DATA_DIR = Path(__file__).resolve().parent / ".test-data"
_TEST_DATA_DIR.mkdir(exist_ok=True)

os.environ.setdefault("FRONTEND_DIR", str(_REPO_ROOT / "frontend"))
os.environ.setdefault("DATABASE_PATH", str(_TEST_DATA_DIR / "test.db"))
os.environ.setdefault("TEMP_DIR", str(_TEST_DATA_DIR / "temp"))

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

import app.main  # noqa: E402
from app.database import AsyncSessionLocal, init_db  # noqa: E402
from app.models.asset_outcome import AssetOutcome  # noqa: E402
from app.models.run import Run  # noqa: E402
from app.models.settings import Settings  # noqa: E402
from app.services import run_service  # noqa: E402
from app.services.lifecycle import seed_settings  # noqa: E402


@pytest_asyncio.fixture
async def client():
    """An httpx AsyncClient wired to the FastAPI app with a clean db.

    Run ids restart from 1 each test (sqlite reuses ids after DELETE
    without AUTOINCREMENT), so in-memory run_service state keyed by id
    must be reset too, or a stale cancelled-id from a prior test can
    collide with a fresh run here.
    """
    await init_db()

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Settings))
        await db.execute(delete(AssetOutcome))
        await db.execute(delete(Run))
        await db.commit()
    await seed_settings()
    run_service._cancelled_runs.clear()

    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

"""Startup tasks: run once when the app boots."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.run import Run
from app.models.settings import SETTINGS_ROW_ID, Settings

logger = logging.getLogger(__name__)


async def seed_settings() -> None:
    """Create the Settings row with its model defaults if it doesn't exist yet.

    Only runs once, ever, per database: after the row exists, the Settings
    page in the UI is authoritative.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Settings).where(Settings.id == SETTINGS_ROW_ID)
        )
        if result.scalar_one_or_none() is not None:
            return

        db.add(Settings(id=SETTINGS_ROW_ID))
        await db.commit()
        logger.info("Seeded settings with defaults")


async def reconcile_interrupted_runs() -> None:
    """Fail any run left "queued"/"running" by a previous process.

    Nothing re-enqueues a pending run into run_queue on boot, and nothing
    else ever moves a run out of "running" once its process is gone -- a
    kill/crash/OOM mid-run otherwise leaves it stuck in that state forever,
    permanently blocking retry-failed for it.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Run).where(Run.status.in_(("queued", "running")))
        )
        stale_runs = result.scalars().all()
        if not stale_runs:
            return

        now = datetime.now(timezone.utc)
        for run in stale_runs:
            run.status = "failed"
            run.completed_at = now
            run.error_message = "Interrupted by application restart"
        await db.commit()
        logger.warning(
            "Marked %d interrupted run(s) as failed on startup: %s",
            len(stale_runs),
            [r.id for r in stale_runs],
        )

"""Startup tasks: run once when the app boots."""

import logging

from sqlalchemy import select

from app.config import seed_settings_from_env
from app.database import AsyncSessionLocal
from app.models.settings import SETTINGS_ROW_ID, Settings

logger = logging.getLogger(__name__)


async def seed_settings() -> None:
    """Create the Settings row from env vars if it doesn't exist yet.

    Only runs once, ever, per database: after the row exists, env vars are
    no longer consulted and the Settings page in the UI is authoritative.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Settings).where(Settings.id == SETTINGS_ROW_ID)
        )
        if result.scalar_one_or_none() is not None:
            return

        seed = seed_settings_from_env()
        row = Settings(id=SETTINGS_ROW_ID, **seed)
        db.add(row)
        await db.commit()
        logger.info("Seeded settings from environment variables")

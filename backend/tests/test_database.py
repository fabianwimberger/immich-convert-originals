"""Tests for the settings-table upgrade path (no Alembic, see database.py)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import _sync_settings_columns


@pytest.mark.asyncio
class TestSyncSettingsColumns:
    async def test_adds_missing_column_with_model_default(self):
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.begin() as conn:
                # Simulate a pre-upgrade settings table: everything except
                # one column the current model has ("concurrency"), with an
                # existing row already in it.
                await conn.execute(
                    text(
                        "CREATE TABLE settings ("
                        "id INTEGER PRIMARY KEY, "
                        "immich_api_base TEXT DEFAULT ''"
                        ")"
                    )
                )
                await conn.execute(
                    text("INSERT INTO settings (id, immich_api_base) VALUES (1, '')")
                )

                await _sync_settings_columns(conn)

                result = await conn.execute(text("PRAGMA table_info(settings)"))
                columns = {row[1] for row in result.fetchall()}
                assert "concurrency" in columns
                assert "image_distance" in columns

                row = await conn.execute(
                    text("SELECT concurrency, image_distance FROM settings WHERE id=1")
                )
                concurrency, image_distance = row.fetchone()
                assert concurrency == 2
                assert image_distance == 1.0
        finally:
            await engine.dispose()

    async def test_noop_when_table_already_current(self):
        from app.models.settings import Settings

        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Settings.metadata.create_all)
                # Should not raise or duplicate columns when nothing is missing.
                await _sync_settings_columns(conn)
                result = await conn.execute(text("PRAGMA table_info(settings)"))
                names = [row[1] for row in result.fetchall()]
                assert len(names) == len(set(names))
        finally:
            await engine.dispose()

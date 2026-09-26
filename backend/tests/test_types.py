"""Tests for the TZDateTime column type (see app/models/types.py)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Integer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from app.models.types import TZDateTime

_Base = declarative_base()


class _Stamped(_Base):
    """A throwaway model, isolated from the app's real tables."""

    __tablename__ = "_tzdatetime_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime | None] = mapped_column(TZDateTime, default=None)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            yield s
    finally:
        await engine.dispose()


class TestTZDateTime:
    async def test_utc_datetime_round_trips_as_aware_utc(self, session):
        original = datetime(2026, 9, 23, 22, 0, 1, tzinfo=timezone.utc)
        row = _Stamped(at=original)
        session.add(row)
        await session.commit()
        await session.refresh(row)

        assert row.at == original
        assert row.at.tzinfo is timezone.utc

    async def test_non_utc_aware_datetime_is_normalized_to_utc(self, session):
        cest = timezone(timedelta(hours=2))
        # 2026-09-24 00:00 CEST == 2026-09-23 22:00 UTC, the local-midnight
        # case that surfaced the original bug.
        local_midnight = datetime(2026, 9, 24, 0, 0, 0, tzinfo=cest)
        row = _Stamped(at=local_midnight)
        session.add(row)
        await session.commit()
        await session.refresh(row)

        assert row.at == datetime(2026, 9, 23, 22, 0, 0, tzinfo=timezone.utc)
        assert row.at.tzinfo is timezone.utc

    async def test_naive_datetime_is_rejected_before_it_reaches_the_db(self, session):
        row = _Stamped(at=datetime(2026, 9, 24, 0, 0, 0))  # no tzinfo
        session.add(row)
        with pytest.raises(Exception, match="is naive"):
            await session.commit()

    async def test_none_round_trips_as_none(self, session):
        row = _Stamped(at=None)
        session.add(row)
        await session.commit()
        await session.refresh(row)

        assert row.at is None

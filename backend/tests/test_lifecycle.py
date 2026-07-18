"""Tests for startup reconciliation of interrupted runs."""

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, init_db
from app.models.run import Run
from app.services.lifecycle import reconcile_interrupted_runs


async def _make_run(db, status: str) -> int:
    run = Run(status=status)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run.id


@pytest.mark.asyncio
class TestReconcileInterruptedRuns:
    async def test_marks_queued_and_running_as_failed(self):
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Run))
            await db.commit()
            queued_id = await _make_run(db, "queued")
            running_id = await _make_run(db, "running")
            completed_id = await _make_run(db, "completed")

        await reconcile_interrupted_runs()

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run))
            runs = {r.id: r for r in result.scalars().all()}

        assert runs[queued_id].status == "failed"
        assert runs[queued_id].error_message == "Interrupted by application restart"
        assert runs[queued_id].completed_at is not None
        assert runs[running_id].status == "failed"
        assert runs[completed_id].status == "completed"
        assert runs[completed_id].error_message is None

    async def test_noop_when_nothing_stale(self):
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Run))
            await db.commit()
            await _make_run(db, "completed")

        await reconcile_interrupted_runs()

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run))
            runs = result.scalars().all()

        assert len(runs) == 1
        assert runs[0].status == "completed"

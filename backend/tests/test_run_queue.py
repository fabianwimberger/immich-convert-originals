"""Tests for the sequential run queue."""

import asyncio

import pytest

from app.services.run_queue import RunQueue


@pytest.mark.asyncio
class TestRunQueue:
    async def test_processes_runs_in_order(self, monkeypatch):
        processed: list[int] = []

        async def fake_execute(run_id: int) -> None:
            processed.append(run_id)

        monkeypatch.setattr("app.services.run_queue.execute_run", fake_execute)

        queue = RunQueue()
        await queue.start()
        try:
            await queue.add_run(1)
            await queue.add_run(2)
            await queue.add_run(3)
            await asyncio.wait_for(queue._queue.join(), timeout=2)
        finally:
            await queue.stop()

        assert processed == [1, 2, 3]

    async def test_error_in_one_run_does_not_stop_the_worker(self, monkeypatch):
        processed: list[int] = []

        async def fake_execute(run_id: int) -> None:
            if run_id == 1:
                raise RuntimeError("boom")
            processed.append(run_id)

        monkeypatch.setattr("app.services.run_queue.execute_run", fake_execute)

        queue = RunQueue()
        await queue.start()
        try:
            await queue.add_run(1)
            await queue.add_run(2)
            await asyncio.wait_for(queue._queue.join(), timeout=2)
        finally:
            await queue.stop()

        assert processed == [2]

    async def test_stop_is_safe_when_never_started(self):
        queue = RunQueue()
        await queue.stop()  # should not raise

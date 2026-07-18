"""Sequential run queue: one Run executes at a time, others wait their turn."""

import asyncio
import logging

from app.services.run_service import execute_run

logger = logging.getLogger(__name__)


class RunQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def add_run(self, run_id: int) -> None:
        await self._queue.put(run_id)

    async def _worker(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await execute_run(run_id)
            except Exception:
                logger.exception("Unhandled error executing run %s", run_id)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        if self._worker_task is None:
            # asyncio.Queue binds lazily to whatever loop first awaits on
            # it. Recreate it here so start()/stop() is safe to call more
            # than once in the same process on a different loop (matters
            # for tests using per-test event loops; a no-op difference in
            # production, where start() runs exactly once).
            self._queue = asyncio.Queue()
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None


run_queue = RunQueue()

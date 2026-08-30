import asyncio
import time
from typing import Callable, Coroutine, Any, List, Optional
from pydantic import BaseModel
from app.config import settings
from app.core.logger import logger


class JobProgress(BaseModel):
    total: int = 0
    checked: int = 0
    live_count: int = 0
    dead_count: int = 0
    percent: float = 0.0
    elapsed_seconds: float = 0.0
    is_running: bool = False
    status_message: str = "Idle"


class AsyncRunner:
    """Manages concurrent async task execution with rate limits and progress tracking."""

    def __init__(self, max_concurrency: int = settings.MAX_CONCURRENT_CHECKS):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.progress = JobProgress()
        self._listeners: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    def subscribe(self) -> asyncio.Queue:
        """Subscribe an SSE listener queue to receive progress updates."""
        q: asyncio.Queue = asyncio.Queue()
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a listener queue."""
        if q in self._listeners:
            self._listeners.remove(q)

    async def _notify(self, data: dict) -> None:
        """Broadcast progress event to all active SSE listeners."""
        for q in list(self._listeners):
            try:
                q.put_nowait(data)
            except Exception:
                pass

    async def run_batch(
        self,
        items: List[Any],
        task_fn: Callable[[Any], Coroutine[Any, Any, Any]],
        on_item_complete: Optional[Callable[[Any, Any], Coroutine[Any, Any, None]]] = None,
    ) -> List[Any]:
        """Execute task_fn for all items concurrently bounded by semaphore."""
        total = len(items)
        if total == 0:
            return []

        start_time = time.time()
        self.progress = JobProgress(
            total=total,
            checked=0,
            live_count=0,
            dead_count=0,
            percent=0.0,
            elapsed_seconds=0.0,
            is_running=True,
            status_message="Checking nodes...",
        )
        await self._notify({"event": "progress", "data": self.progress.model_dump()})

        results: List[Any] = []
        checked_count = 0
        live_count = 0
        dead_count = 0

        async def worker(item: Any) -> Any:
            nonlocal checked_count, live_count, dead_count
            async with self.semaphore:
                try:
                    res = await task_fn(item)
                except Exception as e:
                    logger.error(f"Error checking node {item}: {e}")
                    res = None

                checked_count += 1
                is_alive = bool(getattr(res, "is_alive", False))
                if is_alive:
                    live_count += 1
                else:
                    dead_count += 1

                self.progress.checked = checked_count
                self.progress.live_count = live_count
                self.progress.dead_count = dead_count
                self.progress.percent = round((checked_count / total) * 100, 1)
                self.progress.elapsed_seconds = round(time.time() - start_time, 2)

                # Broadcast progress & individual result
                await self._notify({
                    "event": "node_checked",
                    "data": {
                        "progress": self.progress.model_dump(),
                        "result": res.model_dump() if hasattr(res, "model_dump") else str(res),
                    }
                })

                if on_item_complete and res is not None:
                    try:
                        await on_item_complete(item, res)
                    except Exception as e:
                        logger.error(f"on_item_complete callback error: {e}")

                return res

        tasks = [asyncio.create_task(worker(item)) for item in items]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in raw_results:
            if not isinstance(r, Exception) and r is not None:
                results.append(r)

        self.progress.is_running = False
        self.progress.status_message = "Completed"
        self.progress.elapsed_seconds = round(time.time() - start_time, 2)
        await self._notify({"event": "complete", "data": self.progress.model_dump()})

        logger.info(
            f"Batch check completed: {checked_count}/{total} checked in {self.progress.elapsed_seconds}s. "
            f"Live: {live_count}, Dead: {dead_count}"
        )
        return results


runner = AsyncRunner()

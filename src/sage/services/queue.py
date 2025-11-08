"""In-memory priority queue with rate-limited ingestion processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

from rich.console import Console
from pydantic import HttpUrl

from sage.config.settings import RateLimitConfig, ServiceRateLimit, Settings, get_settings
from sage.models.queue import QueueItem, QueueStatus
from sage.utils.progress import ProcessingStage, ProgressUpdate


ProgressHandler = Callable[[ProgressUpdate], None]
IngestionHandler = Callable[[QueueItem, ProgressHandler], Awaitable[None]]


@dataclass(slots=True)
class RateLimiter:
    """Token bucket with exponential backoff for rate-limited operations."""

    requests_per_minute: int
    burst: int
    backoff_base_seconds: float = 0.5
    max_backoff_seconds: float = 5.0
    _tokens: float = field(init=False, repr=False)
    _last_refill: float = field(init=False, repr=False)
    _refill_rate: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tokens: float = float(self.burst)
        self._last_refill: float = asyncio.get_event_loop().time()
        self._refill_rate: float = self.requests_per_minute / 60.0 if self.requests_per_minute else 0.0

    async def acquire(self) -> None:
        """Wait until a token is available according to the configured rate limit."""

        if self.requests_per_minute <= 0:
            return

        attempt = 0
        while True:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            wait_time = (1.0 - self._tokens) / self._refill_rate if self._refill_rate else self.backoff_base_seconds
            backoff = min(self.max_backoff_seconds, self.backoff_base_seconds * (2**attempt))
            await asyncio.sleep(max(wait_time, backoff))
            attempt += 1

    def _refill(self) -> None:
        """Replenish available tokens based on elapsed time since the last refill."""

        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_refill
        if elapsed <= 0 or self._refill_rate == 0:
            return

        self._tokens = min(self.burst, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now


class QueueService:
    """Coordinates batch ingestion with rate limiting and progress updates."""

    def __init__(
        self,
        *,
        ingestion_handler: IngestionHandler,
        settings: Optional[Settings] = None,
        console: Optional[Console] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._console = console or Console()
        self._ingestion_handler = ingestion_handler
        self._priority_queue: asyncio.PriorityQueue[Tuple[int, int, QueueItem]] = asyncio.PriorityQueue()
        self._items: Dict[str, QueueItem] = {}
        self._sequence = 0
        self._rate_limiters = self.load_rate_limits(self._settings.rate_limits)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    async def add_to_queue(
        self,
        url: str,
        *,
        priority: int = 0,
        manual_tags: Optional[Sequence[str]] = None,
        summarize: bool = True,
        summary_length: int = 300,
        remove_timestamps: bool = False,
        force: bool = False,
    ) -> QueueItem:
        """Enqueue a YouTube URL with ingestion preferences."""

        queued_at = datetime.now(timezone.utc)
        typed_url = cast(HttpUrl, url)
        item = QueueItem(
            video_url=typed_url,
            priority=priority,
            queued_at=queued_at,
            manual_tags=list(manual_tags or []),
            summarize=summarize,
            summary_length=summary_length,
            remove_timestamps=remove_timestamps,
            force=force,
        )

        async with self._lock:
            self._sequence += 1
            await self._priority_queue.put((-priority, self._sequence, item))
            self._items[str(typed_url)] = item

        return item

    async def process_queue(self) -> None:
        """Process queued items sequentially while respecting configured rate limits."""

        while True:
            try:
                priority, sequence, item = await asyncio.wait_for(self._priority_queue.get(), timeout=0.05)
                _ = priority  # unused, kept for tuple structure clarity
                _ = sequence
            except asyncio.TimeoutError:
                if self._priority_queue.empty():
                    break
                continue

            await self._process_item(item)
            self._priority_queue.task_done()

    def get_queue_status(self) -> Dict[str, int]:
        """Return summary statistics describing queue progress."""

        counts = {
            QueueStatus.QUEUED: 0,
            QueueStatus.PROCESSING: 0,
            QueueStatus.COMPLETED: 0,
            QueueStatus.FAILED: 0,
        }
        for item in self._items.values():
            counts[item.status] += 1

        return {
            "queued": counts[QueueStatus.QUEUED],
            "processing": counts[QueueStatus.PROCESSING],
            "completed": counts[QueueStatus.COMPLETED],
            "failed": counts[QueueStatus.FAILED],
            "total": sum(counts.values()),
        }

    # ------------------------------------------------------------------ #
    # Rate limit management                                              #
    # ------------------------------------------------------------------ #
    def load_rate_limits(self, configuration: RateLimitConfig) -> Dict[str, RateLimiter]:
        """Create rate limiter instances from configuration."""

        limiters: Dict[str, RateLimiter] = {}
        for service_name, config in configuration.services.items():
            limiters[service_name] = self._create_limiter(service_name, config)
        return limiters

    async def apply_rate_limit(self, service_name: str) -> None:
        """Enforce rate limits for a given external service."""

        limiter = self._rate_limiters.get(service_name)
        if limiter is None:
            return
        await limiter.acquire()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    async def _process_item(self, item: QueueItem) -> None:
        """Execute ingestion for a single queue item with error handling."""

        in_progress = item.model_copy(
            update={
                "status": QueueStatus.PROCESSING,
                "started_at": datetime.now(timezone.utc),
                "current_stage": ProcessingStage.VALIDATING,
                "stage_progress_percent": 0,
            }
        )
        self._items[str(item.video_url)] = in_progress

        progress_handler = self._progress_callback_for(str(item.video_url))
        services_to_throttle = ["youtube_api"]
        if in_progress.summarize:
            services_to_throttle.append("openai_api")

        try:
            for service in services_to_throttle:
                await self.apply_rate_limit(service)

            await self._ingestion_handler(in_progress, progress_handler)

            completed = in_progress.model_copy(
                update={
                    "status": QueueStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc),
                    "current_stage": ProcessingStage.COMPLETE,
                    "overall_progress_percent": 100,
                    "stage_progress_percent": 100,
                }
            )
            self._items[str(item.video_url)] = completed
        except Exception as exc:  # pragma: no cover - defensive fallback
            failed = in_progress.model_copy(
                update={
                    "status": QueueStatus.FAILED,
                    "completed_at": datetime.now(timezone.utc),
                    "current_stage": ProcessingStage.FAILED,
                    "error_message": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            )
            self._items[str(item.video_url)] = failed
            self._console.log(f"[red]Batch item failed:[/red] {exc}")

    def _progress_callback_for(self, video_url: str) -> ProgressHandler:
        """Return a callback that updates queue state based on service progress events."""

        def handler(update: ProgressUpdate) -> None:
            current = self._items.get(video_url)
            if current is None:
                return
            self._items[video_url] = current.model_copy(
                update={
                    "current_stage": update.stage,
                    "stage_progress_percent": update.stage_progress,
                    "overall_progress_percent": max(current.overall_progress_percent, update.overall_progress),
                    "message": update.message,
                }
            )

        return handler

    def _create_limiter(self, service_name: str, config: ServiceRateLimit) -> RateLimiter:
        """Build a :class:`RateLimiter` instance from a single service configuration."""

        requests_per_minute = config.requests_per_minute or 60
        burst = config.burst or requests_per_minute
        if requests_per_minute <= 0:
            self._console.log(f"[yellow]{service_name}: rate limit disabled or zero requests configured.[/yellow]")
        return RateLimiter(requests_per_minute=requests_per_minute, burst=burst)

    def items(self) -> Iterable[QueueItem]:
        """Expose current queue items (primarily for status commands)."""

        return list(self._items.values())


__all__ = ["QueueService", "RateLimiter"]


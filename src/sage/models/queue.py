"""Pydantic models describing ingestion queue items."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field, HttpUrl

from sage.models.base import SageBaseModel
from sage.utils.progress import ProcessingStage


class QueueStatus(str, Enum):
    """Lifecycle states for a queue item."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueItem(SageBaseModel):
    """In-memory queue item used during batch processing.

    Contains end-user command preferences, current processing state, and retry metadata.
    """

    video_url: HttpUrl
    status: QueueStatus = QueueStatus.QUEUED
    priority: int = 0
    manual_tags: List[str] = Field(default_factory=list)
    summarize: bool = True
    summary_length: int = Field(default=300, ge=1)
    remove_timestamps: bool = False
    force: bool = False
    current_stage: Optional[ProcessingStage] = None
    stage_progress_percent: int = Field(default=0, ge=0, le=100)
    overall_progress_percent: int = Field(default=0, ge=0, le=100)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    message: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


__all__ = ["QueueItem", "QueueStatus"]




"""Progress tracking types shared across CLI and services."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcessingStage(str, Enum):
    """Lifecycle stages for ingesting a YouTube video."""

    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    STORING = "storing"
    COMPLETE = "complete"
    FAILED = "failed"


class ProgressUpdate(BaseModel):
    """Structured progress payload for UI rendering and logging."""

    stage: ProcessingStage
    stage_progress: int = Field(ge=0, le=100)
    overall_progress: int = Field(ge=0, le=100)
    message: str
    video_url: str
    estimated_time_remaining: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


__all__ = ["ProcessingStage", "ProgressUpdate"]


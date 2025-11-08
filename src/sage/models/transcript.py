"""Pydantic models for transcript storage and processing."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from sage.models.base import SageBaseModel


class TranscriptSource(str, Enum):
    """Available transcript sources."""

    YOUTUBE_CAPTIONS = "youtube_captions"
    WHISPER_LOCAL = "whisper_local"
    WHISPER_API = "whisper_api"


class TranscriptSegment(SageBaseModel):
    """Segment of a transcript including precise timing metadata."""

    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    text: str


class Transcript(SageBaseModel):
    """Domain model representing a row in the ``transcripts`` table.

    The model stores both the raw segment list (if available) and a cleaned string representation
    along with metadata about the transcription source and quality metrics.
    """

    id: Optional[UUID] = None
    video_id: Optional[UUID] = None
    raw_transcript_json: Optional[List[TranscriptSegment]] = None
    cleaned_transcript: str
    word_count: int = Field(ge=0)
    transcript_source: TranscriptSource
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    has_timestamps: bool = True
    created_at: Optional[datetime] = None


__all__ = ["Transcript", "TranscriptSegment", "TranscriptSource"]


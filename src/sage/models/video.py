"""Pydantic models describing YouTube video metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, HttpUrl

from sage.models.base import SageBaseModel


class YouTubeVideo(SageBaseModel):
    """Domain model representing a row in the ``youtube_videos`` table.

    Fields capture metadata extracted from YouTube as well as ingestion timestamps. Instances
    are created from API responses and persisted via :class:`sage.db.video_repository.VideoRepository`.
    """

    id: Optional[UUID] = None
    video_url: HttpUrl
    video_id: str = Field(min_length=1, max_length=20)
    video_title: str
    channel_name: str
    channel_id: Optional[str] = Field(default=None, max_length=50)
    publish_date: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    language: str = Field(default="en", min_length=2, max_length=10)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


__all__ = ["YouTubeVideo"]


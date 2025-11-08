"""Repository for interacting with the `youtube_videos` table."""

from __future__ import annotations

from typing import Optional

from sage.db import ConnectionFactory
from sage.db.repositories import BaseRepository, RecordNotFoundError
from sage.models.video import YouTubeVideo


class VideoRepository(BaseRepository[YouTubeVideo]):
    """Data access object encapsulating YouTube video persistence logic."""

    table_name = "youtube_videos"
    model_type = YouTubeVideo
    insert_fields = (
        "video_url",
        "video_id",
        "video_title",
        "channel_name",
        "channel_id",
        "publish_date",
        "duration_seconds",
        "language",
    )
    update_fields = (
        "video_title",
        "channel_name",
        "channel_id",
        "publish_date",
        "duration_seconds",
        "language",
    )
    auto_timestamp_field = "updated_at"

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        super().__init__(connection_factory)

    def find_by_url(self, url: str) -> Optional[YouTubeVideo]:
        """Return an existing record by URL, if present."""

        try:
            return self.fetch_one("video_url = %(url)s", {"url": url})
        except RecordNotFoundError:
            return None

    def find_by_video_id(self, video_id: str) -> Optional[YouTubeVideo]:
        """Return an existing record by canonical YouTube ID, if present."""

        try:
            return self.fetch_one("video_id = %(video_id)s", {"video_id": video_id})
        except RecordNotFoundError:
            return None


__all__ = ["VideoRepository"]


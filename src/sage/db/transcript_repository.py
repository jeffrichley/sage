"""Repository for interacting with the `transcripts` table."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from psycopg2.extras import Json

from sage.db import ConnectionFactory
from sage.db.repositories import BaseRepository, RecordNotFoundError
from sage.models.transcript import Transcript


class TranscriptRepository(BaseRepository[Transcript]):
    """Data access object encapsulating transcript persistence logic."""

    table_name = "transcripts"
    model_type = Transcript
    insert_fields = (
        "video_id",
        "raw_transcript_json",
        "cleaned_transcript",
        "word_count",
        "transcript_source",
        "confidence_score",
        "has_timestamps",
    )
    update_fields = (
        "raw_transcript_json",
        "cleaned_transcript",
        "word_count",
        "transcript_source",
        "confidence_score",
        "has_timestamps",
    )

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        super().__init__(connection_factory)

    def find_latest_for_video(self, video_id: UUID) -> Optional[Transcript]:
        """Return the most recent transcript stored for a video."""

        try:
            row = self._fetch_one(
                "SELECT * FROM transcripts WHERE video_id = %(video_id)s ORDER BY created_at DESC LIMIT 1",
                {"video_id": str(video_id)},
            )
            return self.model_type.model_validate(row)
        except RecordNotFoundError:
            return None

    def _transform_value(self, field: str, value: object) -> object:
        if field == "raw_transcript_json" and value is not None:
            return Json(value)
        return super()._transform_value(field, value)


__all__ = ["TranscriptRepository"]


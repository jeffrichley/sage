"""Repository for interacting with the `summaries` table."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sage.db import ConnectionFactory
from sage.db.repositories import BaseRepository, RecordNotFoundError
from sage.models.summary import Summary


class SummaryRepository(BaseRepository[Summary]):
    """Data access object encapsulating summary persistence logic."""

    table_name = "summaries"
    model_type = Summary
    insert_fields = (
        "video_id",
        "transcript_id",
        "summary_text",
        "summary_word_count",
        "identified_topics",
        "identified_speakers",
        "key_takeaways",
        "model_name",
        "model_version",
        "prompt_template",
        "generation_timestamp",
        "generation_cost_usd",
        "generation_latency_seconds",
        "mem0_memory_id",
        "keyword_tags",
    )
    update_fields = (
        "summary_text",
        "summary_word_count",
        "identified_topics",
        "identified_speakers",
        "key_takeaways",
        "model_name",
        "model_version",
        "prompt_template",
        "generation_timestamp",
        "generation_cost_usd",
        "generation_latency_seconds",
        "mem0_memory_id",
        "keyword_tags",
    )

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        super().__init__(connection_factory)

    def find_by_mem0_id(self, memory_id: str) -> Optional[Summary]:
        """Return a stored summary using its Mem0 memory identifier."""

        try:
            return self.fetch_one("mem0_memory_id = %(memory_id)s", {"memory_id": memory_id})
        except RecordNotFoundError:
            return None

    def list_for_video(self, video_id: UUID) -> list[Summary]:
        """Return all summaries associated with a single video."""

        rows = self._fetch_many(
            "SELECT * FROM summaries WHERE video_id = %(video_id)s ORDER BY generation_timestamp DESC",
            {"video_id": str(video_id)},
        )
        return [self.model_type.model_validate(row) for row in rows]

    def _transform_value(self, field: str, value: object) -> object:
        if field == "generation_cost_usd" and isinstance(value, Decimal):
            return float(value)
        return super()._transform_value(field, value)


__all__ = ["SummaryRepository"]


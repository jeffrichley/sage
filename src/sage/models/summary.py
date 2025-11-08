"""Pydantic models representing stored summaries."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from sage.models.base import SageBaseModel


class Summary(SageBaseModel):
    """Domain model representing a row in the ``summaries`` table.

    Captures structured summary output, observability metrics, and references to related video and
    transcript records, along with Mem0 memory identifiers for semantic retrieval.
    """

    id: Optional[UUID] = None
    video_id: UUID
    transcript_id: UUID
    summary_text: str
    summary_word_count: int = Field(ge=0)
    identified_topics: List[str] = Field(default_factory=list)
    identified_speakers: List[str] = Field(default_factory=list)
    key_takeaways: List[str] = Field(default_factory=list)
    model_name: str
    model_version: Optional[str] = None
    prompt_template: Optional[str] = None
    generation_timestamp: Optional[datetime] = None
    generation_cost_usd: Optional[Decimal] = Field(default=None, ge=0)
    generation_latency_seconds: Optional[float] = Field(default=None, ge=0.0)
    mem0_memory_id: Optional[str] = None
    keyword_tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


__all__ = ["Summary"]


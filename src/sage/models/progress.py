"""Models describing summarization progress and output."""

from __future__ import annotations

from typing import List

from pydantic import Field

from sage.models.base import SageBaseModel


class SummaryOutput(SageBaseModel):
    """Structured payload returned by summarization workflows."""

    summary_text: str
    topics: List[str] = Field(default_factory=list)
    speakers: List[str] = Field(default_factory=list)
    key_takeaways: List[str] = Field(default_factory=list)


__all__ = ["SummaryOutput"]



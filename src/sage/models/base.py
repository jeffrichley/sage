"""Shared base model definitions for Sage domain objects."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SageBaseModel(BaseModel):
    """Base model configured for Sage-wide defaults."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


__all__ = ["SageBaseModel"]



"""Utility helpers shared across Sage modules."""

from enum import Enum


class Environment(str, Enum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


__all__ = ["Environment"]


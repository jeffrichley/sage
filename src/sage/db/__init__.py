"""Database utilities and connection helpers for Sage."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from psycopg2.extensions import connection as PsycopgConnection


class ConnectionFactory(Protocol):
    """Callable protocol that yields a managed psycopg2 connection."""

    def __call__(self) -> AbstractContextManager[PsycopgConnection]:
        """Return a context manager that produces a live database connection."""


__all__ = ["ConnectionFactory"]
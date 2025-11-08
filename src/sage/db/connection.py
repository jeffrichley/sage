"""Database connection utilities using psycopg2 connection pooling."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from psycopg2 import connect
from psycopg2.extensions import connection as PsycopgConnection
from psycopg2.pool import SimpleConnectionPool

from sage.config.settings import get_settings

DEFAULT_MIN_CONNECTIONS = 1
DEFAULT_MAX_CONNECTIONS = 5


class DatabasePool:
    """Lightweight wrapper around psycopg2's SimpleConnectionPool."""

    def __init__(
        self,
        dsn: str,
        *,
        min_connections: int = DEFAULT_MIN_CONNECTIONS,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
    ) -> None:
        self._pool = SimpleConnectionPool(min_connections, max_connections, dsn)

    @contextmanager
    def connection(self) -> Iterator[PsycopgConnection]:
        """Yield a transactional connection from the pool."""

        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:  # pragma: no cover - re-raised after rollback
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def close(self) -> None:
        """Close all pooled connections."""

        self._pool.closeall()


_pool: Optional[DatabasePool] = None


def _ensure_pool() -> DatabasePool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = DatabasePool(str(settings.database_url))
    return _pool


@contextmanager
def get_connection() -> Iterator[PsycopgConnection]:
    """Provide a pooled database connection as a context manager."""

    pool = _ensure_pool()
    with pool.connection() as conn:
        yield conn


def connection_from_dsn(dsn: str) -> PsycopgConnection:
    """Create a standalone connection using the given DSN."""

    return connect(dsn)


__all__ = ["DatabasePool", "connection_from_dsn", "get_connection"]


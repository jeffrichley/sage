"""Generic repository abstractions for Postgres-backed persistence."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import ClassVar, Dict, Generic, Iterable, Mapping, Optional, Sequence, Tuple, Type, TypeVar
from uuid import UUID

from psycopg2.extensions import connection as PsycopgConnection
from psycopg2.extras import RealDictCursor

from sage.db import ConnectionFactory
from sage.models.base import SageBaseModel

ModelT = TypeVar("ModelT", bound=SageBaseModel)


class RepositoryError(RuntimeError):
    """Base exception raised for repository layer failures."""


class RecordNotFoundError(RepositoryError):
    """Raised when a requested record cannot be located."""


class BaseRepository(Generic[ModelT]):
    """Reusable building block for table-specific repositories."""

    table_name: ClassVar[str]
    model_type: ClassVar[Type[ModelT]]
    insert_fields: ClassVar[Sequence[str]]
    update_fields: ClassVar[Sequence[str]]
    auto_timestamp_field: ClassVar[Optional[str]] = None

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def insert(self, model: ModelT) -> ModelT:
        """Persist a new record to the backing table."""

        payload = self._serialize(model, fields=self.insert_fields, include_none=False)
        columns, placeholders = self._build_insert_clause(payload)
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders}) RETURNING *"
        row = self._fetch_one(query, payload)
        return self.model_type.model_validate(row)

    def update(self, model: ModelT, *, include_none: bool = False) -> ModelT:
        """Update an existing record identified by its `id`."""

        record_id = getattr(model, "id", None)
        if record_id is None:
            raise RepositoryError("Update requires the model to include an `id` field.")

        payload = self._serialize(model, fields=self.update_fields, include_none=include_none)
        if not payload:
            raise RepositoryError("No fields provided for update.")
        payload["id"] = self._normalise_identifier(record_id)

        set_clause = self._build_update_clause(payload.keys())
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = %(id)s RETURNING *"
        row = self._fetch_one(query, payload)
        return self.model_type.model_validate(row)

    def get_by_id(self, record_id: object) -> ModelT:
        """Return a single record by its primary key."""

        query = f"SELECT * FROM {self.table_name} WHERE id = %(id)s"
        row = self._fetch_one(query, {"id": self._normalise_identifier(record_id)})
        return self.model_type.model_validate(row)

    def fetch_one(self, where_clause: str, params: Mapping[str, object]) -> ModelT:
        """Return the first record matching the provided predicate."""

        query = f"SELECT * FROM {self.table_name} WHERE {where_clause} LIMIT 1"
        row = self._fetch_one(query, params)
        return self.model_type.model_validate(row)

    def fetch_all(
        self,
        where_clause: Optional[str] = None,
        params: Optional[Mapping[str, object]] = None,
    ) -> list[ModelT]:
        """Return all records, optionally filtered by a predicate."""

        base_query = f"SELECT * FROM {self.table_name}"
        if where_clause:
            base_query = f"{base_query} WHERE {where_clause}"
        rows = self._fetch_many(base_query, params or {})
        return [self.model_type.model_validate(row) for row in rows]

    def delete_by_id(self, record_id: object) -> None:
        """Delete a record identified by its primary key."""

        query = f"DELETE FROM {self.table_name} WHERE id = %(id)s"
        self._execute(query, {"id": self._normalise_identifier(record_id)})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _serialize(
        self,
        model: ModelT,
        *,
        fields: Iterable[str],
        include_none: bool,
    ) -> Dict[str, object]:
        raw_values = model.model_dump(mode="json")
        payload: Dict[str, object] = {}

        for field in fields:
            if field not in raw_values:
                continue
            value = raw_values[field]
            if value is None and not include_none:
                continue
            payload[field] = self._transform_value(field, value)

        return payload

    def _transform_value(self, field: str, value: object) -> object:  # noqa: D401
        """Hook for subclasses to customise value transformations."""

        return value

    def _build_insert_clause(self, payload: Mapping[str, object]) -> Tuple[str, str]:
        columns = ", ".join(payload.keys())
        placeholders = ", ".join(f"%({field})s" for field in payload.keys())
        return columns, placeholders

    def _build_update_clause(self, payload_keys: Iterable[str]) -> str:
        assignments = []
        for field in payload_keys:
            if field == "id":
                continue
            assignments.append(f"{field} = %({field})s")
        if self.auto_timestamp_field:
            assignments.append(f"{self.auto_timestamp_field} = NOW()")
        if not assignments:
            raise RepositoryError("No columns available for update.")
        return ", ".join(assignments)

    def _fetch_one(self, query: str, params: Mapping[str, object]) -> Mapping[str, object]:
        with self._connection() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFoundError(f"No records returned for query: {query!r}")
                return dict(row)

    def _fetch_many(self, query: str, params: Mapping[str, object]) -> list[Mapping[str, object]]:
        with self._connection() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def _execute(self, query: str, params: Mapping[str, object]) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)

    def _connection(self) -> AbstractContextManager[PsycopgConnection]:
        return self._connection_factory()

    def _normalise_identifier(self, value: object) -> object:
        if isinstance(value, UUID):
            return str(value)
        return value


__all__ = [
    "BaseRepository",
    "RecordNotFoundError",
    "RepositoryError",
]


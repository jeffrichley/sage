"""Utilities for executing SQL migrations stored under `db/migrations`."""

from __future__ import annotations

from pathlib import Path
from typing import List

from psycopg2.extensions import cursor as PsycopgCursor
from rich.console import Console
from rich.table import Table

from sage.config.settings import get_settings
from sage.db.connection import connection_from_dsn

MIGRATIONS_ROOT = Path(__file__).resolve().parent / "migrations"


def _load_migration_files(directory: Path) -> List[Path]:
    return sorted(directory.glob("*.sql"))


def _execute_sql_file(db_cursor: PsycopgCursor, migration_file: Path) -> None:
    statement = migration_file.read_text(encoding="utf-8")
    db_cursor.execute(statement)


def run_migrations(console: Console | None = None) -> None:
    """Execute all SQL migrations in order."""

    console = console or Console()
    migrations = _load_migration_files(MIGRATIONS_ROOT)

    if not migrations:
        console.print("[yellow]No migrations found.[/yellow]")
        return

    settings = get_settings()
    connection = connection_from_dsn(str(settings.database_url))

    table = Table(title="Database Migrations")
    table.add_column("Migration", style="cyan")
    table.add_column("Status", style="green")

    try:
        with connection.cursor() as db_cursor:
            for migration in migrations:
                _execute_sql_file(db_cursor, migration)
                table.add_row(migration.name, "applied")
        connection.commit()
    except Exception as exc:  # pragma: no cover - surface migration errors
        connection.rollback()
        console.print(f"[red]Migration failed:[/red] {exc}")
        raise
    finally:
        connection.close()

    console.print(table)


def main() -> None:
    """Entry point for running migrations via `python -m sage.db.migrate`."""

    run_migrations()


if __name__ == "__main__":  # pragma: no cover
    main()


"""Quick connectivity check for the local Supabase Postgres instance."""

from __future__ import annotations

from psycopg2 import connect

from sage.config.settings import get_settings


def main() -> None:
    """Attempt a simple connection and query against DATABASE_URL."""

    settings = get_settings()
    dsn = str(settings.database_url)
    try:
        with connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                print("Connection successful, SELECT 1 returned:", cur.fetchone())
    except Exception as exc:  # pragma: no cover - diagnostic script
        print("Connection failed:", exc)


if __name__ == "__main__":
    main()


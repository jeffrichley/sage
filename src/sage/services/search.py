"""Hybrid search service combining Postgres FTS with Mem0 semantic search."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence
from uuid import UUID

from psycopg2.extras import RealDictCursor
from rich.console import Console

try:  # pragma: no cover - optional dependency
    from mem0 import MemoryClient
except ImportError:  # pragma: no cover
    MemoryClient = None  # type: ignore[assignment]

from sage.config.settings import Settings, get_settings
from sage.db.connection import get_connection


@dataclass(slots=True)
class SearchFilters:
    """Options that constrain search results."""

    channel_name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: Sequence[str] = ()


@dataclass(slots=True)
class SearchResult:
    """Unified representation of keyword and semantic search output."""

    video_id: Optional[UUID]
    video_url: Optional[str]
    video_title: Optional[str]
    channel_name: Optional[str]
    publish_date: Optional[datetime]
    summary_text: Optional[str]
    keyword_tags: List[str]
    keyword_score: float
    semantic_score: float
    hybrid_score: float
    mem0_memory_id: Optional[str]
    summary_id: Optional[UUID]
    transcript_id: Optional[UUID]

    @property
    def identity(self) -> str:
        if self.mem0_memory_id:
            return self.mem0_memory_id
        if self.video_id:
            return str(self.video_id)
        if self.video_url:
            return self.video_url
        return id(self).__repr__()


class SearchService:
    """Coordinate keyword and semantic search across storage backends."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        console: Optional[Console] = None,
        memory_client: Optional[MemoryClient] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._console = console or Console()
        self._connection_factory = get_connection
        self._memory_client = memory_client or self._initialise_memory_client()

    # ------------------------------------------------------------------ #
    # Keyword search                                                     #
    # ------------------------------------------------------------------ #
    def postgres_keyword_search(
        self,
        query: str,
        *,
        limit: int = 20,
        filters: Optional[SearchFilters] = None,
    ) -> List[SearchResult]:
        """Execute a Postgres full-text search across transcripts and summaries.

        Parameters
        ----------
        query:
            Keyword query parsed via ``plainto_tsquery`` for ranking.
        limit:
            Maximum number of results returned.
        filters:
            Optional metadata filters applied to the SQL query.
        """

        filter_clauses: List[str] = []
        params: Dict[str, object] = {"query": query, "limit": limit}

        if filters:
            if filters.channel_name:
                filter_clauses.append("v.channel_name ILIKE %(channel_name)s")
                params["channel_name"] = f"%{filters.channel_name}%"
            if filters.start_date:
                filter_clauses.append("v.publish_date >= %(start_date)s")
                params["start_date"] = filters.start_date
            if filters.end_date:
                filter_clauses.append("v.publish_date <= %(end_date)s")
                params["end_date"] = filters.end_date
            if filters.tags:
                filter_clauses.append("s.keyword_tags && %(tags)s::text[]")
                params["tags"] = list(filters.tags)

        where_fragment = ""
        if filter_clauses:
            where_fragment = " AND " + " AND ".join(filter_clauses)

        sql = f"""
            SELECT
                v.id AS video_id,
                v.video_url,
                v.video_title,
                v.channel_name,
                v.publish_date,
                s.summary_text,
                s.keyword_tags,
                s.id AS summary_id,
                t.id AS transcript_id,
                s.mem0_memory_id,
                ts_rank_cd(
                    to_tsvector('english', coalesce(t.cleaned_transcript, '') || ' ' || coalesce(s.summary_text, '')),
                    plainto_tsquery('english', %(query)s)
                ) AS keyword_score
            FROM youtube_videos v
            LEFT JOIN transcripts t ON v.id = t.video_id
            LEFT JOIN summaries s ON v.id = s.video_id
            WHERE to_tsvector('english', coalesce(t.cleaned_transcript, '') || ' ' || coalesce(s.summary_text, ''))
                  @@ plainto_tsquery('english', %(query)s)
                  {where_fragment}
            ORDER BY keyword_score DESC
            LIMIT %(limit)s
        """

        with self._connection_factory() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

        results: List[SearchResult] = []
        for row in rows:
            keyword_tags = list(row.get("keyword_tags") or [])
            publish_date = row.get("publish_date")
            if publish_date is not None and not isinstance(publish_date, datetime):
                publish_date = datetime.fromisoformat(str(publish_date))
            results.append(
                SearchResult(
                    video_id=self._coerce_uuid(row.get("video_id")),
                    video_url=row.get("video_url"),
                    video_title=row.get("video_title"),
                    channel_name=row.get("channel_name"),
                    publish_date=publish_date,
                    summary_text=row.get("summary_text"),
                    keyword_tags=keyword_tags,
                    keyword_score=float(row.get("keyword_score") or 0.0),
                    semantic_score=0.0,
                    hybrid_score=float(row.get("keyword_score") or 0.0),
                    mem0_memory_id=row.get("mem0_memory_id"),
                    summary_id=self._coerce_uuid(row.get("summary_id")),
                    transcript_id=self._coerce_uuid(row.get("transcript_id")),
                )
            )
        return results

    # ------------------------------------------------------------------ #
    # Semantic search                                                    #
    # ------------------------------------------------------------------ #
    def pgvector_semantic_search(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> List[SearchResult]:
        """Delegate semantic matching to Mem0."""

        if self._memory_client is None:
            return []

        try:
            results = self._memory_client.search(query=query, limit=limit)
        except Exception as exc:  # pragma: no cover - external service
            self._console.log(f"[yellow]Mem0 semantic search failed:[/yellow] {exc}")
            return []

        parsed: List[SearchResult] = []
        for item in results:
            metadata = item.get("metadata", {}) if isinstance(item, Mapping) else {}
            mem0_id = item.get("id") if isinstance(item, Mapping) else None
            score = float(item.get("score", 0.0)) if isinstance(item, Mapping) else 0.0
            publish_date = metadata.get("publish_date")
            if publish_date and not isinstance(publish_date, datetime):
                try:
                    publish_date = datetime.fromisoformat(str(publish_date))
                except ValueError:
                    publish_date = None

            tags = metadata.get("tags") or metadata.get("keyword_tags") or []
            if isinstance(tags, str):
                tags = [tags]

            parsed.append(
                SearchResult(
                    video_id=self._coerce_uuid(metadata.get("video_id")),
                    video_url=metadata.get("video_url"),
                    video_title=metadata.get("video_title"),
                    channel_name=metadata.get("channel_name"),
                    publish_date=publish_date,
                    summary_text=metadata.get("summary_text"),
                    keyword_tags=list(tags) if isinstance(tags, Iterable) else [],
                    keyword_score=0.0,
                    semantic_score=score,
                    hybrid_score=score,
                    mem0_memory_id=str(mem0_id) if mem0_id else None,
                    summary_id=self._coerce_uuid(metadata.get("summary_id")),
                    transcript_id=self._coerce_uuid(metadata.get("transcript_id")),
                )
            )
        return parsed

    # ------------------------------------------------------------------ #
    # Hybrid orchestration                                               #
    # ------------------------------------------------------------------ #
    def merge_search_results(
        self,
        keyword_results: Sequence[SearchResult],
        semantic_results: Sequence[SearchResult],
        *,
        keyword_weight: float = 0.5,
        semantic_weight: float = 0.5,
    ) -> List[SearchResult]:
        """Combine keyword and semantic search results into a unified ranking."""

        combined: Dict[str, SearchResult] = {}

        for result in keyword_results:
            combined[result.identity] = replace(
                result,
                hybrid_score=result.keyword_score * keyword_weight,
                semantic_score=0.0,
            )

        for result in semantic_results:
            hybrid_component = result.semantic_score * semantic_weight
            existing = combined.get(result.identity)
            if existing:
                merged_tags = self._merge_tags(existing.keyword_tags, result.keyword_tags)
                combined[result.identity] = replace(
                    existing,
                    semantic_score=result.semantic_score,
                    hybrid_score=existing.hybrid_score + hybrid_component,
                    keyword_tags=merged_tags,
                    mem0_memory_id=existing.mem0_memory_id or result.mem0_memory_id,
                    summary_text=existing.summary_text or result.summary_text,
                    video_url=existing.video_url or result.video_url,
                    video_title=existing.video_title or result.video_title,
                    channel_name=existing.channel_name or result.channel_name,
                    summary_id=existing.summary_id or result.summary_id,
                    transcript_id=existing.transcript_id or result.transcript_id,
                )
            else:
                combined[result.identity] = replace(
                    result,
                    hybrid_score=hybrid_component,
                    keyword_score=0.0,
                )

        merged = list(combined.values())
        merged.sort(key=lambda item: item.hybrid_score, reverse=True)
        return merged

    def hybrid_search(
        self,
        query: str,
        *,
        limit: int = 20,
        filters: Optional[SearchFilters] = None,
    ) -> List[SearchResult]:
        """Perform a hybrid search and return ranked results."""

        keyword_results = self.postgres_keyword_search(query, limit=limit, filters=filters)
        semantic_results = self.pgvector_semantic_search(query, limit=limit)
        merged = self.merge_search_results(keyword_results, semantic_results)

        if filters:
            merged = self.filter_by_metadata(merged, filters)

        return merged[:limit]

    def filter_by_metadata(self, results: Sequence[SearchResult], filters: SearchFilters) -> List[SearchResult]:
        """Apply metadata filtering to an existing list of results."""

        filtered: List[SearchResult] = []
        for result in results:
            if filters.channel_name:
                channel = (result.channel_name or "").lower()
                if filters.channel_name.lower() not in channel:
                    continue

            if filters.start_date and result.publish_date:
                if result.publish_date < filters.start_date:
                    continue

            if filters.end_date and result.publish_date:
                if result.publish_date > filters.end_date:
                    continue

            if filters.tags:
                if not set(tag.lower() for tag in result.keyword_tags).intersection(
                    tag.lower() for tag in filters.tags
                ):
                    continue

            filtered.append(result)
        return filtered

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _initialise_memory_client(self) -> Optional[MemoryClient]:
        """Instantiate a Mem0 client for semantic search when configured."""

        if MemoryClient is None:
            self._console.log("[yellow]Mem0 package unavailable - semantic search disabled.[/yellow]")
            return None

        api_key = self._settings.mem0_api_key
        if api_key is None:
            self._console.log("[yellow]MEM0_API_KEY not configured - semantic search disabled.[/yellow]")
            return None

        try:
            return MemoryClient(api_key=api_key.get_secret_value())
        except Exception as exc:  # pragma: no cover - external dependency errors
            self._console.log(f"[red]Failed to initialise Mem0 client for search:[/red] {exc}")
            return None

    def _coerce_uuid(self, value: object) -> Optional[UUID]:
        """Attempt to coerce arbitrary values to UUID instances."""

        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _merge_tags(self, existing: Iterable[str], incoming: Iterable[str]) -> List[str]:
        """Merge keyword lists while preserving stable ordering."""

        merged: List[str] = []
        seen = set()
        for tag in list(existing) + list(incoming):
            cleaned = tag.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            merged.append(cleaned)
            seen.add(key)
        return merged


__all__ = ["SearchFilters", "SearchResult", "SearchService"]


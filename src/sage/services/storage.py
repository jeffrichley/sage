"""Persistence layer responsible for storing ingestion artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence
from uuid import UUID

from rich.console import Console

try:  # pragma: no cover - optional dependency may be absent in test environments
    from mem0 import MemoryClient
except ImportError:  # pragma: no cover
    MemoryClient = None  # type: ignore[assignment]

from sage.config.settings import Settings, get_settings
from sage.db.connection import get_connection
from sage.db.migrate import run_migrations
from sage.db.summary_repository import SummaryRepository
from sage.db.transcript_repository import TranscriptRepository
from sage.db.video_repository import VideoRepository
from sage.models.summary import Summary
from sage.models.transcript import Transcript
from sage.models.video import YouTubeVideo
from sage.utils.progress import ProcessingStage, ProgressUpdate


class StorageError(RuntimeError):
    """Base exception raised when persistence fails."""


class VideoAlreadyExistsError(StorageError):
    """Raised when attempting to store a duplicate video without force override."""


@dataclass(slots=True)
class StorageResult:
    """Container representing stored database entities."""

    video: YouTubeVideo
    transcript: Transcript
    summary: Optional[Summary]
    keyword_tags: List[str]
    mem0_memory_id: Optional[str]


class StorageService:
    """Persist video metadata, transcripts, and summaries with optional Mem0 linkage."""

    _migrations_applied: bool = False

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        console: Optional[Console] = None,
        memory_client: Optional[MemoryClient] = None,
        auto_migrate: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._console = console or Console()
        self._connection_factory = get_connection
        self._video_repo = VideoRepository(self._connection_factory)
        self._transcript_repo = TranscriptRepository(self._connection_factory)
        self._summary_repo = SummaryRepository(self._connection_factory)
        self._memory_client = memory_client or self._initialise_memory_client()

        if auto_migrate and not StorageService._migrations_applied:
            try:
                run_migrations(console=self._console)
            except Exception as exc:  # pragma: no cover - surfaced to caller
                raise StorageError(f"Failed to run database migrations: {exc}") from exc
            StorageService._migrations_applied = True

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def store_video_metadata(
        self,
        metadata: Mapping[str, object],
        *,
        force: bool = False,
    ) -> YouTubeVideo:
        """Insert or optionally update video metadata.

        Parameters
        ----------
        metadata:
            Mapping of video metadata fields compatible with :class:`YouTubeVideo`.
        force:
            When ``True`` an existing video record is updated instead of raising an error.

        Returns
        -------
        YouTubeVideo
            Persisted model instance representing the stored database record.

        Raises
        ------
        VideoAlreadyExistsError
            If the video already exists and ``force`` is ``False``.
        """

        model = YouTubeVideo.model_validate(metadata)
        existing = self._video_repo.find_by_url(str(model.video_url))

        if existing and not force:
            raise VideoAlreadyExistsError(f"Video '{model.video_url}' already stored.")

        if existing and force:
            updated = existing.model_copy(
                update=model.model_dump(
                    mode="json",
                    include={
                        "video_title",
                        "channel_name",
                        "channel_id",
                        "publish_date",
                        "duration_seconds",
                        "language",
                    },
                )
            )
            return self._video_repo.update(updated, include_none=True)

        return self._video_repo.insert(model)

    def store_transcript(self, transcript: Transcript, *, video_id: UUID) -> Transcript:
        """Persist transcript information linked to a specific video record."""

        record = transcript.model_copy(update={"video_id": video_id})
        return self._transcript_repo.insert(record)

    def store_summary(
        self,
        summary_text: str,
        *,
        video_id: UUID,
        transcript_id: UUID,
        keyword_tags: Sequence[str],
        model_name: str,
        model_version: Optional[str],
        prompt_template: Optional[str],
        memory_id: Optional[str],
        topics: Sequence[str],
        speakers: Sequence[str],
        key_takeaways: Sequence[str],
        generation_cost_usd: Optional[float] = None,
        generation_latency_seconds: Optional[float] = None,
    ) -> Summary:
        """Store summarisation output alongside metadata and analytics details."""

        summary_model = Summary(
            video_id=video_id,
            transcript_id=transcript_id,
            summary_text=summary_text,
            summary_word_count=len(summary_text.split()),
            identified_topics=list(topics),
            identified_speakers=list(speakers),
            key_takeaways=list(key_takeaways),
            model_name=model_name,
            model_version=model_version,
            prompt_template=prompt_template,
            generation_timestamp=datetime.now(timezone.utc),
            generation_cost_usd=generation_cost_usd,
            generation_latency_seconds=generation_latency_seconds,
            mem0_memory_id=memory_id,
            keyword_tags=list(keyword_tags),
        )
        return self._summary_repo.insert(summary_model)

    def store_complete_entry(
        self,
        *,
        metadata: Mapping[str, object],
        transcript: Transcript,
        transcript_text: str,
        summary_text: Optional[str],
        summary_topics: Sequence[str],
        summary_speakers: Sequence[str],
        summary_takeaways: Sequence[str],
        keyword_tags: Sequence[str],
        model_name: Optional[str],
        model_version: Optional[str],
        prompt_template: Optional[str],
        manual_tags: Sequence[str],
        generation_cost_usd: Optional[float],
        generation_latency_seconds: Optional[float],
        video_url: str,
        force: bool,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> StorageResult:
        """Persist the full ingestion artefact set and return stored models.

        Parameters
        ----------
        metadata:
            Video metadata dictionary produced by :meth:`TranscriptService.extract_video_metadata`.
        transcript:
            Transcript model containing segment and cleaned text information.
        transcript_text:
            Clean transcript text used for embedding generation.
        summary_text:
            Optional summary text to persist and embed. When ``None`` only transcript data is stored.
        summary_topics, summary_speakers, summary_takeaways:
            Structured summary metadata.
        keyword_tags:
            Tags generated from summarisation analysis.
        model_name, model_version, prompt_template:
            Details describing the language model invocation that produced the summary.
        manual_tags:
            User-provided tags that should be merged with generated tags.
        generation_cost_usd, generation_latency_seconds:
            Optional observability metrics captured during summarisation.
        video_url:
            Original ingestion URL, used for progress reporting.
        force:
            Whether to override existing video entries.
        on_progress:
            Optional callback invoked with progress updates.

        Returns
        -------
        StorageResult
            Aggregated result containing persisted models and derived metadata.

        Raises
        ------
        StorageError
            If persistence fails or required inputs are missing.
        """

        summary_state = "enabled" if summary_text is not None else "disabled"
        self._console.log(
            f"[blue]Storage:[/blue] beginning persistence pipeline "
            f"(video_url={video_url}, summary={summary_state})"
        )

        combined_tags = self._merge_tags(keyword_tags, manual_tags)

        self._emit_progress(on_progress, 10, "Persisting video metadata", video_url)
        video = self.store_video_metadata(metadata, force=force)
        if video.id is None:
            raise StorageError("Video insert did not return an identifier.")

        self._emit_progress(on_progress, 40, "Saving transcript", video_url)
        stored_transcript = self.store_transcript(transcript, video_id=video.id)
        if stored_transcript.id is None:
            raise StorageError("Transcript insert did not return an identifier.")

        summary_record: Optional[Summary] = None
        memory_id: Optional[str] = None

        if summary_text is not None:
            self._emit_progress(on_progress, 70, "Creating semantic memory entry", video_url)
            memory_id = self._generate_summary_embedding(
                transcript_text=transcript_text,
                summary_text=summary_text,
                metadata=metadata,
                keyword_tags=combined_tags,
            )

            if model_name is None:
                raise StorageError("Summary model name must be provided when storing summaries.")

            self._emit_progress(on_progress, 90, "Saving summary", video_url)
            summary_record = self.store_summary(
                summary_text,
                video_id=video.id,
                transcript_id=stored_transcript.id,
                keyword_tags=combined_tags,
                model_name=model_name,
                model_version=model_version,
                prompt_template=prompt_template,
                memory_id=memory_id,
                topics=summary_topics,
                speakers=summary_speakers,
                key_takeaways=summary_takeaways,
                generation_cost_usd=generation_cost_usd,
                generation_latency_seconds=generation_latency_seconds,
            )
            stored_summary_id = str(summary_record.id) if summary_record and summary_record.id else "unknown"
            self._console.log(
                f"[green]Storage:[/green] summary stored successfully "
                f"(video_url={video_url}, summary_id={stored_summary_id})"
            )
        else:
            self._console.log(
                "[yellow]Storage:[/yellow] skipping summary storage "
                f"(video_url={video_url}, reason=summaries disabled or unavailable)"
            )

        self._emit_progress(on_progress, 100, "Storage completed", video_url)
        summary_id_str = str(summary_record.id) if summary_record and summary_record.id else "n/a"
        transcript_id_str = str(stored_transcript.id) if stored_transcript.id else "n/a"
        self._console.log(
            "[green]Storage:[/green] pipeline completed "
            f"(video_url={video_url}, video_id={video.id}, transcript_id={transcript_id_str}, summary_id={summary_id_str})"
        )
        return StorageResult(
            video=video,
            transcript=stored_transcript,
            summary=summary_record,
            keyword_tags=list(combined_tags),
            mem0_memory_id=memory_id,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _initialise_memory_client(self) -> Optional[MemoryClient]:
        """Attempt to instantiate a Mem0 client for semantic storage."""

        if MemoryClient is None:
            self._console.log("[yellow]Mem0 client unavailable - semantic storage disabled.[/yellow]")
            return None

        api_key = self._settings.mem0_api_key
        if api_key is None:
            self._console.log("[yellow]MEM0_API_KEY not configured - semantic storage disabled.[/yellow]")
            return None

        try:
            return MemoryClient(api_key=api_key.get_secret_value())
        except Exception as exc:  # pragma: no cover - external dependency errors
            self._console.log(f"[red]Failed to initialise Mem0 client:[/red] {exc}")
            return None

    def _generate_summary_embedding(
        self,
        *,
        transcript_text: str,
        summary_text: str,
        metadata: Mapping[str, object],
        keyword_tags: Sequence[str],
    ) -> Optional[str]:
        """Create a Mem0 memory entry combining transcript and summary content."""

        if self._memory_client is None:
            return None

        payload_metadata: Dict[str, object] = {
            "video_url": metadata.get("video_url"),
            "video_title": metadata.get("video_title"),
            "channel_name": metadata.get("channel_name"),
            "tags": list(keyword_tags),
        }

        try:
            result = self._memory_client.add(
                messages=[{"role": "user", "content": f"{transcript_text}\n\n{summary_text}"}],
                metadata=payload_metadata,
            )
        except Exception as exc:  # pragma: no cover - network failures
            self._console.log(f"[yellow]Mem0 storage failed:[/yellow] {exc}")
            return None

        if isinstance(result, str):
            return result
        if isinstance(result, Mapping):
            return str(result.get("id") or result.get("memory_id"))
        return None

    def _merge_tags(self, keyword_tags: Iterable[str], manual_tags: Iterable[str]) -> List[str]:
        """Merge generated and manual tags while preserving original ordering."""

        merged: List[str] = []
        seen = set()

        for tag in list(keyword_tags) + list(manual_tags):
            cleaned = tag.strip()
            if not cleaned:
                continue
            lower = cleaned.lower()
            if lower in seen:
                continue
            merged.append(cleaned)
            seen.add(lower)
        return merged

    def _emit_progress(
        self,
        callback: Optional[Callable[[ProgressUpdate], None]],
        stage_progress: int,
        message: str,
        video_url: str,
    ) -> None:
        """Emit storage progress updates if a callback has been provided."""

        if callback is None:
            return
        callback(
            ProgressUpdate(
                stage=ProcessingStage.STORING,
                stage_progress=stage_progress,
                overall_progress=stage_progress,
                message=message,
                video_url=video_url,
            )
        )


__all__ = ["StorageError", "StorageResult", "StorageService", "VideoAlreadyExistsError"]


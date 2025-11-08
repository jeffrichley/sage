"""CLI commands for ingesting, storing, searching, and batching YouTube videos."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import unicodedata
from typing import Callable, Iterable, Mapping, Optional, Sequence
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn
from rich.table import Table

from sage.db.connection import get_connection
from sage.db.repositories import RecordNotFoundError
from sage.db.summary_repository import SummaryRepository
from sage.db.transcript_repository import TranscriptRepository
from sage.db.video_repository import VideoRepository
from sage.models.progress import SummaryOutput
from sage.models.queue import QueueItem
from sage.services.queue import QueueService
from sage.services.search import SearchFilters, SearchResult, SearchService
from sage.services.storage import StorageError, StorageResult, StorageService, VideoAlreadyExistsError
from sage.services.summarization import SummarizationError, SummarizationService
from sage.services.transcript import TranscriptService
from sage.utils.progress import ProcessingStage, ProgressUpdate
from sage.utils.validation import extract_video_id, InvalidYouTubeURLError
from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable


class IngestExitCode:
    """Mapping of meaningful CLI exit codes."""

    SUCCESS = 0
    INVALID_INPUT = 1
    VIDEO_UNAVAILABLE = 2
    NETWORK_ERROR = 3
    PROCESSING_ERROR = 4
    STORAGE_ERROR = 5


@dataclass(slots=True)
class IngestionResult:
    """Aggregate result returned after the ingestion pipeline completes."""

    metadata: dict[str, object]
    transcript_display: str
    transcript_source: str
    transcript_word_count: int
    summary_output: Optional[SummaryOutput]
    storage: StorageResult


StageRanges = dict[ProcessingStage, tuple[int, int]]

_WINDOWS_CHAR_REPLACEMENTS = {
    ord("\u00a0"): " ",
    ord("\u2010"): "-",
    ord("\u2011"): "-",
    ord("\u2012"): "-",
    ord("\u2013"): "-",
    ord("\u2014"): "-",
    ord("\u2015"): "-",
    ord("\u2212"): "-",
    ord("\u2018"): "'",
    ord("\u2019"): "'",
    ord("\u201a"): "'",
    ord("\u201b"): "'",
    ord("\u201c"): '"',
    ord("\u201d"): '"',
    ord("\u201e"): '"',
    ord("\u2026"): "...",
}


def register(app: typer.Typer, console: Console) -> None:
    """Register CLI commands for YouTube ingestion and search."""

    @lru_cache(maxsize=1)
    def get_transcript_service() -> TranscriptService:
        return TranscriptService(console=console)

    @lru_cache(maxsize=1)
    def get_summarization_service() -> SummarizationService:
        return SummarizationService(console=console)

    @lru_cache(maxsize=1)
    def get_storage_service() -> StorageService:
        return StorageService(console=console)

    @lru_cache(maxsize=1)
    def get_search_service() -> SearchService:
        return SearchService(console=console)

    @lru_cache(maxsize=1)
    def get_summary_repository() -> SummaryRepository:
        return SummaryRepository(get_connection)

    @lru_cache(maxsize=1)
    def get_transcript_repository() -> TranscriptRepository:
        return TranscriptRepository(get_connection)

    @lru_cache(maxsize=1)
    def get_video_repository() -> VideoRepository:
        return VideoRepository(get_connection)

    stage_ranges: StageRanges = {
        ProcessingStage.VALIDATING: (0, 5),
        ProcessingStage.DOWNLOADING: (5, 25),
        ProcessingStage.TRANSCRIBING: (25, 70),
        ProcessingStage.SUMMARIZING: (70, 90),
        ProcessingStage.STORING: (90, 100),
        ProcessingStage.COMPLETE: (100, 100),
        ProcessingStage.FAILED: (0, 0),
    }

    async def ingest_pipeline(
        *,
        url: str,
        manual_tags: Sequence[str],
        remove_timestamps: bool,
        summarize: bool,
        summary_length: int,
        force: bool,
        progress_callback: Optional[Callable[[ProgressUpdate], None]],
    ) -> IngestionResult:
        video_id = extract_video_id(url)
        transcript_service = get_transcript_service()

        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    stage=ProcessingStage.DOWNLOADING,
                    stage_progress=10,
                    overall_progress=10,
                    message="Fetching video metadata",
                    video_url=url,
                )
            )

        metadata = await asyncio.to_thread(transcript_service.extract_video_metadata, video_id)

        transcript = await asyncio.to_thread(
            transcript_service.get_transcript,
            url,
            on_progress=progress_callback,
        )

        summary_output: Optional[SummaryOutput] = None
        generated_tags: Sequence[str] = ()
        summarization_service: Optional[SummarizationService] = None

        if summarize:
            summarization_service = get_summarization_service()
            try:
                summary_output = await summarization_service.summarize(
                    transcript.cleaned_transcript,
                    max_words=summary_length,
                    metadata={**metadata, "video_url": url},
                    on_progress=progress_callback,
                )
                generated_tags = summarization_service.extract_keywords(summary_output, transcript.cleaned_transcript)
            except SummarizationError:
                raise
        else:
            if progress_callback:
                progress_callback(
                    ProgressUpdate(
                        stage=ProcessingStage.SUMMARIZING,
                        stage_progress=100,
                        overall_progress=80,
                        message="Summarization skipped",
                        video_url=url,
                    )
                )

        storage_result = await asyncio.to_thread(
            get_storage_service().store_complete_entry,
            metadata=metadata,
            transcript=transcript,
            transcript_text=transcript.cleaned_transcript,
            summary_text=summary_output.summary_text if summary_output else None,
            summary_topics=summary_output.topics if summary_output else [],
            summary_speakers=summary_output.speakers if summary_output else [],
            summary_takeaways=summary_output.key_takeaways if summary_output else [],
            keyword_tags=list(generated_tags),
            model_name=summarization_service.model_name if summary_output and summarization_service else None,
            model_version=None,
            prompt_template=summarization_service.system_prompt if summary_output and summarization_service else None,
            manual_tags=manual_tags,
            generation_cost_usd=None,
            generation_latency_seconds=None,
            video_url=url,
            force=force,
            on_progress=progress_callback,
        )

        display_text = (
            storage_result.transcript.cleaned_transcript
            if remove_timestamps
            else _format_segments(transcript.raw_transcript_json)
        )

        return IngestionResult(
            metadata=dict(metadata),
            transcript_display=display_text or "<empty transcript>",
            transcript_source=transcript.transcript_source.value,
            transcript_word_count=transcript.word_count,
            summary_output=summary_output,
            storage=storage_result,
        )

    _queue_service_holder: dict[str, QueueService] = {}

    def get_queue_service() -> QueueService:
        if "instance" not in _queue_service_holder:

            async def queue_ingestion_handler(
                item: QueueItem,
                progress_handler: Callable[[ProgressUpdate], None],
            ) -> None:
                await ingest_pipeline(
                    url=str(item.video_url),
                    manual_tags=item.manual_tags,
                    remove_timestamps=item.remove_timestamps,
                    summarize=item.summarize,
                    summary_length=item.summary_length,
                    force=item.force,
                    progress_callback=progress_handler,
                )

            _queue_service_holder["instance"] = QueueService(
                ingestion_handler=queue_ingestion_handler,
                console=console,
            )
        return _queue_service_holder["instance"]

    @app.command("ingest-youtube")
    def ingest_youtube(  # pylint: disable=too-many-arguments
        url: str = typer.Argument(..., help="YouTube video URL to ingest"),
        remove_timestamps: bool = typer.Option(
            False, "--remove-timestamps", help="Remove timestamps from transcript output"
        ),
        summarize: bool = typer.Option(True, "--summarize/--no-summarize", help="Generate summary"),
        tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated manual tags"),
        summary_length: int = typer.Option(300, "--summary-length", help="Maximum words in summary"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress interactive output"),
        force: bool = typer.Option(False, "--force", help="Re-ingest even if URL already exists"),
    ) -> None:
        manual_tags = _parse_tags(tags)

        progress: Optional[Progress] = None
        progress_task: Optional[TaskID] = None
        progress_handler: Optional[Callable[[ProgressUpdate], None]] = None

        if not quiet:
            progress = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            )

        try:
            if progress is None:
                result = asyncio.run(
                    ingest_pipeline(
                        url=url,
                        manual_tags=manual_tags,
                        remove_timestamps=remove_timestamps,
                        summarize=summarize,
                        summary_length=summary_length,
                        force=force,
                        progress_callback=None,
                    )
                )
            else:
                with progress as running_progress:
                    progress_task = running_progress.add_task("Processing", total=100)
                    progress_handler = _progress_handler_factory(running_progress, progress_task, stage_ranges)
                    result = asyncio.run(
                        ingest_pipeline(
                            url=url,
                            manual_tags=manual_tags,
                            remove_timestamps=remove_timestamps,
                            summarize=summarize,
                            summary_length=summary_length,
                            force=force,
                            progress_callback=progress_handler,
                        )
                    )
        except InvalidYouTubeURLError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=IngestExitCode.INVALID_INPUT) from exc
        except VideoUnavailable as exc:
            console.print(f"[red]Error:[/red] Video not accessible\nURL: {url}")
            raise typer.Exit(code=IngestExitCode.VIDEO_UNAVAILABLE) from exc
        except TranscriptsDisabled:
            console.print("[red]Error:[/red] Transcript unavailable and Whisper fallback failed")
            raise typer.Exit(code=IngestExitCode.PROCESSING_ERROR) from None
        except SummarizationError as exc:
            console.print(f"[red]Summarization failed:[/red] {exc}")
            raise typer.Exit(code=IngestExitCode.PROCESSING_ERROR) from exc
        except VideoAlreadyExistsError as exc:
            console.print(f"[yellow]{exc} Use --force to re-ingest.[/yellow]")
            raise typer.Exit(code=IngestExitCode.STORAGE_ERROR) from exc
        except StorageError as exc:
            console.print(f"[red]Storage error:[/red] {exc}")
            raise typer.Exit(code=IngestExitCode.STORAGE_ERROR) from exc
        except Exception as exc:  # pragma: no cover - unexpected failure
            console.print(f"[red]Unexpected error:[/red] {exc}")
            raise typer.Exit(code=IngestExitCode.NETWORK_ERROR) from exc

        if quiet:
            typer.echo(json.dumps(_build_json_payload(result), ensure_ascii=False, indent=2))
            return

        console.print(Panel.fit(f"Processing: [bold]{result.metadata.get('video_title', '')}[/bold]", border_style="green"))
        console.print(f"Channel: {result.metadata.get('channel_name', 'Unknown')}")
        console.print(f"Database Video ID: {result.storage.video.id}")
        console.print(f"Memory ID: {result.storage.mem0_memory_id or 'n/a'}")
        console.print()
        console.print(
            Panel.fit(
                result.transcript_display,
                title="Transcript",
                border_style="blue",
            )
        )
        console.print(f"Source: {result.transcript_source}")
        console.print(f"Words: {result.transcript_word_count}")

        if result.summary_output:
            console.print()
            console.print(_build_summary_panel(result.summary_output, result.storage.keyword_tags, console=console))
            if result.storage.summary and result.storage.summary.id:
                console.print(f"Summary record ID: {result.storage.summary.id}")

    @app.command("ingest-youtube-batch")
    def ingest_youtube_batch(  # pylint: disable=too-many-arguments
        file: Optional[Path] = typer.Option(None, "--file", "-f", exists=True, help="File with one URL per line"),
        urls: Optional[str] = typer.Option(None, "--urls", help="Comma-separated list of URLs"),
        remove_timestamps: bool = typer.Option(False, "--remove-timestamps", help="Remove timestamps from transcripts"),
        summarize: bool = typer.Option(True, "--summarize/--no-summarize", help="Generate summaries"),
        tags: Optional[str] = typer.Option(None, "--tags", help="Manual tags applied to all videos"),
        summary_length: int = typer.Option(300, "--summary-length", help="Maximum words in summary"),
        force: bool = typer.Option(False, "--force", help="Re-ingest existing videos"),
        priority: int = typer.Option(0, "--priority", help="Queue priority (higher = sooner)"),
        quiet: bool = typer.Option(False, "--quiet", help="Suppress interactive output"),
    ) -> None:
        manual_tags = _parse_tags(tags)
        targets = _collect_urls(file, urls)

        if not targets:
            console.print("[red]Error:[/red] Provide URLs via --file or --urls.")
            raise typer.Exit(code=IngestExitCode.INVALID_INPUT)

        async def _enqueue_and_process() -> None:
            queue_service = get_queue_service()
            for url in targets:
                await queue_service.add_to_queue(
                    url,
                    priority=priority,
                    manual_tags=manual_tags,
                    summarize=summarize,
                    summary_length=summary_length,
                    remove_timestamps=remove_timestamps,
                    force=force,
                )
            await queue_service.process_queue()

        asyncio.run(_enqueue_and_process())

        queue_service = get_queue_service()
        status = queue_service.get_queue_status()
        items = list(queue_service.items())

        if quiet:
            payload = {
                "status": status,
                "items": [_queue_item_payload(item) for item in items],
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        _render_queue_summary(console, status, items)

    @app.command("queue-status")
    def queue_status(
        json_output: bool = typer.Option(False, "--json", help="Output queue status as JSON"),
    ) -> None:
        queue_service = get_queue_service()
        status = queue_service.get_queue_status()
        items = list(queue_service.items())

        if json_output:
            payload = {
                "status": status,
                "items": [_queue_item_payload(item) for item in items],
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        _render_queue_summary(console, status, items)

    @app.command("search")
    def search(  # pylint: disable=too-many-arguments
        query: str = typer.Argument(..., help="Search query for stored videos"),
        limit: int = typer.Option(10, "--limit", help="Maximum results to return"),
        channel: Optional[str] = typer.Option(None, "--channel", help="Filter by channel name"),
        start_date: Optional[str] = typer.Option(None, "--start-date", help="Filter publish date >= ISO timestamp"),
        end_date: Optional[str] = typer.Option(None, "--end-date", help="Filter publish date <= ISO timestamp"),
        tags: Optional[str] = typer.Option(None, "--tags", help="Filter by keyword tags"),
        json_output: bool = typer.Option(False, "--json", help="Output search results as JSON"),
    ) -> None:
        try:
            filters = SearchFilters(
                channel_name=channel,
                start_date=_parse_datetime(start_date),
                end_date=_parse_datetime(end_date),
                tags=_parse_tags(tags),
            )
        except ValueError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=IngestExitCode.INVALID_INPUT) from exc

        results = get_search_service().hybrid_search(query, limit=limit, filters=filters)

        if json_output:
            typer.echo(json.dumps([_search_result_payload(result) for result in results], ensure_ascii=False, indent=2))
            return

        _render_search_results(console, results)

    @app.command("show-summary")
    def show_summary(  # pylint: disable=too-many-arguments
        summary_id: UUID = typer.Argument(..., help="Summary record UUID"),
        json_output: bool = typer.Option(False, "--json", help="Output summary as JSON"),
    ) -> None:
        try:
            summary = get_summary_repository().get_by_id(summary_id)
        except RecordNotFoundError:
            console.print(f"[red]Summary not found:[/red] {summary_id}")
            raise typer.Exit(code=IngestExitCode.INVALID_INPUT) from None

        if json_output:
            typer.echo(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return

        video = None
        try:
            video = get_video_repository().get_by_id(summary.video_id)
        except RecordNotFoundError:
            video = None

        console.print(Panel.fit(f"Summary ID: {summary_id}", border_style="magenta"))
        if video is not None:
            console.print(f"[bold]Video:[/bold] {video.video_title} ({video.video_url})")
        console.print(f"[bold]Transcript ID:[/bold] {summary.transcript_id}")
        if summary.created_at:
            console.print(f"[bold]Created:[/bold] {summary.created_at.isoformat()}")
        if summary.model_name:
            console.print(f"[bold]Model:[/bold] {summary.model_name}")
        if summary.mem0_memory_id:
            console.print(f"[bold]Mem0 Memory ID:[/bold] {summary.mem0_memory_id}")

        summary_output = SummaryOutput(
            summary_text=summary.summary_text,
            topics=summary.identified_topics,
            speakers=summary.identified_speakers,
            key_takeaways=summary.key_takeaways,
        )
        console.print()
        console.print(_build_summary_panel(summary_output, summary.keyword_tags, console=console))

    @app.command("show-transcript")
    def show_transcript(
        transcript_id: UUID = typer.Argument(..., help="Transcript record UUID"),
        json_output: bool = typer.Option(False, "--json", help="Output transcript as JSON"),
        raw: bool = typer.Option(
            False,
            "--raw",
            help="Include raw transcript segments in addition to the cleaned transcript",
        ),
    ) -> None:
        try:
            transcript = get_transcript_repository().get_by_id(transcript_id)
        except RecordNotFoundError:
            console.print(f"[red]Transcript not found:[/red] {transcript_id}")
            raise typer.Exit(code=IngestExitCode.INVALID_INPUT) from None

        if json_output:
            typer.echo(json.dumps(transcript.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return

        video = None
        try:
            if transcript.video_id is not None:
                video = get_video_repository().get_by_id(transcript.video_id)
        except RecordNotFoundError:
            video = None

        console.print(Panel.fit(f"Transcript ID: {transcript_id}", border_style="cyan"))
        if video is not None:
            console.print(f"[bold]Video:[/bold] {video.video_title} ({video.video_url})")
        console.print(f"[bold]Source:[/bold] {transcript.transcript_source.value}")
        console.print(f"[bold]Word count:[/bold] {transcript.word_count}")
        if transcript.created_at:
            console.print(f"[bold]Created:[/bold] {transcript.created_at.isoformat()}")

        console.print()
        console.print(
            Panel.fit(
                transcript.cleaned_transcript or "<empty transcript>",
                title="Cleaned Transcript",
                border_style="blue",
            )
        )

        if raw:
            raw_segments = transcript.raw_transcript_json or []
            segment_payload: list[dict[str, object]] = []
            for segment in raw_segments:
                if hasattr(segment, "model_dump"):
                    segment_payload.append(segment.model_dump(mode="json"))
                elif isinstance(segment, Mapping):
                    segment_payload.append({str(key): value for key, value in segment.items()})
                else:
                    segment_payload.append({"value": str(segment)})
            console.print()
            console.print(
                Panel.fit(
                    json.dumps(segment_payload, ensure_ascii=False, indent=2),
                    title="Raw Segments",
                    border_style="yellow",
                )
            )


def _progress_handler_factory(
    progress: Progress,
    task_id: TaskID,
    stage_ranges: StageRanges,
) -> Callable[[ProgressUpdate], None]:
    def handler(update: ProgressUpdate) -> None:
        start, end = stage_ranges.get(update.stage, (0, 100))
        span = max(end - start, 1)
        overall = start + (update.stage_progress / 100) * span
        progress.update(
            task_id,
            completed=min(overall, 100),
            description=f"{update.stage.value.title()}...",
        )

    return handler


def _format_segments(segments: Optional[Iterable[object]]) -> str:
    if not segments:
        return ""
    lines = []
    for segment in segments:
        if hasattr(segment, "start") and hasattr(segment, "text"):
            start = getattr(segment, "start", 0.0)
            text = getattr(segment, "text", "")
            lines.append(f"[{float(start):>6.2f}] {text}")
        else:
            lines.append(str(segment))
    return "\n".join(lines)


def _parse_tags(raw_tags: Optional[str]) -> list[str]:
    if not raw_tags:
        return []
    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]


def _build_summary_panel(summary: SummaryOutput, tags: Sequence[str], *, console: Optional[Console] = None) -> Panel:
    grid = Table.grid(padding=(0, 1))
    grid.add_column()

    encoding = getattr(console, "encoding", None) if console else None

    grid.add_row(_ensure_printable(summary.summary_text.strip(), encoding))

    if summary.topics:
        topics = ", ".join(_ensure_printable(topic, encoding) for topic in summary.topics)
        grid.add_row(f"[bold]Topics:[/bold] {topics}")

    if summary.speakers:
        speakers = ", ".join(_ensure_printable(speaker, encoding) for speaker in summary.speakers)
        grid.add_row(f"[bold]Speakers:[/bold] {speakers}")

    if summary.key_takeaways:
        grid.add_row("[bold]Key Takeaways:[/bold]")
        for takeaway in summary.key_takeaways:
            grid.add_row(f"- {_ensure_printable(takeaway, encoding)}")

    if tags:
        safe_tags = ", ".join(_ensure_printable(tag, encoding) for tag in tags)
        grid.add_row(f"[bold]Keywords:[/bold] {safe_tags}")

    return Panel.fit(grid, title="Summary", border_style="magenta")


def _ensure_printable(text: str, encoding: Optional[str]) -> str:
    if not text:
        return text

    normalized = unicodedata.normalize("NFKC", text).translate(_WINDOWS_CHAR_REPLACEMENTS)
    if not encoding:
        return normalized

    try:
        normalized.encode(encoding)
        return normalized
    except (UnicodeEncodeError, LookupError):
        try:
            return normalized.encode(encoding, errors="replace").decode(encoding, errors="replace")
        except Exception:  # pragma: no cover - defensive fallback
            return normalized.encode("ascii", errors="replace").decode("ascii", errors="replace")


def _build_json_payload(result: IngestionResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "success",
        "video": {
            "url": result.metadata.get("video_url"),
            "title": result.metadata.get("video_title"),
            "channel": result.metadata.get("channel_name"),
            "duration": result.metadata.get("duration_seconds"),
            "database_id": str(result.storage.video.id) if result.storage.video.id else None,
        },
        "transcript": {
            "word_count": result.transcript_word_count,
            "source": result.transcript_source,
            "database_id": str(result.storage.transcript.id) if result.storage.transcript.id else None,
        },
        "storage": {
            "memory_id": result.storage.mem0_memory_id,
            "keyword_tags": result.storage.keyword_tags,
        },
    }

    if result.summary_output:
        payload["summary"] = {
            "summary_text": result.summary_output.summary_text,
            "word_count": len(result.summary_output.summary_text.split()),
            "topics": result.summary_output.topics,
            "speakers": result.summary_output.speakers,
            "key_takeaways": result.summary_output.key_takeaways,
            "database_id": (
                str(result.storage.summary.id) if result.storage.summary and result.storage.summary.id else None
            ),
        }

    return payload


def _collect_urls(file_path: Optional[Path], inline_urls: Optional[str]) -> list[str]:
    urls: list[str] = []
    if file_path:
        urls.extend(line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if inline_urls:
        urls.extend(url.strip() for url in inline_urls.split(",") if url.strip())
    return urls


def _queue_item_payload(item: QueueItem) -> dict[str, object]:
    return {
        "url": str(item.video_url),
        "status": item.status.value,
        "priority": item.priority,
        "current_stage": item.current_stage.value if item.current_stage else None,
        "overall_progress_percent": item.overall_progress_percent,
        "message": item.message,
        "error": item.error_message,
        "queued_at": item.queued_at.isoformat(),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def _render_queue_summary(console: Console, status: Mapping[str, int], items: Iterable[QueueItem]) -> None:
    table = Table(title="Queue Status", show_lines=False)
    table.add_column("URL", overflow="fold")
    table.add_column("Status")
    table.add_column("Stage")
    table.add_column("Progress")
    table.add_column("Message")

    for item in items:
        table.add_row(
            str(item.video_url),
            item.status.value,
            item.current_stage.value if item.current_stage else "-",
            f"{item.overall_progress_percent}%",
            item.message or "",
        )

    console.print(table)
    console.print(
        f"Queued: {status['queued']} | Processing: {status['processing']} | "
        f"Completed: {status['completed']} | Failed: {status['failed']}"
    )


def _render_search_results(console: Console, results: Sequence[SearchResult]) -> None:
    table = Table(title="Search Results")
    table.add_column("Title", overflow="fold")
    table.add_column("Channel")
    table.add_column("Published")
    table.add_column("Hybrid Score")
    table.add_column("Memory ID")
    table.add_column("IDs", overflow="fold")

    for result in results:
        published = result.publish_date.isoformat() if result.publish_date else "unknown"
        id_lines = [
            f"Video: {result.video_id}" if result.video_id else "Video: n/a",
            f"Summary: {result.summary_id}" if result.summary_id else "Summary: n/a",
            f"Transcript: {result.transcript_id}" if result.transcript_id else "Transcript: n/a",
        ]
        table.add_row(
            result.video_title or "<unknown>",
            result.channel_name or "<unknown>",
            published,
            f"{result.hybrid_score:.3f}",
            result.mem0_memory_id or "n/a",
            "\n".join(id_lines),
        )

    console.print(table)
    console.print(
        "\nTip: run `sage show-summary <SUMMARY_ID>` or `sage show-transcript <TRANSCRIPT_ID>` to view stored content."
    )


def _search_result_payload(result: SearchResult) -> dict[str, object]:
    return {
        "video_id": str(result.video_id) if result.video_id else None,
        "video_url": result.video_url,
        "video_title": result.video_title,
        "channel_name": result.channel_name,
        "publish_date": result.publish_date.isoformat() if result.publish_date else None,
        "summary_text": result.summary_text,
        "keyword_tags": result.keyword_tags,
        "keyword_score": result.keyword_score,
        "semantic_score": result.semantic_score,
        "hybrid_score": result.hybrid_score,
        "memory_id": result.mem0_memory_id,
        "summary_id": str(result.summary_id) if result.summary_id else None,
        "transcript_id": str(result.transcript_id) if result.transcript_id else None,
    }


def _parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:  # pragma: no cover - user input validation
        raise ValueError(f"Invalid ISO datetime: {raw}") from exc

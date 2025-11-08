"""Transcript acquisition service with fallback strategies."""

from __future__ import annotations

import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import yt_dlp
from rich.console import Console
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable

from sage.config.settings import Settings, get_settings
from sage.models.transcript import Transcript, TranscriptSegment, TranscriptSource
from sage.utils.progress import ProcessingStage, ProgressUpdate
from sage.utils.validation import extract_video_id


FallbackHandler = Callable[[str], Transcript]
CAPTION_RETRY_ATTEMPTS = 3
CAPTION_RETRY_BACKOFF_SECONDS = 1.5

try:  # pragma: no cover - optional dependency heavy to load in tests
    import torch  # type: ignore
    import whisperx  # type: ignore
except ImportError:  # pragma: no cover
    torch = None
    whisperx = None


class TranscriptService:
    """Service responsible for fetching and cleaning YouTube transcripts."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        console: Optional[Console] = None,
        fallback_handler: Optional[FallbackHandler] = None,
        caption_retry_attempts: Optional[int] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._console = console or Console()
        self._fallback_handler = fallback_handler or self._transcribe_with_whisper
        self._caption_attempts = max(1, caption_retry_attempts or CAPTION_RETRY_ATTEMPTS)
        self._transcript_api = YouTubeTranscriptApi()

    def get_transcript_from_captions(self, video_id: str) -> Transcript:
        """Fetch the transcript directly from YouTube captions.

        Parameters
        ----------
        video_id:
            The canonical 11-character YouTube video identifier.

        Returns
        -------
        Transcript
            A transcript populated with raw segments and cleaned text derived from captions.

        Raises
        ------
        youtube_transcript_api._errors.TranscriptsDisabled
            If captions are disabled for the requested video.
        youtube_transcript_api._errors.VideoUnavailable
            If the video cannot be accessed (removed, private, geo-restricted, etc.).
        """

        self._console.log("Fetching transcript from YouTube captions")
        attempt = 0
        fetched_transcript = None
        last_error: Optional[Exception] = None
        while attempt < self._caption_attempts:
            attempt += 1
            try:
                fetched_transcript = self._transcript_api.fetch(video_id, languages=("en",))
                break
            except (VideoUnavailable, TranscriptsDisabled):
                raise
            except Exception as exc:  # pragma: no cover - network issues
                last_error = exc
                if attempt >= self._caption_attempts:
                    self._console.log(
                        f"[red]Caption fetch failed after {attempt} attempts:[/red] {exc} (video_id={video_id})"
                    )
                    raise
                delay = min(CAPTION_RETRY_BACKOFF_SECONDS * attempt, 10.0)
                self._console.log(
                    f"[yellow]Caption fetch attempt {attempt} failed:[/yellow] {exc}; "
                    f"retrying in {delay:.1f}s (video_id={video_id})"
                )
                time.sleep(delay)
        else:
            raise RuntimeError("Caption fetch exhausted retries without raising an explicit error.") from last_error

        if fetched_transcript is None:
            raise RuntimeError("Caption fetch failed without returning transcript data.") from last_error

        captions = fetched_transcript.to_raw_data()
        segments: List[TranscriptSegment] = [
            TranscriptSegment(start=float(segment["start"]), duration=float(segment["duration"]), text=segment["text"])
            for segment in captions
        ]
        cleaned_text = self.clean_transcript(segments)
        return Transcript(
            raw_transcript_json=segments,
            cleaned_transcript=cleaned_text,
            word_count=self._word_count(cleaned_text),
            transcript_source=TranscriptSource.YOUTUBE_CAPTIONS,
        )

    def _download_video(self, video_id: str, destination: Path) -> Path:
        """Download the audio track for Whisper processing via ``yt-dlp``.

        Parameters
        ----------
        video_id:
            YouTube identifier for the target video.
        destination:
            Temporary directory where the audio artefact should be saved.

        Returns
        -------
        Path
            Absolute path to the downloaded audio file.

        Raises
        ------
        FileNotFoundError
            If ``yt-dlp`` completes without producing an output file.
        """

        self._console.log("Downloading audio via yt-dlp")
        output_path = destination / f"{video_id}.%(ext)s"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_path),
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        downloaded_files = list(destination.glob(f"{video_id}.*"))
        if not downloaded_files:
            raise FileNotFoundError("yt-dlp failed to download audio")
        return downloaded_files[0]

    def _transcribe_with_whisper(self, video_id: str) -> Transcript:
        """Produce a transcript using Whisper when captions are unavailable.

        Parameters
        ----------
        video_id:
            YouTube identifier for the target video whose audio will be transcribed.

        Returns
        -------
        Transcript
            Transcript instance constructed from Whisper output segments.

        Raises
        ------
        RuntimeError
            If Whisper dependencies are unavailable in the current environment.
        """

        self._console.log("Falling back to Whisper transcription")
        if whisperx is None:
            raise RuntimeError("Whisper fallback requires the `whisperx` package to be installed.")

        device = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"  # type: ignore[operator]
        compute_type = "float16" if device == "cuda" else "int8"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            audio_path = self._download_video(video_id, tmp_path)
            model = whisperx.load_model("large-v2", device=device, compute_type=compute_type)
            audio = whisperx.load_audio(str(audio_path))
            result = model.transcribe(audio)

            segments: List[TranscriptSegment] = []
            for item in result.get("segments", []):
                start = float(item.get("start", 0.0))
                end = float(item.get("end", start))
                text = item.get("text", "").strip()
                if not text:
                    continue
                duration = end - start if end > start else item.get("duration", 0.0)
                duration = float(duration) if duration else 1e-3
                segments.append(TranscriptSegment(start=start, duration=duration, text=text))

        cleaned_text = self.clean_transcript(segments)
        return Transcript(
            raw_transcript_json=segments,
            cleaned_transcript=cleaned_text,
            word_count=self._word_count(cleaned_text),
            transcript_source=TranscriptSource.WHISPER_LOCAL,
        )

    def get_transcript(
        self,
        url: str,
        *,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> Transcript:
        """Obtain a transcript using captions or the configured fallback strategy.

        Parameters
        ----------
        url:
            User-provided YouTube URL.
        on_progress:
            Optional callback that receives granular progress updates.

        Returns
        -------
        Transcript
            Normalised transcript representing the fetched or transcribed content.
        """

        video_id = extract_video_id(url)
        self._emit_progress(on_progress, ProcessingStage.VALIDATING, 100, 5, f"Validated URL {url}", url)

        try:
            transcript = self.get_transcript_from_captions(video_id)
        except (VideoUnavailable, TranscriptsDisabled):
            self._emit_progress(
                on_progress,
                ProcessingStage.TRANSCRIBING,
                10,
                50,
                "Captions unavailable; using fallback",
                url,
            )
            transcript = self._fallback_handler(video_id)

        self._emit_progress(
            on_progress,
            ProcessingStage.TRANSCRIBING,
            100,
            85,
            "Transcript fetched successfully",
            url,
        )
        return transcript

    def clean_transcript(self, segments: Iterable[TranscriptSegment]) -> str:
        """Create a whitespace-normalised text representation from transcript segments.

        Parameters
        ----------
        segments:
            Iterable collection of transcript segments, typically including timestamps.

        Returns
        -------
        str
            Cleaned string suitable for keyword search and summarisation.
        """

        joined = " ".join(segment.text.strip() for segment in segments if segment.text)
        return " ".join(joined.split())

    @staticmethod
    def _word_count(text: str) -> int:
        """Return the number of whitespace-delimited tokens in ``text``."""

        return len(text.split()) if text else 0

    def extract_video_metadata(self, video_id: str) -> dict[str, object]:
        """Retrieve YouTube metadata using ``yt-dlp`` without downloading media.

        Parameters
        ----------
        video_id:
            YouTube identifier for the target video.

        Returns
        -------
        dict
            Mapping of metadata fields (title, channel, publish date, etc.).
        """

        self._console.log("Extracting YouTube metadata via yt-dlp")
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        publish_date = info.get("upload_date")
        parsed_publish_date = (
            datetime.strptime(publish_date, "%Y%m%d") if publish_date else None
        )

        return {
            "video_url": url,
            "video_id": info.get("id", video_id),
            "video_title": info.get("title", ""),
            "channel_name": info.get("uploader", ""),
            "channel_id": info.get("channel_id"),
            "publish_date": parsed_publish_date,
            "duration_seconds": info.get("duration"),
            "language": info.get("language"),
        }

    def _emit_progress(
        self,
        callback: Optional[Callable[[ProgressUpdate], None]],
        stage: ProcessingStage,
        stage_progress: int,
        overall_progress: int,
        message: str,
        video_url: str,
    ) -> None:
        """Emit a progress update to the supplied callback if one exists."""

        if callback is None:
            return
        callback(
            ProgressUpdate(
                stage=stage,
                stage_progress=stage_progress,
                overall_progress=overall_progress,
                message=message,
                video_url=video_url,
            )
        )


__all__ = ["TranscriptService"]


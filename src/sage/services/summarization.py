"""Summarization service built on top of Pydantic AI and LangGraph."""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter
from typing import Callable, Dict, List, Optional, Set, TypedDict, TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from rich.console import Console

from sage.config.settings import Settings, get_settings
from sage.models.progress import SummaryOutput
from sage.utils.progress import ProcessingStage, ProgressUpdate

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

try:  # pragma: no cover - optional anthropic provider
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
except ImportError:  # pragma: no cover - optional anthropic provider
    AnthropicModel = None  # type: ignore[assignment]

try:  # pragma: no cover - optional instrumentation dependency
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - optional instrumentation dependency
    Langfuse = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from langfuse import Langfuse as LangfuseClient
else:  # pragma: no cover - runtime fallback
    LangfuseClient = object  # type: ignore[misc, assignment]

from sage import __version__ as sage_version

DEFAULT_MODEL_NAME = "gpt-5-nano"
MAX_TRANSCRIPT_CHARS = 20_000
MAX_BACKOFF_SECONDS = 10.0
BASE_BACKOFF_SECONDS = 2.0


class SummarizationError(RuntimeError):
    """Raised when the summarization pipeline fails after retries."""


class SummarizationState(TypedDict, total=False):
    """Workflow state propagated through the LangGraph pipeline."""

    transcript: str
    max_words: int
    attempt: int
    summary: Optional[SummaryOutput]
    error: Optional[str]


class SummarizationService:
    """Generate structured summaries with retry and tracing support."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        console: Optional[Console] = None,
        model_name: str = DEFAULT_MODEL_NAME,
        max_attempts: int = 3,
    ) -> None:
        self._settings = settings or get_settings()
        self._console = console or Console()
        self._model_name = model_name
        self._max_attempts = max(1, max_attempts)
        self._progress_callback: Optional[Callable[[ProgressUpdate], None]] = None
        self._metadata: Dict[str, object] = {}
        self._agent = self._create_agent()
        self._langfuse: Optional[LangfuseClient] = self._create_langfuse()
        self._workflow = self._build_workflow()

    async def summarize(
        self,
        transcript_text: str,
        *,
        max_words: Optional[int] = None,
        metadata: Optional[Dict[str, object]] = None,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None,
    ) -> SummaryOutput:
        """Execute the summarisation workflow for a transcript.

        Parameters
        ----------
        transcript_text:
            Raw transcript text that should be summarised.
        max_words:
            Optional override for the maximum allowed words in the summary output.
        metadata:
            Additional contextual metadata forwarded to prompts and tracing systems.
        on_progress:
            Optional callback invoked with progress updates during summarisation.

        Returns
        -------
        SummaryOutput
            Structured summary containing summary text, topics, speakers, and takeaways.

        Raises
        ------
        SummarizationError
            If summarisation fails after exhausting retries or credentials are missing.
        """
        if not transcript_text.strip():
            raise SummarizationError("Transcript is empty; nothing to summarize.")

        self._metadata = metadata or {}
        self._progress_callback = on_progress

        self._emit_progress(ProcessingStage.SUMMARIZING, 5, "Preparing summarization request")

        state: SummarizationState = {
            "transcript": transcript_text,
            "max_words": max_words or int(self._settings.max_summary_words),
            "attempt": 0,
            "summary": None,
            "error": None,
        }

        try:
            final_state = await self._workflow.ainvoke(state)
        finally:
            self._progress_callback = None
            self._metadata = {}

        summary = final_state.get("summary")
        if summary is None:
            error_message = final_state.get("error") or "Summarization failed"
            raise SummarizationError(error_message)

        self._emit_progress(ProcessingStage.SUMMARIZING, 100, "Summary generated")
        return summary

    def extract_keywords(
        self,
        summary_output: SummaryOutput,
        transcript_text: str,
        *,
        limit: int = 10,
    ) -> List[str]:
        """Derive a deduplicated list of keyword tags from summary outputs and transcript context.

        Parameters
        ----------
        summary_output:
            Structured summary payload produced by :meth:`summarize`.
        transcript_text:
            Original transcript text used to calculate frequency-based fallback keywords.
        limit:
            Maximum number of keywords to return.

        Returns
        -------
        list[str]
            Ordered list of lowercase keyword terms.
        """
        curated: Set[str] = {
            topic.strip() for topic in summary_output.topics if topic.strip()
        }
        curated.update({speaker.strip() for speaker in summary_output.speakers if speaker.strip()})
        curated.update({takeaway.strip() for takeaway in summary_output.key_takeaways if takeaway.strip()})

        normalized: List[str] = []
        for item in curated:
            cleaned = item.lower()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= limit:
                return normalized[:limit]

        tokens = self._tokenize(transcript_text)
        frequencies = Counter(tokens)
        for term, _ in frequencies.most_common(limit * 2):
            if term not in normalized:
                normalized.append(term)
            if len(normalized) >= limit:
                break

        return normalized[:limit]

    @property
    def model_name(self) -> str:
        """Return the configured model identifier."""

        return self._model_name

    @property
    def system_prompt(self) -> str:
        """Expose the system prompt used for summarization requests."""

        return self._system_prompt()

    def _build_workflow(self) -> object:
        """Construct the LangGraph workflow that orchestrates summarisation retries."""

        graph = StateGraph(SummarizationState)
        graph.add_node("summarize", self._summarize_node)
        graph.add_node("backoff", self._backoff_node)
        graph.add_edge(START, "summarize")
        graph.add_conditional_edges(
            "summarize",
            self._route_post_summary,
            {
                "complete": END,
                "retry": "backoff",
                "fail": END,
            },
        )
        graph.add_edge("backoff", "summarize")
        return graph.compile()

    async def _summarize_node(self, state: SummarizationState) -> SummarizationState:
        """Invoke the LLM agent and capture success or failure outcomes."""

        attempt = state.get("attempt", 0) + 1
        prompt = self._build_summarization_prompt(
            state["transcript"],
            max_words=state["max_words"],
        )

        self._emit_progress(
            ProcessingStage.SUMMARIZING,
            self._progress_for_attempt(attempt),
            f"Generating summary (attempt {attempt}/{self._max_attempts})",
        )

        trace = self._start_trace(attempt, prompt)
        start_time = time.perf_counter()
        try:
            result = await self._agent.run(prompt)
            summary = result.output
            duration_seconds = time.perf_counter() - start_time
            self._record_trace_success(trace, summary, duration_seconds)
            self._log_success(summary, duration_seconds)
            return {
                "attempt": attempt,
                "summary": summary,
                "error": None,
            }
        except Exception as exc:  # pragma: no cover - defensive fallback
            duration_seconds = time.perf_counter() - start_time
            error_message = str(exc)
            self._record_trace_failure(trace, error_message, duration_seconds)
            self._log_failure(error_message, duration_seconds)
            return {
                "attempt": attempt,
                "summary": None,
                "error": error_message,
            }

    async def _backoff_node(self, state: SummarizationState) -> SummarizationState:
        """Sleep for an exponentially increasing duration before retrying."""

        attempt = state.get("attempt", 1)
        delay = min(BASE_BACKOFF_SECONDS * math.pow(2, attempt - 1), MAX_BACKOFF_SECONDS)
        self._emit_progress(
            ProcessingStage.SUMMARIZING,
            self._progress_for_attempt(attempt),
            f"Retrying summarization in {delay:.1f}s",
        )
        await asyncio.sleep(delay)
        return {}

    def _route_post_summary(self, state: SummarizationState) -> str:
        """Determine the next workflow edge based on summarisation outcome."""

        if state.get("summary") is not None:
            return "complete"
        if state.get("attempt", 0) >= self._max_attempts:
            return "fail"
        return "retry"

    def _create_agent(self) -> Agent[SummaryOutput]:
        """Instantiate the Pydantic AI agent using available provider credentials."""

        openai_key = (
            self._settings.openai_api_key.get_secret_value()
            if self._settings.openai_api_key is not None
            else None
        )
        anthropic_key = (
            self._settings.anthropic_api_key.get_secret_value()
            if self._settings.anthropic_api_key is not None
            else None
        )

        if openai_key:
            provider = OpenAIProvider(api_key=openai_key)
            model = OpenAIChatModel(self._model_name, provider=provider)
        elif anthropic_key:
            if AnthropicModel is None:
                raise SummarizationError("Anthropic support is unavailable. Install anthropic extras or provide an OpenAI API key.")
            provider = AnthropicProvider(api_key=anthropic_key)
            model = AnthropicModel(self._model_name, provider=provider)
        else:
            raise SummarizationError(
                "No language model credentials configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )

        return Agent(model=model, output_type=SummaryOutput, system_prompt=self._system_prompt())

    def _create_langfuse(self) -> Optional[LangfuseClient]:
        """Initialise Langfuse tracing if the dependency and credentials are available."""

        if Langfuse is None:
            return None
        if self._settings.langfuse_public_key is None or self._settings.langfuse_secret_key is None:
            return None

        kwargs: Dict[str, str] = {
            "public_key": self._settings.langfuse_public_key.get_secret_value(),
            "secret_key": self._settings.langfuse_secret_key.get_secret_value(),
        }
        if self._settings.langfuse_host is not None:
            kwargs["host"] = str(self._settings.langfuse_host)

        try:
            return Langfuse(**kwargs)  # type: ignore[call-arg]
        except Exception as exc:  # pragma: no cover - instrumentation failures are non-fatal
            self._console.log(f"LangFuse initialization failed: {exc}")
            return None

    def _system_prompt(self) -> str:
        """Return the reusable system prompt guiding summarisation behaviour."""

        return (
            "You are Sage's research summarizer. Produce concise, structured summaries capturing topics, "
            "speakers, and key takeaways. Maintain factual accuracy and an objective tone."
        )

    def _start_trace(self, attempt: int, prompt: str) -> Optional[object]:
        """Open a Langfuse trace span for the current summarisation attempt, if supported."""

        if self._langfuse is None:
            return None
        trace_callable = getattr(self._langfuse, "trace", None)
        if not callable(trace_callable):
            return None

        metadata: Dict[str, str] = {
            key: str(value) for key, value in self._metadata.items()
        }
        metadata.update(
            {
                "attempt": str(attempt),
                "model": self._model_name,
                "version": sage_version,
            }
        )

        try:
            return trace_callable(
                name="summarization",
                input={"prompt": prompt},
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - instrumentation failures are non-fatal
            self._console.log(f"LangFuse trace creation failed: {exc}")
            return None

    def _record_trace_success(
        self,
        trace: Optional[object],
        summary: SummaryOutput,
        duration_seconds: float,
    ) -> None:
        """Record a successful summarisation attempt with Langfuse instrumentation."""

        if trace is None:
            return
        end_callable = getattr(trace, "end", None)
        if not callable(end_callable):
            return

        payload = summary.model_dump(mode="json")
        metadata = {
            "duration_seconds": duration_seconds,
            "word_count": len(summary.summary_text.split()),
            "model": self._model_name,
        }

        try:
            end_callable(output=payload, status="success", metadata=metadata)
        except Exception as exc:  # pragma: no cover - instrumentation failures are non-fatal
            self._console.log(f"LangFuse trace completion failed: {exc}")

    def _record_trace_failure(
        self,
        trace: Optional[object],
        error_message: str,
        duration_seconds: float,
    ) -> None:
        """Record a failed summarisation attempt with Langfuse instrumentation."""

        if trace is None:
            return
        end_callable = getattr(trace, "end", None)
        if not callable(end_callable):
            return

        metadata = {
            "duration_seconds": duration_seconds,
            "model": self._model_name,
        }

        try:
            end_callable(output={"error": error_message}, status="error", metadata=metadata)
        except Exception as exc:  # pragma: no cover - instrumentation failures are non-fatal
            self._console.log(f"LangFuse trace completion failed: {exc}")

    def _build_summarization_prompt(self, transcript_text: str, *, max_words: int) -> str:
        """Compose the prompt fed into the language model for summarisation."""

        header_lines = [
            "You are an expert research assistant producing concise, structured summaries.",
            "Follow the output schema exactly and keep the tone objective.",
            f"Limit the summary_text field to at most {max_words} words.",
        ]

        if self._metadata:
            header_lines.append("Context:")
            for key, value in self._metadata.items():
                value_str = value if isinstance(value, str) else str(value)
                header_lines.append(f"- {key.replace('_', ' ').title()}: {value_str}")

        truncated_transcript = transcript_text[:MAX_TRANSCRIPT_CHARS]
        if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
            truncated_transcript += "\n...[truncated]"

        instructions = "\n".join(header_lines)

        return (
            f"{instructions}\n\n"
            "Return JSON that matches the SummaryOutput model with fields: \n"
            "- summary_text (string)\n"
            "- topics (list of short topic strings)\n"
            "- speakers (list of speaker names if mentioned, otherwise empty)\n"
            "- key_takeaways (list of concise bullet strings)\n\n"
            "Transcript:\n"
            f"{truncated_transcript}"
        )

    def _progress_for_attempt(self, attempt: int) -> int:
        """Calculate a stage progress percentage based on retry attempt count."""

        fraction = min(attempt, self._max_attempts) / self._max_attempts
        return max(10, min(95, int(fraction * 100)))

    def _emit_progress(self, stage: ProcessingStage, stage_progress: int, message: str) -> None:
        """Safely invoke the progress callback if one has been registered."""

        if self._progress_callback is None:
            return
        self._progress_callback(
            ProgressUpdate(
                stage=stage,
                stage_progress=stage_progress,
                overall_progress=stage_progress,
                message=message,
                video_url=str(self._metadata.get("video_url", "")),
            )
        )

    def _log_success(self, summary: SummaryOutput, duration_seconds: float) -> None:
        """Log a successful summarisation attempt with timing information."""

        words = len(summary.summary_text.split())
        self._console.log(
            "Summarization succeeded "
            f"(duration={duration_seconds:.2f}s, words={words})"
        )

    def _log_failure(self, error_message: str, duration_seconds: float) -> None:
        """Emit a log entry describing a failed summarisation attempt."""

        self._console.log(
            "Summarization attempt failed "
            f"(duration={duration_seconds:.2f}s, error='{error_message}')"
        )

    def _tokenize(self, text: str) -> List[str]:
        """Split text into filtered tokens used for fallback keyword extraction."""

        stopwords = self._stopwords()
        matches = re.findall(r"[A-Za-z][A-Za-z0-9\-']+", text.lower())
        return [token for token in matches if token not in stopwords and len(token) > 3]

    def _stopwords(self) -> Set[str]:
        """Return the minimal stopword list used by :meth:`_tokenize`."""

        return {
            "the",
            "and",
            "that",
            "with",
            "from",
            "this",
            "have",
            "will",
            "your",
            "into",
            "there",
            "their",
            "about",
            "which",
            "when",
            "where",
            "while",
            "after",
            "before",
            "because",
            "these",
            "those",
            "would",
            "could",
            "should",
            "might",
            "being",
            "video",
            "transcript",
        }


__all__ = ["SummarizationService", "SummarizationError"]



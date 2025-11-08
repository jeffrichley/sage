# Implementation Plan: YouTube Transcript & Memory Ingestion Pipeline

**Branch**: `001-youtube-ingestion` | **Date**: 2025-11-07 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-youtube-ingestion/spec.md`

## Summary

Build a CLI-based YouTube ingestion pipeline that retrieves or generates transcripts (with timestamps kept by default) from YouTube videos, generates AI-powered summaries (enabled by default), and stores both in Sage's Postgres database for downstream querying. Structured data lives in relational tables, while summary embeddings are persisted in a pgvector column to support semantic retrieval. The system prioritizes research workflows with features like progress tracking (via callbacks), batch processing (in-memory queue), and conservative rate limiting (YAML config). Implementation uses Typer CLI framework, youtube-transcript-api with WhisperX fallback, Pydantic AI + LangGraph for summarization, and Postgres + pgvector for storage and search.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: 
- CLI: Typer (structured CLI framework)
- Transcript: youtube-transcript-api (primary), yt-dlp + WhisperX/WhisperFast (fallback)
- Summarization: Pydantic AI + LangGraph
- Storage & search: Postgres (JSON/array columns + full-text search) with pgvector for semantic queries
- Observability: LangFuse (run metrics, costs, latency)
- Logging: rich (colored terminal output per constitution)
- Testing: pytest with explicit markers

**Storage**: PostgreSQL for structured data (youtube_videos, transcripts, summaries) with full-text indexes and pgvector-based embeddings for semantic search

**Testing**: pytest with markers (unit, integration, contract), run via `just test` per constitution

**Target Platform**: Local development (macOS/Linux/Windows), Docker containerized deployment

**Project Type**: single (CLI application)

**Performance Goals**: 
- Process typical 30-60 minute video within 5 minutes
- Support 1000+ stored video entries without degradation
- Search queries return results in < 2 seconds
- Batch processing with conservative rate limit throttling

**Constraints**: 
- English-only transcription (initial release)
- Public YouTube videos only (no authentication)
- Conservative rate limiting to maintain good API standing
- Text-only storage (no video file retention)
- Asynchronous processing with progress callbacks

**Scale/Scope**: 
- Initial: Single-user researcher (Jeff)
- Storage: 1000+ video entries (text: transcripts + summaries)
- Batch: Queue-based processing with automatic throttling
- Search: Postgres full-text search plus pgvector for semantic retrieval

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify alignment with the Sage Constitution (`.specify/memory/constitution.md`):

### Principle I: Consistency & Predictability
- [x] Follows established directory layout conventions (specs/, src/sage/, tests/)
- [x] Uses consistent naming patterns (CLI commands, modules, database schemas)
- [x] Adheres to project typing and testing conventions (strict mypy, explicit pytest markers)

### Principle II: Clarity over Cleverness
- [x] Code design prioritizes readability (Typer CLI, clear service boundaries)
- [x] Modular boundaries are clear (CLI layer, transcript service, summarization service, storage service)
- [x] Type annotations are thorough (avoiding `Any` types per constitution)
- [x] Docstrings explain intent (research-oriented documentation)

### Principle III: Incremental Safety
- [x] Feature can be implemented without breaking existing functionality (new sage command)
- [x] Test strategy is defined (unit tests per service, integration for pipeline, contract for CLI interface)
- [x] Rollback strategy: Feature behind CLI subcommand, no breaking changes to existing code
- [x] Validation checkpoints: P1 (transcript), P2 (summary), P3 (storage) can each be validated independently

### Principle IV: Stack-Adherence
- [x] Uses approved tech stack (Python/uv, rich logging, just test commands)
- [x] Configuration follows Pydantic models pattern (config/settings.py with environment overrides)
- [x] Dependencies managed via pyproject.toml with explicit versions
- [x] HPC/cluster compatibility: N/A for initial CLI (local/Docker deployment)

### Principle V: Research-Engineering Bridge
- [x] Reproducibility strategy: LangFuse tracks all runs, configs, prompts; database stores all metadata
- [x] Instrumentation: Progress callbacks, LangFuse metrics, rich logging for observability
- [x] Experiment tracking: Each ingestion logged with timestamps, costs, success/failure rates
- [x] Research-relevant validation: Transcript accuracy, summary quality, search recall metrics

### Principle VI: Efficiency with Discipline
- [x] Minimal boilerplate (Typer handles CLI parsing, Postgres keeps storage/search co-located, LangGraph manages agent flow)
- [x] Integrates with uv task-runner (dependencies installed via `uv sync`)
- [x] CLI interface with rich progress bars for researcher feedback
- [x] Fast iteration: Each priority (P1/P2/P3) delivers independent value

### Cross-Cutting Concerns
- [x] Error handling: Comprehensive try/catch with rich error messages, retry logic for transient failures
- [x] Logging uses rich library for colored output per constitution
- [x] Technical debt: None anticipated; stack choices are well-established
- [x] Tests use explicit decorators (`pytest.mark.unit`, `pytest.mark.integration`)
- [x] Tests never disable warnings (per constitution)

**Constitution Status**: ✅ **PASSED** - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/001-youtube-ingestion/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Technology decisions and rationale
├── data-model.md        # Phase 1: Database schema and entities
├── quickstart.md        # Phase 1: Getting started guide
├── contracts/           # Phase 1: CLI command contracts
│   └── cli-commands.md  # Typer CLI interface specification
└── checklists/
    └── requirements.md  # Spec quality validation
```

### Source Code (repository root)

```text
src/sage/
├── __init__.py                      # Version and package exports
├── cli/
│   ├── __init__.py
│   ├── main.py                      # Typer app entry point
│   └── ingest_youtube.py            # YouTube ingestion command
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic settings (env vars, API keys)
├── services/
│   ├── __init__.py
│   ├── transcript.py                # Transcript retrieval (youtube-transcript-api + WhisperX)
│   ├── summarization.py             # Pydantic AI + LangGraph summarization
│   ├── storage.py                   # Postgres persistence layer
│   └── queue.py                     # Batch processing queue with rate limiting
├── models/
│   ├── __init__.py
│   ├── video.py                     # YouTube Video Entry model
│   ├── transcript.py                # Transcript model
│   ├── summary.py                   # Summary model (includes topics/tags arrays)
└── utils/
    ├── __init__.py
    ├── progress.py                  # Callback-based progress tracking
    └── validation.py                # URL validation, error handling

tests/
├── __init__.py
├── conftest.py                      # Shared fixtures
├── unit/
│   ├── test_transcript_service.py
│   ├── test_summarization_service.py
│   ├── test_storage_service.py
│   └── test_queue_service.py
├── integration/
│   ├── test_full_pipeline.py       # End-to-end: URL → storage
│   └── test_batch_processing.py    # Multiple videos with rate limiting
└── contract/
    └── test_cli_commands.py         # Typer CLI interface validation
```

**Structure Decision**: Single project structure selected because this is a CLI application focused on a specific ingestion pipeline. All code lives under `src/sage/` as the top-level package. Clean separation between CLI layer (`cli/`), business logic (`services/`), data models (`models/`), and configuration (`config/`). This structure supports the phased rollout: P1 (transcript service + CLI), P2 (summarization service), P3 (storage service + queue).

## Complexity Tracking

> **No constitution violations to justify**

All technical choices align with constitution principles and research engineering best practices.

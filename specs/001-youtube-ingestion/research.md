# Research & Technology Decisions: YouTube Transcript & Memory Ingestion

**Feature**: 001-youtube-ingestion  
**Date**: 2025-11-07  
**Status**: Complete

## Overview

This document captures technology research, decisions, and rationale for the YouTube transcript ingestion pipeline. All decisions align with the Sage Constitution's principles of Stack-Adherence, Clarity over Cleverness, and Research-Engineering Bridge.

---

## 1. CLI Framework

### Decision: **Typer**

**Rationale**:
- Type-safe CLI interface with automatic help generation from Python type hints
- Excellent developer experience with minimal boilerplate
- Natural fit for Python-first research toolkit
- Supports subcommands for future Sage modules (ingest-paper, summarize-notes, etc.)
- Built on Click (battle-tested, widely used)
- Integrates seamlessly with rich for progress bars and colored output

**Alternatives Considered**:
- **Click**: Lower-level, more boilerplate required, Typer built on top of it anyway
- **argparse**: Standard library but verbose, no type safety, poor DX
- **fire**: Too magical, less explicit control over interface

**Constitution Alignment**: Efficiency with Discipline (minimal boilerplate), Clarity (type-safe)

---

## 2. Transcript Retrieval

### Decision: **Dual Strategy - youtube-transcript-api (primary) + yt-dlp + WhisperX (fallback)**

**Rationale**:

**Primary: youtube-transcript-api**
- Fast, no download required - uses YouTube's built-in captions API
- Preserves timestamps for deep-linking (requirement from spec clarifications)
- Zero GPU requirements for most videos
- Handles multi-language detection automatically
- Minimal rate limit concerns (read-only API)

**Fallback: yt-dlp + WhisperX/WhisperFast**
- Handles videos without captions
- yt-dlp: Robust YouTube downloader, handles formats, extracts metadata
- WhisperX: Faster than base Whisper, better timestamp alignment
- WhisperFast: Alternative for GPU acceleration
- Provides confidence scores for quality assessment

**Alternatives Considered**:
- **Always use Whisper**: Slower, requires GPU, unnecessary when captions exist
- **OpenAI Whisper API**: Costs money per minute, external dependency, rate limits
- **Assembly AI / Rev.ai**: Commercial services, ongoing costs, vendor lock-in

**Constitution Alignment**: Efficiency (use captions when available), Incremental Safety (graceful fallback), Stack-Adherence (no vendor lock-in)

---

## 3. Summarization

### Decision: **Pydantic AI + LangGraph**

**Rationale**:

**Pydantic AI**:
- Type-safe AI interactions with Pydantic models
- Structured output generation (summary with topics, speakers, key takeaways)
- Validation built-in (configurable word count limits)
- LLM-agnostic (works with OpenAI, Anthropic, local models)

**LangGraph**:
- Explicit workflow orchestration for summarization pipeline
- Handles retry logic, error recovery gracefully
- Supports streaming for long-running operations
- Enables instrumentation and observability hooks
- State management for multi-step summarization if needed

**Alternatives Considered**:
- **LangChain alone**: More heavyweight, less explicit control flow
- **Raw OpenAI API**: No structure, manual retry logic, less maintainable
- **Anthropic Claude API directly**: Vendor lock-in, less flexible

**Constitution Alignment**: Clarity (explicit workflow), Research-Engineering Bridge (instrumentation), Stack-Adherence (LLM-agnostic)

---

## 4. Storage & Memory

### Decision: **Postgres + Mem0 (Vector Storage Handled by Mem0)**

**Rationale**:

**Postgres**:
- Reliable, mature, battle-tested RDBMS
- JSON support for transcript with timestamps
- TEXT[] for keyword tags
- Full-text search for keyword matching
- ACID guarantees for data integrity
- Excellent tooling and ecosystem
- Stores: youtube_videos, transcripts, summaries tables

**Mem0**:
- **Handles all vector storage and embeddings internally**
- Automatic embedding generation (no manual embedding code needed)
- Semantic search API out of the box
- Supports memory contexts and relationships (future feature)
- Can use Postgres as its backend (unified database) or separate vector DB
- We only store Mem0 memory IDs as references in our Postgres tables

**Hybrid Search Strategy**:
- Postgres full-text search for exact keyword matching
- Mem0 API for semantic/conceptual search
- Combine results in Python with weighted ranking

**Deployment Options**:
- **Supabase**: Managed Postgres, generous free tier, Auth ready
- **Neon**: Serverless Postgres with branching, good for development
- **Local Docker**: Standard Postgres container (Mem0 handles vectors)

**Why NOT PGVector directly**:
- Mem0 abstracts vector operations (embedding generation, search, indexing)
- Simpler code: `mem0.add()` instead of manual embedding + SQL INSERT
- Can switch vector backends later without code changes
- Focus on research, not vector database operations

**Alternatives Considered**:
- **Manual PGVector**: More control, more code, manual embedding pipeline
- **Chroma/Qdrant/Pinecone separate**: Adds deployment complexity
- **SQLite + sqlite-vec**: Not mature enough, limited scale
- **Elasticsearch**: Heavyweight, overkill for 1000+ documents

**Constitution Alignment**: Stack-Adherence (established tools), Efficiency (Mem0 reduces boilerplate), Clarity (simpler code)

---

## 5. Hybrid Search Strategy

### Decision: **Postgres Full-Text Search + Mem0 Semantic Search (Hybrid in Python)**

**Rationale**:

**Full-Text Search** (Postgres native):
- `to_tsvector` and `to_tsquery` for keyword matching
- Supports phrase queries, Boolean operators, ranking
- GIN indexes for fast text search
- Handles exact term matching for known concepts (e.g., "MARL coordination")

**Semantic Search** (Mem0 API):
- Mem0 handles all embedding operations internally
- Finds conceptually related content even with different wording
- Example: "multi-agent learning" matches "cooperative RL" semantically
- No manual embedding generation or vector database management needed

**Hybrid Ranking** (Application Layer):
- Combine scores in Python using weighted sum: `final_score = α * text_score + β * semantic_score`
- Tune weights based on research usage patterns
- Default: Equal weighting (α=0.5, β=0.5)
- Implementation in `src/sage/services/search.py`

**Why Hybrid in Python (not SQL)**:
- Mem0 is an external API, not a Postgres extension
- Cleaner separation: Postgres for structured data, Mem0 for vectors
- Easier to adjust ranking algorithms without SQL complexity
- Can add more search sources later (e.g., local embeddings)

**Alternatives Considered**:
- **Keyword-only**: Misses conceptual matches, poor recall
- **Semantic-only**: Misses exact technical terms, no control
- **BM25 (Elasticsearch)**: Requires separate service, overkill
- **PGVector directly**: Mem0 provides better abstraction

**Constitution Alignment**: Research-Engineering Bridge (optimal recall), Clarity (explicit scoring), Efficiency (Mem0 handles complexity)

---

## 6. Observability

### Decision: **LangFuse + rich logging**

**Rationale**:

**LangFuse**:
- Open-source LLM observability platform
- Tracks: prompts, completions, costs, latency, token usage
- Critical for research: understand summarization quality trends
- Helps optimize: which prompts work best, when to use shorter context
- Enables cost tracking for budgeting
- Self-hostable or cloud (free tier available)

**rich (logging)**:
- Constitution requirement: colored terminal output
- Progress bars for long-running transcriptions
- Structured logging with timestamps
- Error messages stand out visually
- Integrates with Python logging module

**Why NOT more observability**:
- Spec clarification confirmed: "basic logging sufficient for initial release"
- Can add Prometheus/Grafana later if needed
- LangFuse + rich cover: debugging, cost tracking, user feedback

**Alternatives Considered**:
- **LangSmith**: Paid service, vendor lock-in
- **Weights & Biases**: Overkill for non-ML experimentation
- **None**: No cost tracking, hard to debug LLM issues

**Constitution Alignment**: Research-Engineering Bridge (experiment tracking), Efficiency (minimal setup)

---

## 7. Rate Limiting & Queue Management

### Decision: **In-Memory Queue with Token Bucket Algorithm + YAML Config**

**Rationale**:

**Token Bucket Algorithm**:
- Conservative rate limiting: tokens refill at fixed rate
- Burst capacity for occasional spikes
- Transparent to user (automatic backoff)
- Exponential backoff on rate limit errors

**Queue Implementation**:
- **In-memory queue** using Python `asyncio.Queue` for initial release
- Simple, no database dependency for queue state
- Sufficient for single-user CLI use case
- Progress callbacks report: queue position, ETA, rate limit status
- **Future**: Can add Postgres persistence if needed for reliability across restarts

**Rate Limit Configuration**:
- **YAML config file** (`config/rate_limits.yaml`) instead of database table
- Easier to edit, version-controlled, no migration needed
- Loaded via Pydantic Settings with validation
- Example:
  ```yaml
  services:
    youtube_api:
      requests_per_day: 10000
      requests_per_minute: 100
    openai_api:
      requests_per_minute: 60
  ```

**Rate Limit Targets** (conservative):
- YouTube API: 10,000 units/day (1 video = ~10 units) → ~1000 videos/day max
- OpenAI/Anthropic: Tier-dependent, start with 1 req/min conservative
- Whisper (local): No rate limit, GPU-bound only

**Alternatives Considered**:
- **Celery + Redis**: Heavyweight, requires Redis, overkill for single-user CLI
- **RQ (Redis Queue)**: Still requires Redis deployment
- **Postgres-backed queue**: Adds complexity, not needed for initial release
- **Database rate limit table**: YAML config file is simpler and version-controlled

**Constitution Alignment**: Research-Engineering Bridge (batch processing), Incremental Safety (graceful degradation), Efficiency (minimal infrastructure)

---

## 8. Configuration Management

### Decision: **Pydantic Settings with .env support**

**Rationale**:
- Type-safe configuration with validation
- Environment variable overrides (12-factor app pattern)
- `.env` file for local development secrets
- Example:
  ```python
  class Settings(BaseSettings):
      openai_api_key: str
      postgres_url: str
      max_summary_words: int = 300
      
      model_config = SettingsConfigDict(env_file=".env")
  ```

**Alternatives Considered**:
- **YAML config files**: Less type-safe, manual parsing
- **TOML**: Requires extra dependency, less common for secrets

**Constitution Alignment**: Stack-Adherence (Pydantic per constitution), Clarity (validated config)

---

## 9. Testing Strategy

### Decision: **Pytest with Three Test Levels**

**Unit Tests** (`pytest.mark.unit`):
- Mock external services (YouTube API, LLM API, Postgres)
- Test: URL validation, transcript cleaning, summary formatting
- Fast, no external dependencies

**Integration Tests** (`pytest.mark.integration`):
- Use test database (Docker Compose Postgres)
- Test: full pipeline with real Postgres, mocked LLM responses
- Moderate speed, validates data flow

**Contract Tests** (`pytest.mark.contract`):
- Test CLI interface with Typer's testing utilities
- Validate: command arguments, output format, exit codes
- Fast, no external services

**Why NOT**:
- **End-to-end tests**: Expensive (real API costs), slow, brittle (API changes)
- **Snapshot testing**: Not beneficial for dynamic LLM outputs

**Constitution Alignment**: Incremental Safety (comprehensive testing), Efficiency (explicit markers per constitution)

---

## 10. Deployment & Runtime

### Decision: **Docker + uv + Compose**

**Rationale**:

**uv**:
- Fast Python package manager (constitution requirement)
- `uv sync` installs dependencies quickly
- `uv run sage ingest-youtube` executes CLI without activating venv

**Docker**:
- Reproducible environment (pins OS, Python version, system dependencies)
- Dockerfile includes: WhisperX with GPU support, ffmpeg for yt-dlp
- Single image contains: Sage CLI + all dependencies

**Docker Compose**:
- Local development: Postgres + PGVector + Sage CLI container
- One command: `docker-compose up` gets full stack running
- Volumes for: `.env` secrets, persistent Postgres data

**Alternatives Considered**:
- **Conda**: Slower, heavier, uv preferred per constitution
- **Bare metal**: Not reproducible, dependency conflicts
- **Kubernetes**: Overkill for single-user CLI

**Constitution Alignment**: Stack-Adherence (uv), Reproducibility (Docker), Efficiency (Compose simplifies local dev)

---

## Summary of Key Decisions

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **CLI Framework** | Typer | Type-safe, minimal boilerplate, rich integration |
| **Transcript (Primary)** | youtube-transcript-api | Fast, preserves timestamps (default), uses YouTube captions |
| **Transcript (Fallback)** | yt-dlp + WhisperX | Handles videos without captions, local GPU option |
| **Summarization** | Pydantic AI + LangGraph | Structured output, LLM-agnostic, observable |
| **Database** | Postgres | ACID guarantees, full-text search, JSON support |
| **Memory Layer** | Mem0 | Handles embeddings & vector storage internally |
| **Hybrid Search** | Postgres Full-Text + Mem0 API | Exact + conceptual matching, combined in Python |
| **Observability** | LangFuse + rich | LLM tracking, colored CLI output |
| **Rate Limiting** | Token Bucket + In-Memory Queue | Conservative throttling, no DB persistence |
| **Config** | Pydantic Settings + YAML | Type-safe .env, rate limits in config/rate_limits.yaml |
| **Testing** | pytest (3 levels) | Unit/Integration/Contract per constitution |
| **Deployment** | Docker + uv + Compose | Reproducible, GPU-ready, simple local dev |

---

## Dependencies to Add to `pyproject.toml`

```toml
[project.dependencies]
rich = ">=13.7.0"                    # CLI output (existing)
typer = ">=0.9.0"                    # CLI framework
youtube-transcript-api = ">=0.6.0"   # Primary transcript source
yt-dlp = ">=2023.12.0"               # YouTube downloader (fallback)
whisperx = ">=3.1.0"                 # Transcription fallback (optional, for GPU)
pydantic = ">=2.5.0"                 # Models and settings
pydantic-ai = ">=0.0.7"              # AI interactions
langgraph = ">=0.0.13"               # Workflow orchestration
langfuse = ">=2.6.0"                 # Observability
psycopg2-binary = ">=2.9.9"          # Postgres driver
mem0ai = ">=0.0.4"                   # Memory layer (handles embeddings & vector storage)
pyyaml = ">=6.0.1"                   # YAML config file parsing

[project.optional-dependencies]
dev = [
    # ... existing dev dependencies ...
    "pytest-asyncio>=0.21.0",        # Async test support
    "pytest-docker-compose>=3.2.0",  # Docker integration tests
]
```

**Note**: `pgvector` removed - Mem0 handles vector storage internally

---

## Open Questions for Planning Phase

None - all technology decisions resolved and documented.

---

**Phase 0 Status**: ✅ **Complete** - Ready for Phase 1 (Data Model & Contracts)


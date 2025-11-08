# Sage YouTube Ingestion Pipeline

CLI pipeline for ingesting YouTube videos into Sage's research memory stack. The tool retrieves or generates transcripts, produces structured summaries, stores artefacts in Postgres, and exposes search and inspection commands.

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for local Postgres)
- Optional API keys
  - `OPENAI_API_KEY` (summarisation)
  - `ANTHROPIC_API_KEY` (alternative LLM)
  - `MEM0_API_KEY` (semantic storage/search)
  - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (observability)

## Setup

```bash
git clone <repository-url>
cd sage
uv sync
```

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://sage:sage_dev_password@localhost:5432/sage_dev
MEM0_API_KEY=...
OPENAI_API_KEY=<your-openai-api-key>
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
MAX_SUMMARY_WORDS=300
KEEP_TIMESTAMPS=true
ENABLE_SUMMARIZATION=true
LOG_LEVEL=INFO
```

Start local Postgres via Docker Compose:

```bash
docker compose up -d
uv run python -m sage.db.migrate
```

## Usage

All commands run through the `sage` executable (installed via the project script entry point) or `uv run sage` during development.

### Ingest a single video

```bash
uv run sage ingest-youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Key flags:

- `--remove-timestamps` – display cleaned transcript without timestamps
- `--no-summarize` – skip summary generation
- `--tags "reinforcement learning, multi-agent"` – add manual keyword tags
- `--summary-length 400` – override summary target word count
- `--force` – re-ingest even if the URL already exists
- `--quiet` – machine-readable JSON output

### Batch ingest

```bash
uv run sage ingest-youtube-batch --file ./videos.txt --priority 5
```

Options:

- `--urls "<comma-separated list>"` – inline URLs instead of a file
- `--tags` / `--summary-length` / `--remove-timestamps` – applied to each item
- `--quiet` – JSON output containing queue status and item details

### Inspect the queue

```bash
uv run sage queue-status
uv run sage queue-status --json  # machine-readable
```

### Search stored content

```bash
uv run sage search "reinforcement learning"
```

Filters:

- `--limit 5`
- `--channel "DeepMind"`
- `--start-date 2024-01-01`
- `--end-date 2024-12-31`
- `--tags "policy gradients, exploration"`
- `--json` for programmatic access

### Inspect stored records

```bash
uv run sage show-summary <SUMMARY_ID>
uv run sage show-transcript <TRANSCRIPT_ID> --raw
```

## Development Workflow

```bash
uv sync                 # install dependencies
uv run sage --help      # verify CLI wiring
just format             # apply formatting rules
just lint               # run Ruff
just typecheck          # run mypy (strict mode)
just test               # run the full pytest suite
```

The codebase enforces strict typing (no implicit `Any`) and rich logging. Refer to `specs/001-youtube-ingestion/` for design documents, data models, contracts, and quickstart details.

# Sage

## Pre-commit
- install tooling with `uv tool install pre-commit`
- enable the git hook via `pre-commit install`
- run `pre-commit run --all-files` before pushing if you want to scan everything locally
- hooks include `gitleaks`, which blocks OpenAI credentials (e.g., entries in `.env` like `OPENAI_API_KEY=<your-openai-api-key>`)

## Local Development

### Supabase Stack

We use the official Supabase Docker stack for Postgres + pgvector + Studio. Start it from the repository root:

```bash
just supabase-up
```

This launches:

- `supabase-db`: Postgres 15 with pgvector enabled
- `supabase-kong`, `supabase-rest`, `supabase-gotrue`, `supabase-realtime`, `supabase-storage`, `supabase-functions`
- `supabase-studio`: accessible at <http://localhost:54326>

The default connection string (matching `.env.example`) is:

```
postgresql://postgres:postgres@localhost:5432/postgres
```

To stop the stack:

```bash
just supabase-down
```

Tail service logs (e.g., database + storage):

```bash
just supabase-logs supabase-db supabase-storage
```

Data persists in the named volumes `supabase_db_data` and `supabase_storage_data`.

### Application Commands

Install dependencies and run the CLI via `uv`:

```bash
uv sync
uv run sage --help
```


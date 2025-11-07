# Quickstart: YouTube Ingestion Pipeline

**Feature**: 001-youtube-ingestion  
**For**: Developers implementing the feature  
**Date**: 2025-11-07

## Overview

This quickstart guide helps you set up the development environment and implement the YouTube transcript ingestion pipeline step-by-step, following the phased approach (P1 → P2 → P3).

---

## Prerequisites

- **Python**: 3.12+ (check with `python --version`)
- **uv**: Package manager (install from https://github.com/astral-sh/uv)
- **Docker**: For local Postgres + PGVector (install from https://www.docker.com/)
- **Git**: Version control
- **API Keys** (for full functionality):
  - OpenAI API key (for summarization) - https://platform.openai.com/api-keys
  - Optional: Anthropic API key (alternative LLM)
  - Optional: LangFuse API key (for observability)

---

## Setup Steps

### 1. Environment Setup

```bash
# Navigate to project root
cd sage

# Install dependencies with uv
uv sync

# Verify installation
uv run python -c "import typer; print('✅ Typer installed')"
uv run python -c "import youtube_transcript_api; print('✅ youtube-transcript-api installed')"
```

### 2. Database Setup (Local Development)

Create `docker-compose.yml` in project root:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: sage_dev
      POSTGRES_USER: sage
      POSTGRES_PASSWORD: sage_dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sage"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

**Note**: Mem0 handles vector storage internally. We use standard Postgres (no PGVector extension needed).

Start database:

```bash
docker-compose up -d

# Verify database is running
docker-compose ps
```

### 3. Configuration

Create `.env` file in project root (never commit this!):

```bash
# Database
DATABASE_URL=postgresql://sage:sage_dev_password@localhost:5432/sage_dev

# Mem0 (for embeddings and semantic search)
MEM0_API_KEY=...your-key-if-using-cloud...
# Or configure Mem0 to use local Postgres backend

# OpenAI (for summarization)
OPENAI_API_KEY=sk-...your-key-here...

# Optional: Alternative LLM
# ANTHROPIC_API_KEY=sk-ant-...

# Optional: Observability
# LANGFUSE_PUBLIC_KEY=pk-lf-...
# LANGFUSE_SECRET_KEY=sk-lf-...
# LANGFUSE_HOST=https://cloud.langfuse.com

# App Settings
MAX_SUMMARY_WORDS=300
KEEP_TIMESTAMPS=true
ENABLE_SUMMARIZATION=true
LOG_LEVEL=INFO
```

Add `.env` to `.gitignore`:

```bash
echo ".env" >> .gitignore
```

Create `config/rate_limits.yaml` for API rate limiting:

```yaml
# config/rate_limits.yaml
services:
  youtube_api:
    requests_per_day: 10000
    requests_per_minute: 100
    
  openai_api:
    requests_per_minute: 60
    tokens_per_minute: 90000
    
  anthropic_api:
    requests_per_minute: 50
```

### 4. Database Migrations

Create initial schema:

```bash
# Run schema creation SQL from data-model.md
uv run python -m sage.db.migrate
```

(Implementation note: Create `src/sage/db/migrate.py` that executes SQL from data-model.md)

### 5. Verify Setup

```bash
# Test database connection
uv run python -c "
import psycopg2
conn = psycopg2.connect('postgresql://sage:sage_dev_password@localhost:5432/sage_dev')
print('✅ Database connection successful')
conn.close()
"

# Test CLI is accessible
uv run sage --help
```

---

## Implementation Phases

### Phase 1 (P1): Transcript Retrieval ⭐ MVP

**Goal**: Implement `sage ingest-youtube URL` command that retrieves and returns a transcript.

**Tasks**:
1. **CLI Entry Point** (`src/sage/cli/main.py`):
   ```python
   import typer
   from rich.console import Console
   
   app = typer.Typer()
   console = Console()
   
   @app.command()
   def ingest_youtube(
       url: str,
       remove_timestamps: bool = False,
       summarize: bool = True,
       quiet: bool = False
   ):
       """Ingest YouTube video transcript."""
       console.print(f"[green]Processing:[/green] {url}")
       # ... implementation
   ```

2. **Transcript Service** (`src/sage/services/transcript.py`):
   ```python
   from youtube_transcript_api import YouTubeTranscriptApi
   from youtube_transcript_api._errors import TranscriptNotAvailable
   
   class TranscriptService:
       async def get_transcript(self, video_id: str) -> dict:
           """Get transcript with fallback strategy."""
           try:
               # Primary: YouTube captions
               transcript = YouTubeTranscriptApi.get_transcript(video_id)
               return {
                   "source": "youtube_captions",
                   "transcript": transcript,
                   "confidence": 1.0
               }
           except TranscriptNotAvailable:
               # Fallback: WhisperX
               return await self._transcribe_with_whisper(video_id)
   ```

3. **URL Validation** (`src/sage/utils/validation.py`):
   ```python
   import re
   from typing import Optional
   
   def extract_video_id(url: str) -> Optional[str]:
       """Extract YouTube video ID from URL."""
       patterns = [
           r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
           r'(?:embed\/)([0-9A-Za-z_-]{11})',
           r'^([0-9A-Za-z_-]{11})$'
       ]
       for pattern in patterns:
           match = re.search(pattern, url)
           if match:
               return match.group(1)
       return None
   ```

4. **Test P1**:
   ```bash
   uv run sage ingest-youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

**Validation Checkpoint**: You should see a transcript printed to console.

---

### Phase 2 (P2): Summarization

**Goal**: Add AI-powered summarization to the pipeline.

**Tasks**:
1. **Summarization Service** (`src/sage/services/summarization.py`):
   ```python
   from pydantic_ai import Agent
   from pydantic import BaseModel
   
   class SummaryOutput(BaseModel):
       summary_text: str
       topics: list[str]
       speakers: list[str]
       key_takeaways: list[str]
   
   class SummarizationService:
       def __init__(self, model: str = "gpt-4-turbo"):
           self.agent = Agent(model, result_type=SummaryOutput)
       
       async def summarize(self, transcript: str, max_words: int = 300) -> SummaryOutput:
           """Generate structured summary."""
           prompt = f"""Summarize this video transcript in max {max_words} words.
           
           Extract:
           - Main topics
           - Speaker names (if mentioned)
           - Key takeaways (3-5 bullet points)
           
           Transcript:
           {transcript[:10000]}  # Limit context
           """
           result = await self.agent.run(prompt)
           return result.data
   ```

2. **Integrate into CLI**:
   ```python
   @app.command()
   def ingest_youtube(url: str, summarize: bool = True, ...):
       # ... get transcript ...
       
       if summarize:
           summary_service = SummarizationService()
           summary = await summary_service.summarize(transcript_text)
           console.print(f"[blue]Summary:[/blue] {summary.summary_text}")
   ```

3. **Test P2**:
   ```bash
   uv run sage ingest-youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   # Should now show both transcript AND summary
   ```

**Validation Checkpoint**: You should see a 300-word summary with topics and key takeaways.

---

### Phase 3 (P3): Memory Storage & Search

**Goal**: Store transcript + summary in Postgres with hybrid search.

**Tasks**:
1. **Storage Service** (`src/sage/services/storage.py`):
   ```python
   from mem0 import MemoryClient
   import psycopg2
   
   class StorageService:
       def __init__(self, db_url: str):
           self.conn = psycopg2.connect(db_url)
           self.memory = MemoryClient()  # Mem0 handles embeddings internally
       
       async def store_memory_entry(
           self,
           video_data: dict,
           transcript_data: dict,
           summary_data: dict
       ) -> str:
           """Store full memory entry and return Mem0 memory ID."""
           # 1. Insert youtube_videos in Postgres
           # 2. Insert transcripts in Postgres
           # 3. Store in Mem0 (generates embeddings automatically)
           mem0_id = self.memory.add(
               messages=[{"role": "user", "content": transcript + "\n\n" + summary}],
               user_id="researcher_jeff",
               metadata=video_data
           )
           # 4. Insert summaries in Postgres with mem0_id reference
           # 5. Return Mem0 memory ID
           return mem0_id
   ```

2. **Search Service** (`src/sage/services/search.py`):
   ```python
   from mem0 import MemoryClient
   
   class SearchService:
       def __init__(self):
           self.mem0 = MemoryClient()
           self.conn = psycopg2.connect(db_url)
       
       async def hybrid_search(
           self,
           query: str,
           limit: int = 20
       ) -> list[dict]:
           """Combine Postgres keyword search with Mem0 semantic search."""
           # 1. Keyword search in Postgres
           keyword_results = await self.postgres_search(query, limit)
           
           # 2. Semantic search via Mem0
           semantic_results = self.mem0.search(query, user_id="researcher_jeff", limit=limit)
           
           # 3. Merge and rank (0.5 weight each)
           return merge_results(keyword_results, semantic_results)
   ```

3. **Add Search Command**:
   ```python
   @app.command()
   def search(query: str, limit: int = 20):
       """Search memory for videos."""
       search_service = SearchService()
       results = await search_service.hybrid_search(query, limit)
       
       for result in results:
           console.print(f"[green]{result['title']}[/green]")
           console.print(f"  Score: {result['score']:.2f}")
           console.print(f"  {result['url']}")
   ```

4. **Test P3**:
   ```bash
   # Ingest a video
   uv run sage ingest-youtube "https://www.youtube.com/watch?v=seminar_id"
   
   # Search for it
   uv run sage search "reinforcement learning"
   ```

**Validation Checkpoint**: You should find the ingested video via search.

---

## Testing

### Run All Tests

```bash
# All tests
just test

# Unit tests only
just test-unit

# Integration tests (requires Docker Postgres running)
just test-integration

# Contract tests (CLI interface)
pytest -m contract
```

### Manual Testing Checklist

- [ ] Ingest video with captions → uses youtube-transcript-api
- [ ] Ingest video without captions → falls back to WhisperX
- [ ] Generate summary → under 300 words, has topics/speakers
- [ ] Store in database → returns memory ID
- [ ] Search exact keyword → finds result
- [ ] Search conceptual query → finds semantically similar
- [ ] Batch process 3 videos → all succeed with rate limiting
- [ ] Handle private video → clear error message
- [ ] Handle invalid URL → validation error

---

## Development Workflow

### 1. Pick a Task from `tasks.md` (Created by `/speckit.tasks`)

```bash
# View tasks
cat specs/001-youtube-ingestion/tasks.md
```

### 2. Create Feature Branch (if implementing specific task)

```bash
git checkout -b task/transcript-service
```

### 3. Implement + Test

```bash
# Make changes to src/sage/...
# Add tests to tests/...

# Run tests
just test
```

### 4. Format + Lint

```bash
# Format code
just format

# Lint
just lint

# Type check
just typecheck
```

### 5. Commit

```bash
git add -A
git commit -m "feat(youtube): implement transcript service with fallback"
```

---

## Common Issues

### Database Connection Error

```
Error: could not connect to server
```

**Solution**: Ensure Docker Postgres is running:
```bash
docker-compose up -d
docker-compose ps  # Should show postgres running
```

### Import Error: ModuleNotFoundError

```
ModuleNotFoundError: No module named 'typer'
```

**Solution**: Ensure dependencies installed and using `uv run`:
```bash
uv sync
uv run sage --help  # Use `uv run` prefix
```

### WhisperX GPU Not Available

```
Warning: CUDA not available, using CPU
```

**Solution**: This is expected on non-GPU machines. WhisperX will run slower on CPU but still works. For GPU:
```bash
# Install CUDA-enabled PyTorch first
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### API Rate Limit

```
Error: Rate limit exceeded
```

**Solution**: Wait for reset or use batch mode with automatic queuing:
```bash
sage ingest-youtube-batch --file urls.txt  # Handles rate limits automatically
```

---

## Next Steps

1. Review `tasks.md` (generated by `/speckit.tasks`) for implementation task breakdown
2. Start with P1 tasks (transcript retrieval)
3. Validate each phase independently before moving to next
4. Use `just test` frequently to catch regressions early
5. Check LangFuse dashboard to monitor costs and latency

---

## Resources

- **Typer Docs**: https://typer.tiangolo.com/
- **youtube-transcript-api**: https://github.com/jdepoix/youtube-transcript-api
- **WhisperX**: https://github.com/m-bain/whisperX
- **Pydantic AI**: https://ai.pydantic.dev/
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **PGVector**: https://github.com/pgvector/pgvector
- **Mem0**: https://mem0.ai/
- **LangFuse**: https://langfuse.com/docs

---

**Quickstart Status**: ✅ **Complete** - Ready for implementation!


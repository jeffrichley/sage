# Data Model: YouTube Transcript & Memory Ingestion

**Feature**: 001-youtube-ingestion  
**Date**: 2025-11-07  
**Database**: PostgreSQL 15+ (Mem0 handles vector storage separately)

## Overview

This document defines the data model for storing YouTube video transcripts, summaries, and metadata in Sage's PostgreSQL database. **Mem0 handles its own vector storage and embeddings** - we only store Mem0 memory IDs as references. The schema supports full-text search in Postgres, with Mem0 providing semantic search capabilities.

---

## Database Schema

### Table: `youtube_videos`

Stores metadata about ingested YouTube videos.

```sql
CREATE TABLE youtube_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_url TEXT NOT NULL UNIQUE,              -- Original YouTube URL (unique constraint prevents duplicates)
    video_id VARCHAR(20) NOT NULL,               -- Extracted YouTube video ID (e.g., "dQw4w9WgXcQ")
    video_title TEXT NOT NULL,                   -- Title from YouTube metadata
    channel_name TEXT NOT NULL,                  -- Channel/author name
    channel_id VARCHAR(50),                      -- YouTube channel ID
    publish_date TIMESTAMP,                      -- Original video publication date
    duration_seconds INTEGER,                    -- Video length in seconds
    language VARCHAR(10) DEFAULT 'en',           -- Detected/specified language (ISO 639-1)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(), -- Ingestion timestamp
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()  -- Last update timestamp
);

-- Indexes
CREATE INDEX idx_youtube_videos_video_id ON youtube_videos(video_id);
CREATE INDEX idx_youtube_videos_channel_id ON youtube_videos(channel_id);
CREATE INDEX idx_youtube_videos_created_at ON youtube_videos(created_at DESC);
CREATE INDEX idx_youtube_videos_publish_date ON youtube_videos(publish_date DESC);

-- Full-text search index on title
CREATE INDEX idx_youtube_videos_title_fts ON youtube_videos USING GIN(to_tsvector('english', video_title));
```

---

### Table: `transcripts`

Stores transcript data with optional timestamps.

```sql
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
    raw_transcript_json JSONB,                   -- Original transcript with timestamps: [{"start": 0.0, "duration": 2.5, "text": "..."}, ...]
    cleaned_transcript TEXT NOT NULL,            -- Cleaned, searchable text (timestamps removed)
    word_count INTEGER NOT NULL,                 -- Total words in transcript
    transcript_source VARCHAR(50) NOT NULL,      -- Source: "youtube_captions", "whisper_local", "whisper_api"
    confidence_score REAL,                       -- Transcription confidence (0.0-1.0, if available)
    has_timestamps BOOLEAN DEFAULT TRUE,         -- Whether timestamps are preserved (default: keep timestamps)
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_transcripts_video_id ON transcripts(video_id);
CREATE INDEX idx_transcripts_source ON transcripts(transcript_source);

-- Full-text search index on cleaned transcript
CREATE INDEX idx_transcripts_cleaned_fts ON transcripts USING GIN(to_tsvector('english', cleaned_transcript));
```

---

### Table: `summaries`

Stores AI-generated summaries of transcripts.

```sql
CREATE TABLE summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
    transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,                  -- Generated summary (configurable max length)
    summary_word_count INTEGER NOT NULL,         -- Words in summary
    identified_topics TEXT[],                    -- Auto-extracted topics/themes
    identified_speakers TEXT[],                  -- Auto-extracted speaker names (if mentioned)
    key_takeaways TEXT[],                        -- Bullet points of main insights
    model_name VARCHAR(100) NOT NULL,            -- LLM model used (e.g., "gpt-4-turbo", "claude-3-opus")
    model_version VARCHAR(50),                   -- Model version/date
    prompt_template TEXT,                        -- Prompt used for summarization (reproducibility)
    generation_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    generation_cost_usd REAL,                    -- API cost (if applicable)
    generation_latency_seconds REAL,             -- Time to generate
    keyword_tags TEXT[],                         -- Auto-generated + manual keyword tags
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_summaries_video_id ON summaries(video_id);
CREATE INDEX idx_summaries_transcript_id ON summaries(transcript_id);
CREATE INDEX idx_summaries_model ON summaries(model_name);

-- Full-text search index on summary
CREATE INDEX idx_summaries_summary_fts ON summaries USING GIN(to_tsvector('english', summary_text));

-- GIN index on array fields for keyword search
CREATE INDEX idx_summaries_topics ON summaries USING GIN(identified_topics);
CREATE INDEX idx_summaries_speakers ON summaries USING GIN(identified_speakers);
CREATE INDEX idx_summaries_keyword_tags ON summaries USING GIN(keyword_tags);
```

---

## Mem0 Integration

**Mem0 handles vector storage and embeddings internally.** We only store the Mem0 memory ID as a reference in the `summaries` table.

### Mem0 Usage

- Mem0 automatically generates embeddings for transcript + summary content
- Mem0 provides semantic search API out of the box
- Mem0 handles vector indexing (HNSW, IVFFlat, etc.) internally
- We query Mem0 for semantic search, and Postgres for keyword/full-text search

### Integration Point

```python
from mem0 import MemoryClient

client = MemoryClient()

# Store memory in Mem0
memory_id = client.add(
    messages=[{"role": "user", "content": transcript + "\n\n" + summary}],
    user_id="researcher_jeff",
    metadata={
        "video_url": "https://youtube.com/watch?v=...",
        "video_title": "Example Seminar",
        "topics": ["MARL", "coordination"],
    }
)

# Store Mem0 reference in Postgres
UPDATE summaries SET mem0_memory_id = memory_id WHERE id = summary_id;
```

---

## Non-Database Components

### Processing Queue (In-Memory)

Batch video processing queue is managed **in-memory** using Python's `asyncio.Queue`. No database persistence for now.

```python
# In src/sage/services/queue.py
from asyncio import Queue
from dataclasses import dataclass

@dataclass
class QueueItem:
    video_url: str
    status: str  # queued, processing, completed, failed
    progress: int
    # ... other fields
    
processing_queue: Queue[QueueItem] = Queue()
```

### Rate Limit Configuration (Config File)

Rate limits stored in `config/rate_limits.yaml` (not database):

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

Loaded via Pydantic settings in `src/sage/config/settings.py`.

---

## Pydantic Models

Python models for type-safe database interactions.

```python
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl

class YouTubeVideo(BaseModel):
    id: UUID
    video_url: HttpUrl
    video_id: str
    video_title: str
    channel_name: str
    channel_id: Optional[str] = None
    publish_date: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    language: str = "en"
    created_at: datetime
    updated_at: datetime

class Transcript(BaseModel):
    id: UUID
    video_id: UUID
    raw_transcript_json: Optional[dict] = None
    cleaned_transcript: str
    word_count: int
    transcript_source: str  # "youtube_captions" | "whisper_local" | "whisper_api"
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    has_timestamps: bool = True  # Default: keep timestamps
    created_at: datetime

class Summary(BaseModel):
    id: UUID
    video_id: UUID
    transcript_id: UUID
    summary_text: str
    summary_word_count: int
    identified_topics: list[str] = []
    identified_speakers: list[str] = []
    key_takeaways: list[str] = []
    model_name: str
    model_version: Optional[str] = None
    prompt_template: Optional[str] = None
    generation_timestamp: datetime
    generation_cost_usd: Optional[float] = None
    generation_latency_seconds: Optional[float] = None
    mem0_memory_id: Optional[str] = None  # Reference to Mem0 memory entry
    keyword_tags: list[str] = []  # Auto-generated + manual tags
    created_at: datetime

class QueueItem(BaseModel):
    """In-memory queue item (not persisted to database)"""
    video_url: HttpUrl
    status: str  # "queued" | "processing" | "completed" | "failed"
    priority: int = 0
    current_stage: Optional[str] = None
    stage_progress_percent: int = 0
    overall_progress_percent: int = 0
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
```

---

## Hybrid Search Strategy

Hybrid search combines Postgres full-text search with Mem0 semantic search.

### Keyword Search (Postgres Full-Text)

```sql
-- Search in video titles, transcripts, and summaries for exact keywords
SELECT 
    v.id,
    v.video_title,
    v.channel_name,
    v.publish_date,
    s.summary_text,
    s.keyword_tags,
    ts_rank(to_tsvector('english', t.cleaned_transcript), plainto_tsquery('english', 'MARL coordination')) AS text_rank
FROM youtube_videos v
JOIN transcripts t ON v.id = t.video_id
JOIN summaries s ON v.id = s.video_id
WHERE to_tsvector('english', t.cleaned_transcript || ' ' || s.summary_text) 
      @@ plainto_tsquery('english', 'MARL coordination')
ORDER BY text_rank DESC
LIMIT 20;
```

### Semantic Search (Mem0 API)

```python
# Mem0 handles semantic search via its API
from mem0 import MemoryClient

client = MemoryClient()

# Semantic search for conceptually similar content
results = client.search(
    query="multi-agent coordination strategies",
    user_id="researcher_jeff",
    limit=20
)

# Returns: list of memories with similarity scores
# [{"id": "mem_123", "memory": "...", "score": 0.85, "metadata": {...}}, ...]
```

### Hybrid Search (Python Implementation)

```python
# In src/sage/services/search.py
async def hybrid_search(query: str, limit: int = 20) -> list[dict]:
    """Combine Postgres keyword search with Mem0 semantic search."""
    
    # 1. Keyword search in Postgres
    keyword_results = await postgres_search(query, limit=limit)
    
    # 2. Semantic search via Mem0
    semantic_results = mem0_client.search(query, user_id="researcher_jeff", limit=limit)
    
    # 3. Merge and rank results
    combined = merge_results(keyword_results, semantic_results, weights=(0.5, 0.5))
    
    return combined[:limit]
```

---

## Migration Strategy

**Initial Setup**:
1. Create Postgres database (PGVector extension not needed - Mem0 handles vectors)
2. Run schema creation SQL (tables: youtube_videos → transcripts → summaries)
3. Create `config/rate_limits.yaml` with default API quotas
4. Configure Mem0 with connection to Postgres backend

**Future Migrations**:
- Use Alembic for version-controlled schema migrations
- Keep migrations in `src/sage/db/migrations/` directory

---

## Backup & Retention

**Backup Strategy**:
- Daily automated backups of Postgres (Supabase/Neon handle this)
- Weekly full exports for disaster recovery
- Mem0 data backed up as part of Postgres backup (if using Postgres backend)

**Data Retention**:
- Keep all data indefinitely (per spec clarification)
- No automatic deletion policies
- Manual cleanup via CLI command (future feature)

---

**Phase 1 Data Model Status**: ✅ **Complete** - Ready for contracts and quickstart


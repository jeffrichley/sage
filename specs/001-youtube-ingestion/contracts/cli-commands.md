# CLI Command Contracts: YouTube Ingestion

**Feature**: 001-youtube-ingestion  
**Framework**: Typer  
**Date**: 2025-11-07

## Overview

This document specifies the exact CLI interface for YouTube video ingestion commands. All commands are implemented using Typer with rich progress bars and colored output per constitution requirements.

---

## Command: `sage ingest-youtube`

Primary command for ingesting YouTube videos into Sage memory.

### Synopsis

```bash
sage ingest-youtube URL [OPTIONS]
```

### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `URL` | str | Yes | YouTube video URL (supports youtube.com, youtu.be formats) |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--remove-timestamps` | flag | False | Remove timestamps from transcript (kept by default) |
| `--summarize / --no-summarize` | flag | True | Generate AI summary (default: enabled) |
| `--tags` | str | None | Comma-separated manual tags (e.g., "RL,multi-agent,maritime") |
| `--summary-length` | int | 300 | Maximum words in generated summary |
| `--quiet` / `-q` | flag | False | Silent mode (no progress bars, only final output) |
| `--force` | flag | False | Re-ingest even if URL already exists |
| `--help` / `-h` | flag | - | Show help message and exit |

### Examples

**Basic ingestion** (with timestamps and summary):
```bash
sage ingest-youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Without timestamps**:
```bash
sage ingest-youtube "https://youtu.be/dQw4w9WgXcQ" --remove-timestamps
```

**With custom tags and summary length**:
```bash
sage ingest-youtube "https://www.youtube.com/watch?v=abc123" \
  --tags "reinforcement-learning,multi-agent,maritime" \
  --summary-length 500
```

**Transcript only (no summary)**:
```bash
sage ingest-youtube "https://www.youtube.com/watch?v=abc123" --no-summarize
```

**Silent mode for scripting**:
```bash
sage ingest-youtube "https://www.youtube.com/watch?v=abc123" --quiet
```

### Output (Success)

**Interactive mode** (default):
```
🎬 Processing: Example Video Title
📺 Channel: Example Channel

[████████████████████░░░░] 80% Summarizing...

✅ Ingestion complete!

📄 Transcript: 15,234 words (confidence: 0.95)
📝 Summary: 287 words
🏷️  Tags: reinforcement-learning, multi-agent, maritime, MARL, coordination
💾 Memory ID: 550e8400-e29b-41d4-a716-446655440000

🔗 Deep links:
   https://www.youtube.com/watch?v=abc123&t=0
   https://www.youtube.com/watch?v=abc123&t=120
   https://www.youtube.com/watch?v=abc123&t=360

💰 Cost: $0.023 | ⏱️  Duration: 3m 24s
```

**Quiet mode** (JSON output for scripting):
```json
{
  "status": "success",
  "video": {
    "url": "https://www.youtube.com/watch?v=abc123",
    "title": "Example Video Title",
    "channel": "Example Channel",
    "duration": 3600
  },
  "transcript": {
    "word_count": 15234,
    "source": "youtube_captions",
    "confidence": 0.95
  },
  "summary": {
    "word_count": 287,
    "topics": ["reinforcement-learning", "multi-agent", "MARL"],
    "speakers": ["Dr. Smith"],
    "key_takeaways": [
      "Multi-agent systems benefit from coordination mechanisms",
      "MARL outperforms single-agent RL in complex environments"
    ]
  },
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "cost_usd": 0.023,
  "duration_seconds": 204
}
```

### Output (Failure)

**Invalid URL**:
```
❌ Error: Invalid YouTube URL
   Expected format: https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID
   Received: https://example.com/video

Exit code: 1
```

**Video unavailable**:
```
❌ Error: Video not accessible
   URL: https://www.youtube.com/watch?v=private123
   Reason: Video is private or does not exist

Exit code: 2
```

**Rate limit reached**:
```
⚠️  Rate limit reached for YouTube API
   Queued for processing (position: 3)
   Estimated wait: 5 minutes

   Use --quiet to run in background.

Exit code: 0  (queued successfully)
```

**Network error**:
```
❌ Error: Network connection failed
   Could not connect to YouTube API
   
   Retry with: sage ingest-youtube <URL>

Exit code: 3
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (or queued) |
| 1 | Invalid input (URL, arguments) |
| 2 | Video not accessible (private, deleted, unavailable) |
| 3 | Network/API error (transient failure) |
| 4 | Processing error (transcription, summarization failed) |
| 5 | Storage error (database connection, write failure) |

---

## Command: `sage ingest-youtube-batch`

Batch ingestion of multiple YouTube videos from a file or list.

### Synopsis

```bash
sage ingest-youtube-batch [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--file` / `-f` | Path | None | File containing YouTube URLs (one per line) |
| `--urls` | str | None | Comma-separated list of URLs |
| `--remove-timestamps` | flag | False | Remove timestamps for all videos (kept by default) |
| `--summarize / --no-summarize` | flag | True | Generate summary for all (default: enabled) |
| `--tags` | str | None | Common tags to apply to all videos |
| `--quiet` / `-q` | flag | False | Silent mode (no progress bars) |
| `--help` / `-h` | flag | - | Show help message |

### Examples

**From file**:
```bash
sage ingest-youtube-batch --file urls.txt --tags "seminar,2024"
```

**From list**:
```bash
sage ingest-youtube-batch --urls "https://youtu.be/abc123,https://youtu.be/xyz789"
```

### Output (Success)

**Interactive mode**:
```
📋 Batch ingestion: 5 videos queued

[██████████░░░░░░░░░░] 2/5 completed

✅ Completed: Example Video 1 (Memory ID: 550e8400...)
✅ Completed: Example Video 2 (Memory ID: 660f9500...)
⏳ Processing: Example Video 3 (45% - transcribing...)
⏳ Queued: Example Video 4
⏳ Queued: Example Video 5

⏱️  Estimated completion: 8 minutes
```

**Quiet mode** (JSON):
```json
{
  "status": "processing",
  "total": 5,
  "completed": 2,
  "processing": 1,
  "queued": 2,
  "failed": 0,
  "results": [
    {
      "url": "https://youtu.be/abc123",
      "status": "completed",
      "memory_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    {
      "url": "https://youtu.be/xyz789",
      "status": "completed",
      "memory_id": "660f9500-f3ab-52e5-b827-556766551111"
    },
    {
      "url": "https://youtu.be/def456",
      "status": "processing",
      "progress": 45
    }
  ]
}
```

### Exit Codes

Same as `ingest-youtube` command.

---

## Command: `sage queue status`

Check status of processing queue (batch ingestion monitoring).

### Synopsis

```bash
sage queue status [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | False | Output as JSON |
| `--help` / `-h` | flag | - | Show help message |

### Output

**Interactive mode**:
```
📊 Queue Status

Processing: 1
Queued: 3
Completed (last hour): 5
Failed (last hour): 0

Current: Example Video 3 (65% - summarizing...)
Next: Example Video 4 (ETA: 2 minutes)

Rate Limits:
  YouTube API: 9,847 / 10,000 requests remaining (resets in 6h)
  OpenAI API: OK
```

**JSON mode**:
```json
{
  "queue": {
    "processing": 1,
    "queued": 3,
    "completed_last_hour": 5,
    "failed_last_hour": 0
  },
  "current_item": {
    "url": "https://youtu.be/def456",
    "progress": 65,
    "stage": "summarizing"
  },
  "rate_limits": {
    "youtube_api": {
      "remaining": 9847,
      "total": 10000,
      "reset_at": "2025-11-08T06:00:00Z"
    },
    "openai_api": {
      "status": "ok"
    }
  }
}
```

---

## Progress Callbacks

All commands support progress callbacks for rich UI updates.

### Callback Events

```python
from enum import Enum
from pydantic import BaseModel

class ProcessingStage(str, Enum):
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    STORING = "storing"
    COMPLETE = "complete"
    FAILED = "failed"

class ProgressUpdate(BaseModel):
    stage: ProcessingStage
    stage_progress: int  # 0-100
    overall_progress: int  # 0-100
    message: str
    video_url: str
    estimated_time_remaining: Optional[int]  # seconds
```

### Example Progress Sequence

```python
# 1. Validation
ProgressUpdate(stage="validating", stage_progress=100, overall_progress=5, message="Validating URL...")

# 2. Downloading
ProgressUpdate(stage="downloading", stage_progress=50, overall_progress=25, message="Downloading audio...")

# 3. Transcribing
ProgressUpdate(stage="transcribing", stage_progress=75, overall_progress=60, message="Transcribing (WhisperX)...")

# 4. Summarizing
ProgressUpdate(stage="summarizing", stage_progress=100, overall_progress=85, message="Generating summary...")

# 5. Storing
ProgressUpdate(stage="storing", stage_progress=100, overall_progress=100, message="Saving to memory...")

# 6. Complete
ProgressUpdate(stage="complete", stage_progress=100, overall_progress=100, message="Ingestion complete!")
```

---

## Error Handling Contract

All commands must:
1. Validate inputs before processing (fail fast)
2. Provide actionable error messages with suggestions
3. Use appropriate exit codes
4. Log errors to `ingestion_logs` table
5. Apply retry logic with exponential backoff for transient failures
6. Never crash without error message

---

## Testing Contracts

### Contract Tests (CLI Interface)

Test with `pytest.mark.contract`:

```python
@pytest.mark.contract
def test_ingest_youtube_valid_url():
    result = runner.invoke(app, ["ingest-youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "--no-summary"])
    assert result.exit_code == 0
    assert "Ingestion complete" in result.stdout

@pytest.mark.contract
def test_ingest_youtube_invalid_url():
    result = runner.invoke(app, ["ingest-youtube", "https://example.com/video"])
    assert result.exit_code == 1
    assert "Invalid YouTube URL" in result.stdout
```

---

**CLI Contracts Status**: ✅ **Complete** - Ready for implementation


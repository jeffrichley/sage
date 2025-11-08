# Pipeline Validation Report

**Date**: 2025-11-08  
**Environment**: Windows 11, Python 3.12, uv-managed virtualenv, local Postgres via Docker (mem0 disabled)  
**Observer**: Sage Automation (GPT-5 Codex)

## Test Inputs

- Video URL: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- Flags: `--no-summarize --quiet` (summaries skipped due to missing OpenAI/Anthropic keys)

## Command Log

1. **Single Ingestion**

   ```bash
   uv run sage ingest-youtube "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --no-summarize --quiet
   ```

   Key observations:

   - Rich logging confirmed metadata extraction and caption fetch.
   - Database migrations auto-executed (`001_initial_schema.sql` applied).
   - Output (abridged):

     ```json
     {
       "status": "success",
       "video": {
         "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
         "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
         "database_id": "5f4c9401-8810-4f21-a596-f695be162bc7"
       },
       "transcript": {
         "word_count": 487,
         "source": "youtube_captions",
         "database_id": "2a0d96be-6054-415c-9bfa-0dd941d5c39c"
       }
     }
     ```

   - Mem0 storage skipped (API key not configured) with informative warning.

2. **Hybrid Search**

   ```bash
   uv run sage search "Never Gonna Give You Up" --limit 1 --json
   ```

   - Returned the ingested video with matching database identifiers.
   - Keyword score populated; semantic score omitted (Mem0 disabled).

## Result Summary

- ✅ URL validation, metadata extraction, caption transcript, and database storage verified.
- ✅ Hybrid search (Postgres keyword) locates stored video and returns transcript ID.
- ⚠️ Summaries not generated due to missing LLM credentials; storage pipeline handled this branch gracefully.
- ✅ Logging improvements visible (`Storage` stage logs, Mem0 warnings, caption retry fallback not triggered).

## Follow-up Actions

- Configure OpenAI/Anthropic and Mem0 keys to validate summarisation and semantic search branches.
- Run `uv run sage ingest-youtube <URL> --summarize --quiet` once credentials are available to capture summary/embedding IDs.



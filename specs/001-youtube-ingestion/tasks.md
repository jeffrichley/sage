# Tasks: YouTube Transcript & Memory Ingestion Pipeline

**Input**: Design documents from `/specs/001-youtube-ingestion/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Tests are NOT included in this task list (not explicitly requested in specification).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/sage/`, `tests/` at repository root
- Project uses: Python 3.12, Typer CLI, Postgres (pgvector), LangGraph

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Add project dependencies to pyproject.toml (typer, youtube-transcript-api, yt-dlp, whisperx, pydantic-ai, langgraph, langfuse, psycopg2-binary, mem0ai, pyyaml)
- [X] T002 Create config/rate_limits.yaml with conservative API rate limits for youtube_api, openai_api, anthropic_api
- [X] T003 Create docker-compose.yml with Postgres 15 service for local development
- [X] T004 Update .env.example with required environment variables (DATABASE_URL, MEM0_API_KEY, OPENAI_API_KEY, etc.)
- [X] T005 [P] Create src/sage/cli/__init__.py module
- [X] T006 [P] Create src/sage/config/__init__.py module
- [X] T007 [P] Create src/sage/services/__init__.py module
- [X] T008 [P] Create src/sage/models/__init__.py module
- [X] T009 [P] Create src/sage/utils/__init__.py module
- [X] T010 [P] Create src/sage/db/__init__.py module for database utilities

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T011 Create database migration SQL in src/sage/db/migrations/001_initial_schema.sql with youtube_videos, transcripts, summaries tables
- [X] T012 Create src/sage/db/migrate.py script to execute database migrations
- [X] T013 Create src/sage/config/settings.py with Pydantic Settings for environment variables and YAML config loading
- [X] T014 [P] Create src/sage/models/video.py with YouTubeVideo Pydantic model matching database schema
- [X] T015 [P] Create src/sage/models/transcript.py with Transcript Pydantic model matching database schema
- [X] T016 [P] Create src/sage/models/summary.py with Summary Pydantic model matching database schema
- [X] T017 [P] Create src/sage/models/queue.py with QueueItem Pydantic model for in-memory queue
- [X] T018 Create src/sage/utils/validation.py with YouTube URL validation and video ID extraction functions
- [X] T019 Create src/sage/utils/progress.py with ProgressUpdate Pydantic model and ProcessingStage enum
- [X] T020 Create src/sage/cli/main.py with Typer app initialization and rich Console setup
- [X] T021 Create src/sage/db/connection.py with Postgres connection pooling and context managers

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - YouTube URL to Transcript (Priority: P1) 🎯 MVP

**Goal**: Implement `sage ingest-youtube URL` command that retrieves YouTube video transcript with timestamps (default), using youtube-transcript-api as primary source with WhisperX fallback

**Independent Test**: Provide a YouTube URL and verify complete transcript with timestamps is generated and displayed. Test with: (1) video with captions, (2) video without captions (fallback), (3) invalid URL

### Implementation for User Story 1

- [X] T022 [P] [US1] Create src/sage/services/transcript.py with TranscriptService class structure and __init__ method
- [X] T023 [US1] Implement get_transcript_from_captions() method in src/sage/services/transcript.py using youtube-transcript-api
- [X] T024 [US1] Implement _download_video() method in src/sage/services/transcript.py using yt-dlp
- [X] T025 [US1] Implement _transcribe_with_whisper() fallback method in src/sage/services/transcript.py using WhisperX
- [X] T026 [US1] Implement get_transcript() orchestration method in src/sage/services/transcript.py with primary/fallback strategy
- [X] T027 [US1] Implement clean_transcript() method in src/sage/services/transcript.py to create searchable text
- [X] T028 [US1] Implement extract_video_metadata() method in src/sage/services/transcript.py to get title, channel, date from YouTube
- [X] T029 [US1] Create src/sage/cli/ingest_youtube.py with ingest_youtube() Typer command function
- [X] T030 [US1] Implement URL validation in ingest_youtube() command using src/sage/utils/validation.py
- [X] T031 [US1] Integrate TranscriptService into ingest_youtube() command with progress callbacks
- [X] T032 [US1] Implement rich progress bar display in ingest_youtube() command for transcript retrieval stages
- [X] T033 [US1] Add error handling in ingest_youtube() for invalid URLs, private videos, network failures per contracts/cli-commands.md exit codes
- [X] T034 [US1] Add --remove-timestamps and --quiet flags to ingest_youtube() command
- [X] T035 [US1] Register ingest_youtube command in src/sage/cli/main.py Typer app
- [X] T036 [US1] Add rich logging for transcript retrieval (downloading, transcribing stages) using rich.console

**Checkpoint**: At this point, User Story 1 should be fully functional - `sage ingest-youtube URL` returns transcript with timestamps

---

## Phase 4: User Story 2 - Transcript to Concise Summary (Priority: P2)

**Goal**: Add AI-powered summarization using Pydantic AI + LangGraph that generates structured summaries with topics, speakers, and key takeaways

**Independent Test**: Provide a transcript (from P1 or sample text) and verify 300-word summary is generated with identified topics, speakers, and takeaways. Test with: (1) long seminar transcript, (2) short video transcript, (3) technical content preservation

### Implementation for User Story 2

- [X] T037 [P] [US2] Create src/sage/models/progress.py with SummaryOutput Pydantic model (summary_text, topics, speakers, key_takeaways fields)
- [X] T038 [US2] Create src/sage/services/summarization.py with SummarizationService class and Pydantic AI Agent initialization
- [X] T039 [US2] Implement _build_summarization_prompt() method in src/sage/services/summarization.py with configurable max_words parameter
- [X] T040 [US2] Implement summarize() method in src/sage/services/summarization.py using Pydantic AI agent with SummaryOutput result type
- [X] T041 [US2] Implement extract_keywords() method in src/sage/services/summarization.py for automatic keyword tag generation
- [X] T042 [US2] Add LangGraph workflow in src/sage/services/summarization.py for retry logic and error recovery
- [X] T043 [US2] Integrate LangFuse tracing in summarization service to track prompts, costs, and latency
- [X] T044 [US2] Add --summarize/--no-summarize and --summary-length flags to ingest_youtube() command in src/sage/cli/ingest_youtube.py
- [X] T045 [US2] Integrate SummarizationService into ingest_youtube() command with conditional execution (if summarize flag is true)
- [X] T046 [US2] Update progress callbacks in ingest_youtube() to include summarization stage with percentage
- [X] T047 [US2] Add rich formatting for summary output (topics, speakers, takeaways) in ingest_youtube() command
- [X] T048 [US2] Add error handling for summarization failures (LLM API errors, rate limits, timeout)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently - `sage ingest-youtube URL` returns transcript AND summary

---

## Phase 5: User Story 3 - Memory Storage with Metadata (Priority: P3)

**Goal**: Store transcripts and summaries in Postgres with pgvector semantic indexing, implement hybrid search (Postgres full-text + vector similarity), and enable batch processing with queue

**Independent Test**: Provide sample transcript/summary data and verify: (1) storage succeeds with metadata, (2) keyword search returns results, (3) semantic search returns results, (4) batch processing handles multiple URLs with rate limiting

### Implementation for User Story 3

#### Database & Storage Components

- [X] T049 [P] [US3] Run database migration to create youtube_videos, transcripts, summaries tables in src/sage/db/migrate.py
- [X] T050 [P] [US3] Create src/sage/db/repositories.py with generic repository pattern (insert, update, select methods)
- [X] T051 [P] [US3] Create src/sage/db/video_repository.py with YouTubeVideo CRUD operations
- [X] T052 [P] [US3] Create src/sage/db/transcript_repository.py with Transcript CRUD operations
- [X] T053 [P] [US3] Create src/sage/db/summary_repository.py with Summary CRUD operations

#### Storage & Embeddings

- [X] T054 [US3] Create src/sage/services/storage.py with StorageService class that manages Postgres connections
- [X] T055 [US3] Implement store_video_metadata() method in StorageService to insert into youtube_videos table
- [X] T056 [US3] Implement store_transcript() method in StorageService to insert into transcripts table with timestamps
- [X] T057 [US3] Implement _generate_summary_embedding() helper to call embedding provider (e.g., OpenAI) and return vector
- [X] T058 [US3] Implement store_summary() method in StorageService to insert into summaries table and persist pgvector embedding
- [X] T059 [US3] Implement store_complete_entry() orchestration method in StorageService that calls all storage methods in correct order

#### Search Implementation

- [X] T060 [P] [US3] Create src/sage/services/search.py with SearchService class
- [X] T061 [US3] Implement postgres_keyword_search() method in SearchService using full-text search (to_tsvector, to_tsquery)
- [X] T062 [US3] Implement pgvector_semantic_search() method in SearchService using cosine similarity against stored embeddings
- [X] T063 [US3] Implement merge_search_results() method in SearchService to combine and rank keyword + vector results
- [X] T064 [US3] Implement hybrid_search() public method in SearchService that orchestrates keyword + vector search
- [X] T065 [US3] Implement filter_by_metadata() method in SearchService for date range, channel filtering

#### CLI Search Command

- [X] T066 [US3] Create search() Typer command in src/sage/cli/ingest_youtube.py with query, limit, and filter options
- [X] T067 [US3] Integrate SearchService into search() command with rich formatting of results
- [X] T068 [US3] Add --json flag to search() command for programmatic output
- [X] T069 [US3] Register search command in src/sage/cli/main.py

#### Batch Processing & Queue

- [X] T070 [P] [US3] Create src/sage/services/queue.py with in-memory Queue[QueueItem] using asyncio.Queue
- [X] T071 [US3] Implement add_to_queue() method in queue service to enqueue URLs with priority
- [X] T072 [US3] Implement process_queue() async method in queue service with rate limit token bucket algorithm
- [X] T073 [US3] Implement load_rate_limits() method in queue service to read from config/rate_limits.yaml
- [X] T074 [US3] Implement apply_rate_limit() method with exponential backoff and retry logic
- [X] T075 [US3] Implement get_queue_status() method returning queued, processing, completed counts
- [X] T076 [US3] Create ingest_youtube_batch() Typer command in src/sage/cli/ingest_youtube.py supporting --file and --urls options
- [X] T077 [US3] Integrate queue service into ingest_youtube_batch() command with progress tracking
- [X] T078 [US3] Create queue_status() Typer command in src/sage/cli/ingest_youtube.py to display current queue state
- [X] T079 [US3] Register batch and queue-status commands in src/sage/cli/main.py

#### Storage Integration into Main Command

- [X] T080 [US3] Integrate StorageService into ingest_youtube() command to persist transcript, summary, and metadata
- [X] T081 [US3] Add --tags flag processing to store manual keyword tags in summaries table
- [X] T082 [US3] Add --force flag handling to allow duplicate URL re-ingestion with new timestamp
- [X] T083 [US3] Update progress callbacks to include storage stage with percentage
- [X] T084 [US3] Display stored summary and embedding identifiers in success output (interactive and JSON modes)

**Checkpoint**: All user stories should now be independently functional - full pipeline working with search and batch processing

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T085 [P] Add comprehensive docstrings to all services (transcript.py, summarization.py, storage.py, search.py, queue.py)
- [X] T086 [P] Add comprehensive docstrings to all models (video.py, transcript.py, summary.py, queue.py)
- [X] T087 [P] Add type hints validation (ensure no `Any` types) across all modules
- [X] T088 Create README.md in project root with installation, configuration, and usage instructions
- [X] T089 [P] Add error handling improvements: retry logic for transient YouTube API failures in transcript service
- [X] T090 [P] Add logging statements with rich formatting for all major operations (download, transcribe, summarize, store)
- [X] T091 Add CLI usage examples to quickstart.md based on actual implemented commands
- [X] T092 Verify all CLI commands have proper --help text with examples
- [X] T093 Constitution compliance review (verify all principles from plan.md Constitution Check are met)
- [X] T094 Run full pipeline validation: ingest real YouTube video, search for it, verify all metadata correct

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion - No dependencies on other stories
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion - No dependencies on other stories (can use P1 transcript or test data)
- **User Story 3 (Phase 5)**: Depends on Foundational phase completion - Integrates with P1 and P2 but should be independently testable with mock data
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - Delivers transcript extraction MVP
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Can test with sample transcripts, doesn't need P1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Can test with mock data, integrates with P1+P2 when complete

### Within Each User Story

- **User Story 1**: Transcript service → CLI integration → Progress callbacks → Error handling
- **User Story 2**: Summary models → Summarization service → CLI integration → LangFuse tracing
- **User Story 3**: Database repos → Storage service → Embedding/vector integration → Search service → Queue service → Batch CLI commands

### Parallel Opportunities

- **Setup (T005-T010)**: All module initialization tasks can run in parallel
- **Foundational models (T014-T017)**: All Pydantic model files can be created in parallel
- **Foundational DB repos (T051-T053)**: All repository files can be created in parallel (within Phase 5)
- **Different user stories**: US1, US2, US3 can be worked on in parallel by different team members after Foundational phase
- **Within US3**: T051-T053 (repos), T060 (search service creation) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all parallelizable tasks for US1 together (marked with [P]):
Task T022: "Create src/sage/services/transcript.py with TranscriptService class structure"

# Then sequential tasks that depend on T022:
Task T023: "Implement get_transcript_from_captions() method"
Task T024: "Implement _download_video() method"
Task T025: "Implement _transcribe_with_whisper() fallback method"
# ...and so on
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Transcript extraction)
4. **STOP and VALIDATE**: Test `sage ingest-youtube URL` with multiple YouTube videos
5. Deploy/demo transcript extraction capability

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → **Deploy/Demo (MVP: Transcript extraction!)**
3. Add User Story 2 → Test independently → **Deploy/Demo (Now with summaries!)**
4. Add User Story 3 → Test independently → **Deploy/Demo (Full searchable memory!)**
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Transcript)
   - Developer B: User Story 2 (Summarization) - can work with sample transcripts
   - Developer C: User Story 3 (Storage & Search) - can work with mock data initially
3. Stories complete and integrate independently

---

## Task Summary

**Total Tasks**: 94

**Task Breakdown by Phase**:
- Setup (Phase 1): 10 tasks
- Foundational (Phase 2): 11 tasks  
- User Story 1 - Transcript (Phase 3): 15 tasks
- User Story 2 - Summary (Phase 4): 12 tasks
- User Story 3 - Storage & Search (Phase 5): 36 tasks
- Polish (Phase 6): 10 tasks

**Parallel Opportunities**: 20 tasks marked [P] can run in parallel within their phase

**Independent Test Criteria**:
- **US1**: `sage ingest-youtube URL` returns complete transcript with timestamps ✅
- **US2**: Summary generated with topics, speakers, takeaways in ≤300 words ✅
- **US3**: Store + search + batch processing all functional ✅

**Suggested MVP Scope**: Complete phases 1-3 (Setup + Foundational + US1) for working transcript extraction CLI

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Run `just test` frequently (tests to be added in future iteration if needed)
- Run `just format && just lint && just typecheck` before committing
- Use `just ci` for full quality check


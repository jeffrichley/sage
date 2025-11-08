# Feature Specification: YouTube Transcript & Memory Ingestion Pipeline

**Feature Branch**: `001-youtube-ingestion`  
**Created**: 2025-11-07  
**Status**: Draft  
**Input**: User description: "Build the YouTube → Transcript → Summary → Memory component for the Sage research toolkit"

## Clarifications

### Session 2025-11-07

- Q: What is your expected scale for stored videos and how long should data be retained? → A: Will NOT keep video files, only transcripts and summaries (text). Expect 1000+ videos to be processed. Keep indefinitely.
- Q: What level of processing status visibility do you need during video ingestion? → A: Detailed progress (stage + percentage complete for each stage). Implement using callbacks so progress can be shown or hidden based on context (CLI/TUI/headless).
- Q: What search method should be used for retrieving stored memory entries? → A: Hybrid (keyword + semantic search). Support both exact term matching and conceptual/semantic similarity for optimal research recall.
- Q: How should the system handle rate limits when processing multiple videos? → A: Queue with automatic throttling. Conservative approach to stay in good standing with YouTube and transcription service rate limits.
- Q: What metrics and observability do you need beyond basic logging? → A: No additional observability needed. Basic logging (attempts, successes, failures, errors) is sufficient for initial release.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - YouTube URL to Transcript (Priority: P1)

As a researcher, I want to supply a YouTube URL so that the system retrieves the audio or video and generates a full transcript that I can read and search through.

**Why this priority**: This is the foundational capability—without transcript extraction, the entire pipeline cannot function. It delivers immediate value by converting video content into searchable text.

**Independent Test**: Can be fully tested by providing a YouTube URL and verifying that a complete, accurate transcript is generated and returned. Delivers value even without summarization or storage by enabling researchers to quickly scan video content as text.

**Acceptance Scenarios**:

1. **Given** a valid YouTube URL for a public video, **When** I submit the URL to the system, **Then** the system downloads the audio/video and generates a complete transcript
2. **Given** a transcript is generated, **When** I review the output, **Then** the transcript is cleaned of timestamps and special characters, making it fully text-searchable
3. **Given** a YouTube video with multiple speakers, **When** the transcript is generated, **Then** the system captures all spoken content accurately
4. **Given** an invalid or private YouTube URL, **When** I submit it, **Then** the system returns a clear error message explaining the issue
5. **Given** multiple YouTube URLs are submitted for batch processing, **When** the system processes them, **Then** all URLs are queued and processed sequentially with automatic rate limit throttling and queue status visibility

---

### User Story 2 - Transcript to Concise Summary (Priority: P2)

As a researcher, I want the system to produce a concise summary of the transcript so that I can quickly grasp the key points without reading the entire transcript.

**Why this priority**: Summaries dramatically improve research efficiency by distilling hours of content into a few paragraphs. This is the value-multiplier on top of raw transcripts. Can be implemented independently after P1.

**Independent Test**: Can be fully tested by providing a transcript (either from P1 or a sample text) and verifying that a high-quality summary is generated with configurable length. Delivers standalone value for any text summarization task.

**Acceptance Scenarios**:

1. **Given** a complete transcript, **When** the system generates a summary, **Then** the summary is no more than 300 words (or user-configured length)
2. **Given** a summary is generated, **When** I review it, **Then** it highlights the main topics, identifies speaker(s) if mentioned, and captures key takeaways
3. **Given** a very short video (< 2 minutes), **When** a summary is requested, **Then** the system provides an appropriate summary without unnecessary padding
4. **Given** a technical research seminar transcript, **When** summarized, **Then** the summary preserves key technical terms and concepts accurately

---

### User Story 3 - Memory Storage with Metadata (Priority: P3)

As a researcher, I want the transcript and summary to be stored in my Sage memory system with comprehensive metadata so that I can search across all ingested content and quickly retrieve relevant information weeks or months later.

**Why this priority**: Storage enables long-term research workflows and knowledge accumulation. While critical for the overall vision, it can be developed after P1 and P2 deliver immediate value. Requires P1 and P2 outputs to function.

**Independent Test**: Can be fully tested by providing sample transcript/summary data and metadata, then verifying storage succeeds and subsequent searches return correct results. Delivers standalone value as a searchable knowledge base component.

**Acceptance Scenarios**:

1. **Given** a transcript and summary have been generated, **When** the system stores them, **Then** the memory entry includes: video title, channel name, publication date, YouTube URL, and ingest timestamp
2. **Given** memory entries are stored, **When** I search using either exact keywords (e.g., "MARL coordination") or conceptual queries (e.g., "multi-agent learning approaches"), **Then** the system returns matching memory entries ranked by relevance using hybrid search
3. **Given** a memory entry is being created, **When** the system analyzes the content, **Then** it automatically tags the entry with relevant keywords (e.g., speaker names, topics)
4. **Given** automatic tagging is complete, **When** I review tags, **Then** I have the option to manually add or override tags before finalizing storage
5. **Given** multiple videos on similar topics are ingested, **When** I search the memory, **Then** results include metadata that helps distinguish between entries (date, channel, title)

---

### Edge Cases

- **What happens when a YouTube video is very long (> 3 hours)?**  
  System should handle gracefully with progress indicators or time estimates. May need chunking for processing.

- **What happens when YouTube audio quality is poor or contains significant background noise?**  
  Transcript quality may be degraded; system should indicate confidence level or quality warnings.

- **What happens when a video has no spoken content (e.g., music-only video)?**  
  System should detect minimal speech and return appropriate message rather than empty/nonsense transcript.

- **What happens when a video is in a non-English language?**  
  System should either: (a) support multiple languages with language detection, or (b) clearly communicate English-only limitation.

- **What happens when the same YouTube URL is submitted multiple times?**  
  System should either: (a) detect duplicate and return existing entry, or (b) allow re-ingestion with timestamp differentiation.

- **What happens when YouTube API or services are temporarily unavailable?**  
  System should implement retry logic with exponential backoff and provide clear error messages about transient failures.

- **What happens when disk space for storage is insufficient?**  
  System should check available space before processing and fail gracefully with actionable error message.

- **What happens when multiple videos are submitted for batch processing?**  
  System should queue all URLs, process them sequentially with automatic rate limit throttling, and provide queue status visibility.

- **What happens when a rate limit is hit during batch processing?**  
  System should automatically apply exponential backoff, wait for rate limit reset, and continue processing without user intervention. Progress callbacks should indicate "waiting for rate limit reset".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a YouTube URL as input and validate that it is a properly formatted YouTube URL
- **FR-002**: System MUST download audio or video content from the provided YouTube URL for public videos
- **FR-003**: System MUST generate a complete transcript from the downloaded audio/video content
- **FR-004**: System MUST clean the transcript by removing timestamps, special characters, and formatting artifacts to produce text-searchable content
- **FR-005**: System MUST generate a concise summary of the transcript with configurable maximum length (default: 300 words)
- **FR-006**: Summary MUST identify and highlight: main topics, speaker names (if mentioned), and key takeaways
- **FR-007**: System MUST extract video metadata including: title, channel name, publication date, and URL
- **FR-008**: System MUST record an ingest timestamp when processing begins
- **FR-009**: System MUST store the transcript, summary, and all metadata in the Sage memory database as a single memory entry
- **FR-010**: System MUST automatically generate and assign keyword tags to memory entries based on content analysis
- **FR-011**: System MUST provide an option for manual tag override or addition before finalizing storage
- **FR-012**: System MUST support hybrid search combining keyword/full-text search with semantic/embedding-based search for memory entries, returning ranked results
- **FR-013**: Hybrid search MUST support both exact term matching (for known terminology) and conceptual similarity matching (for related concepts)
- **FR-014**: System MUST support filtering search results by metadata fields (date range, channel, etc.)
- **FR-015**: System MUST return clear, actionable error messages for: invalid URLs, private videos, network failures, and processing errors
- **FR-016**: System MUST log all ingestion attempts, successes, and failures for debugging and monitoring
- **FR-017**: System MUST provide detailed progress updates via callback mechanism including: current processing stage (downloading, transcribing, summarizing, storing) and percentage complete for each stage
- **FR-018**: Progress callback mechanism MUST allow callers to subscribe to updates or operate in silent mode without progress reporting
- **FR-019**: System MUST implement automatic rate limit handling with conservative throttling for YouTube API and transcription service calls
- **FR-020**: System MUST queue multiple video processing requests and automatically pace execution to respect rate limits
- **FR-021**: When rate limits are encountered, system MUST apply exponential backoff and transparently retry without user intervention
- **FR-022**: System MUST allow users to submit multiple YouTube URLs for batch processing, with queue status visibility

### Key Entities

- **YouTube Video Entry**: Represents a single ingested video with attributes: YouTube URL (unique identifier), video title, channel name, publication date, duration

- **Transcript**: The full text content extracted from a video with attributes: raw text content, cleaned text content (searchable), word count, language, confidence score (if available)

- **Summary**: A condensed version of the transcript with attributes: summary text (configurable max length), identified topics (list), identified speakers (list), key takeaways (list), generation timestamp

- **Memory Entry**: The stored representation in the Sage memory database with attributes: unique memory ID, associated YouTube Entry, associated Transcript, associated Summary, keyword tags (auto-generated and manual), ingest timestamp, relationships to other memory entries (future)

- **Keyword Tag**: Searchable metadata attached to memory entries with attributes: tag name, tag type (auto-generated vs manual), confidence/relevance score

- **Processing Status**: Real-time progress information with attributes: current stage (downloading/transcribing/summarizing/storing), stage progress percentage (0-100), overall progress percentage, estimated time remaining, error state (if failed)

- **Search Index**: Dual index structure for hybrid search with attributes: full-text keyword index (for exact matching), semantic embedding vectors (for conceptual similarity), relevance scoring weights, combined ranking algorithm

- **Processing Queue**: Manages batch video ingestion with attributes: queued URLs (list), current processing item, queue position, estimated completion time per item, rate limit state (remaining quota, reset time), retry count per item, failed items (with error reasons)

### Assumptions

- **Language Support**: Assume English-only transcription for initial release (can expand later)
- **YouTube Access**: Assume public YouTube videos only; no authentication for private/unlisted videos in this release
- **Audio Quality**: Assume reasonable audio quality; degraded quality will result in lower-accuracy transcripts
- **Storage Backend**: Assume a database backend is available for memory storage (specific technology TBD in planning phase)
- **Storage Scope**: Video files are downloaded temporarily for processing only and discarded after transcript extraction. Only transcripts (text), summaries (text), and metadata are persisted in the memory database
- **Data Volume**: System must support storage and search across 1000+ video entries (transcripts + summaries). Expect indefinite retention with no automatic data expiration
- **Processing Time**: Assume processing can be asynchronous with detailed status updates delivered via callback mechanism. Callbacks enable flexible UI implementations (CLI progress bars, TUI panels, headless/silent mode)
- **Network Availability**: Assume reliable network connection for YouTube API access
- **Rate Limiting**: Assume conservative rate limit handling with automatic queuing and throttling. System should err on the side of slower processing to maintain good standing with external services
- **Summarization Quality**: Assume AI-based summarization (specific model/service TBD in planning phase)
- **Keyword Extraction**: Assume automated keyword extraction using NLP techniques (specific approach TBD in planning phase)
- **Search Strategy**: Assume hybrid search implementation combining traditional full-text/keyword search with semantic embedding-based search. Specific embedding model and vector database selection TBD in planning phase
- **Duplicate Handling**: Assume duplicate detection by URL; re-ingestion creates new timestamped entry

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Researcher can submit a YouTube URL and receive a complete transcript and summary within 5 minutes for a typical 30-60 minute video
- **SC-002**: Transcript accuracy is sufficient that researcher can search for and find specific concepts or quotes mentioned in the video
- **SC-003**: Generated summaries contain the main topics and key takeaways, allowing researcher to determine relevance without reading full transcript
- **SC-004**: Researcher can search the memory database using either exact keywords or conceptual queries (hybrid search) and retrieve stored entries with 90%+ recall for relevant entries
- **SC-005**: Metadata (title, channel, date) is accurately captured for 100% of successfully processed videos
- **SC-006**: System supports storage and efficient search across 1000+ video entries without performance degradation or data loss
- **SC-007**: Researcher can complete the entire workflow (submit URL → receive confirmation → search and retrieve entry) in under 10 minutes total for a typical video
- **SC-008**: Automatically generated keyword tags include at least 70% of the manually-identified important concepts from the video

### Definition of Done

- All three user stories (P1, P2, P3) are implemented and pass acceptance scenarios
- Data schema for memory storage is defined, documented, and implemented
- Researcher (Jeff) can successfully ingest a real YouTube seminar video, receive transcript and summary, and later search and retrieve it by key concepts
- Error handling is implemented for all edge cases identified above
- Feature is code-reviewed and passes all quality checks per constitution
- Documentation is complete: data schema, API/CLI usage, error codes, and troubleshooting guide

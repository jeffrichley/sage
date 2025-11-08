-- 001_initial_schema.sql
-- Initial database schema for the Sage YouTube ingestion pipeline.

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS youtube_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_url TEXT NOT NULL UNIQUE,
    video_id VARCHAR(20) NOT NULL,
    video_title TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_id VARCHAR(50),
    publish_date TIMESTAMP,
    duration_seconds INTEGER,
    language VARCHAR(10) DEFAULT 'en',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
    raw_transcript_json JSONB,
    cleaned_transcript TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    transcript_source VARCHAR(50) NOT NULL,
    confidence_score REAL,
    has_timestamps BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES youtube_videos(id) ON DELETE CASCADE,
    transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    summary_word_count INTEGER NOT NULL,
    identified_topics TEXT[],
    identified_speakers TEXT[],
    key_takeaways TEXT[],
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    prompt_template TEXT,
    generation_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    generation_cost_usd REAL,
    generation_latency_seconds REAL,
    mem0_memory_id TEXT,
    keyword_tags TEXT[],
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- youtube_videos indexes
CREATE INDEX IF NOT EXISTS idx_youtube_videos_video_id ON youtube_videos(video_id);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_channel_id ON youtube_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_created_at ON youtube_videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_publish_date ON youtube_videos(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_title_fts
    ON youtube_videos USING GIN (to_tsvector('english', video_title));

-- transcripts indexes
CREATE INDEX IF NOT EXISTS idx_transcripts_video_id ON transcripts(video_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_source ON transcripts(transcript_source);
CREATE INDEX IF NOT EXISTS idx_transcripts_cleaned_fts
    ON transcripts USING GIN (to_tsvector('english', cleaned_transcript));

-- summaries indexes
CREATE INDEX IF NOT EXISTS idx_summaries_video_id ON summaries(video_id);
CREATE INDEX IF NOT EXISTS idx_summaries_transcript_id ON summaries(transcript_id);
CREATE INDEX IF NOT EXISTS idx_summaries_model ON summaries(model_name);
CREATE INDEX IF NOT EXISTS idx_summaries_summary_fts
    ON summaries USING GIN (to_tsvector('english', summary_text));
CREATE INDEX IF NOT EXISTS idx_summaries_topics ON summaries USING GIN (identified_topics);
CREATE INDEX IF NOT EXISTS idx_summaries_speakers ON summaries USING GIN (identified_speakers);
CREATE INDEX IF NOT EXISTS idx_summaries_keyword_tags ON summaries USING GIN (keyword_tags);

COMMIT;


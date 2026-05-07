-- Migration: Call recordings
-- Date: 2026-05-05
-- Stores the public URL of a recorded call audio file (uploaded to Supabase
-- Storage) alongside its format. Transcript entries gain an optional `t`
-- field (seconds since call start) so the admin UI can seek the player
-- when a message is clicked.

ALTER TABLE voice_call_logs
    ADD COLUMN IF NOT EXISTS recording_url    TEXT,
    ADD COLUMN IF NOT EXISTS recording_format TEXT;

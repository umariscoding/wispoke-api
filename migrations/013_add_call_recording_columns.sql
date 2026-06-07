-- Migration 013: Call recording columns on voice_call_logs
-- Date: 2026-06-07
--
-- The voice worker now records each call (LiveKit audio-only egress →
-- Supabase Storage) and stores the resulting object key + format on the call
-- log. The repository/service already read & write these fields, but no prior
-- migration guaranteed the columns exist (the v2 work in 010 only ALTERed the
-- table). This makes the schema match the code.
--
-- `recording_url` holds the STORAGE OBJECT KEY (e.g. "<company_id>/<call_log_id>.ogg"),
-- not a public URL — the bucket is private and the dashboard mints short-lived
-- signed URLs on demand.
--
-- Idempotent (IF NOT EXISTS) so it's safe to re-apply.

ALTER TABLE voice_call_logs
  ADD COLUMN IF NOT EXISTS recording_url TEXT,
  ADD COLUMN IF NOT EXISTS recording_format TEXT;

-- Migration 010: Voice AI v2 schema
-- Date: 2026-05-27
--
-- Rebuilds voice-agent persistence for the LiveKit Agents stack
-- (Deepgram Nova-3 STT, OpenAI/Anthropic LLM, ElevenLabs Flash v2.5 TTS).
-- The previous Pipecat/Gemini-Live stack and its provider columns are gone;
-- this migration drops the legacy fields and replaces them with a clean
-- provider abstraction.
--
-- All changes are idempotent (IF EXISTS / IF NOT EXISTS) so the file is safe
-- to re-apply.

-- ─────────────────────────────────────────────────────────────────
-- 1. voice_agent_settings — drop legacy columns, add provider abstraction
-- ─────────────────────────────────────────────────────────────────

ALTER TABLE voice_agent_settings
  DROP COLUMN IF EXISTS twilio_phone_number,
  DROP COLUMN IF EXISTS twilio_account_sid,
  DROP COLUMN IF EXISTS twilio_auth_token;

-- voice_provider was an enum-checked column (deepgram | cartesia); drop the
-- constraint first so the column drop doesn't fail on its dependency.
ALTER TABLE voice_agent_settings
  DROP CONSTRAINT IF EXISTS voice_agent_settings_voice_provider_check;

ALTER TABLE voice_agent_settings
  DROP COLUMN IF EXISTS voice_provider;

ALTER TABLE voice_agent_settings
  ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Europe/Copenhagen',
  ADD COLUMN IF NOT EXISTS stt_provider TEXT NOT NULL DEFAULT 'deepgram',
  ADD COLUMN IF NOT EXISTS llm_provider TEXT NOT NULL DEFAULT 'openai',
  ADD COLUMN IF NOT EXISTS tts_provider TEXT NOT NULL DEFAULT 'elevenlabs';

-- CHECK constraints (added separately so ADD COLUMN IF NOT EXISTS stays clean)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'voice_agent_settings_stt_provider_check'
  ) THEN
    ALTER TABLE voice_agent_settings
      ADD CONSTRAINT voice_agent_settings_stt_provider_check
      CHECK (stt_provider IN ('deepgram', 'speechmatics'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'voice_agent_settings_llm_provider_check'
  ) THEN
    ALTER TABLE voice_agent_settings
      ADD CONSTRAINT voice_agent_settings_llm_provider_check
      CHECK (llm_provider IN ('openai', 'anthropic'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'voice_agent_settings_tts_provider_check'
  ) THEN
    ALTER TABLE voice_agent_settings
      ADD CONSTRAINT voice_agent_settings_tts_provider_check
      CHECK (tts_provider IN ('elevenlabs', 'cartesia', 'azure'));
  END IF;
END $$;

-- Migrate stale defaults from Gemini-Live era to the new stack
UPDATE voice_agent_settings
  SET voice_model = '21m00Tcm4TlvDq8ikWAM'   -- ElevenLabs "Rachel"
  WHERE voice_model LIKE 'gemini-%' OR voice_model = 'aura-asteria-en';

UPDATE voice_agent_settings
  SET llm_model = 'gpt-4o'
  WHERE llm_model LIKE 'gemini-%' OR llm_model IS NULL;

-- Update the column-level default so new rows get the new defaults
ALTER TABLE voice_agent_settings
  ALTER COLUMN voice_model SET DEFAULT '21m00Tcm4TlvDq8ikWAM',
  ALTER COLUMN llm_model SET DEFAULT 'gpt-4o';

-- ─────────────────────────────────────────────────────────────────
-- 2. voice_call_logs — clear legacy rows, add v2 columns
-- ─────────────────────────────────────────────────────────────────

-- Clear stale rows from the Gemini-Live test era (user authorized)
DELETE FROM voice_call_logs;

ALTER TABLE voice_call_logs
  ADD COLUMN IF NOT EXISTS room_name TEXT,
  ADD COLUMN IF NOT EXISTS outcome TEXT,
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en',
  ADD COLUMN IF NOT EXISTS llm_model TEXT,
  ADD COLUMN IF NOT EXISTS latency_metrics JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'voice_call_logs_outcome_check'
  ) THEN
    ALTER TABLE voice_call_logs
      ADD CONSTRAINT voice_call_logs_outcome_check
      CHECK (outcome IS NULL OR outcome IN ('booked', 'no_booking', 'failed', 'handoff', 'aborted'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_voice_call_logs_room ON voice_call_logs(room_name);
CREATE INDEX IF NOT EXISTS idx_voice_call_logs_outcome ON voice_call_logs(company_id, outcome);

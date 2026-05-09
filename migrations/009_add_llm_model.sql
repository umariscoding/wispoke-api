-- Migration: Per-tenant Gemini Live model selection
-- Date: 2026-05-09
-- The dashboard's voice settings page now lets each business pick which
-- Gemini Live model to use (recommended vs experimental). Default mirrors
-- DEFAULT_GEMINI_LIVE_MODEL in app/features/voice_agent/pipeline.py.

ALTER TABLE voice_agent_settings
    ADD COLUMN IF NOT EXISTS llm_model TEXT
        DEFAULT 'gemini-2.5-flash-native-audio-preview-12-2025';

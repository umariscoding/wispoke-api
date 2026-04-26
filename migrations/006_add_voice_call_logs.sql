-- Migration: Voice call logs (transcripts + linked booking outcome)
-- Date: 2026-04-26
-- Persists every voice-agent conversation: full transcript JSON, when the call
-- happened, where it came from (browser test vs Twilio), and which appointment
-- (if any) was created during the call.

CREATE TABLE IF NOT EXISTS voice_call_logs (
    call_log_id     TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    source          TEXT NOT NULL DEFAULT 'browser' CHECK (source IN ('browser', 'twilio')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    duration_sec    INTEGER,
    -- Transcript: array of {role: "user"|"assistant"|"system"|"tool", content: "..."}
    transcript      JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- If a booking happened during this call, link it. SET NULL on appointment delete
    -- so the transcript history is preserved even if the appointment row is removed.
    appointment_id  TEXT REFERENCES appointments(appointment_id) ON DELETE SET NULL,
    -- Caller phone (Twilio) or auth subject (browser test) — useful for support/debug.
    caller_ref      TEXT
);

CREATE INDEX IF NOT EXISTS idx_call_logs_company ON voice_call_logs(company_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_started ON voice_call_logs(company_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_call_logs_appt ON voice_call_logs(appointment_id);

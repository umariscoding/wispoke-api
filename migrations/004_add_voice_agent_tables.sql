-- Migration: Add voice agent, availability, and appointments tables
-- Date: 2026-04-19

-- ============================================================
-- 1. Availability Schedules (recurring weekly slots)
-- ============================================================
CREATE TABLE IF NOT EXISTS availability_schedules (
    schedule_id   TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    day_of_week   SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),  -- 0=Sunday, 6=Saturday
    start_time    TIME NOT NULL,
    end_time      TIME NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_time_range CHECK (end_time > start_time)
);

CREATE INDEX IF NOT EXISTS idx_avail_schedules_company ON availability_schedules(company_id);
CREATE INDEX IF NOT EXISTS idx_avail_schedules_day ON availability_schedules(company_id, day_of_week);

-- ============================================================
-- 2. Availability Exceptions (date-specific overrides)
-- ============================================================
CREATE TABLE IF NOT EXISTS availability_exceptions (
    exception_id  TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    exception_date DATE NOT NULL,
    is_available  BOOLEAN NOT NULL DEFAULT FALSE,  -- false=blocked, true=extra availability
    start_time    TIME,          -- NULL if blocked entire day
    end_time      TIME,          -- NULL if blocked entire day
    reason        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_exception_time CHECK (
        (is_available = FALSE AND start_time IS NULL AND end_time IS NULL) OR
        (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
    )
);

CREATE INDEX IF NOT EXISTS idx_avail_exceptions_company ON availability_exceptions(company_id);
CREATE INDEX IF NOT EXISTS idx_avail_exceptions_date ON availability_exceptions(company_id, exception_date);

-- ============================================================
-- 3. Appointments
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    company_id     TEXT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    caller_name    TEXT,
    caller_phone   TEXT,
    caller_email   TEXT,
    scheduled_date DATE NOT NULL,
    start_time     TIME NOT NULL,
    end_time       TIME NOT NULL,
    duration_min   INTEGER NOT NULL DEFAULT 30,
    service_type   TEXT,
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
    source         TEXT NOT NULL DEFAULT 'voice_agent' CHECK (source IN ('voice_agent', 'manual', 'web')),
    call_sid       TEXT,            -- Twilio call SID reference
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_appt_time CHECK (end_time > start_time)
);

CREATE INDEX IF NOT EXISTS idx_appointments_company ON appointments(company_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(company_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(company_id, status);

-- ============================================================
-- 4. Voice Agent Settings
-- ============================================================
CREATE TABLE IF NOT EXISTS voice_agent_settings (
    settings_id       TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL UNIQUE REFERENCES companies(company_id) ON DELETE CASCADE,
    is_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    twilio_phone_number TEXT,
    twilio_account_sid  TEXT,
    twilio_auth_token   TEXT,
    greeting_message  TEXT NOT NULL DEFAULT 'Hello! Thank you for calling. How can I help you today?',
    business_name     TEXT,
    business_type     TEXT,           -- e.g., 'plumber', 'electrician', 'dentist'
    appointment_duration_min INTEGER NOT NULL DEFAULT 30,
    voice_provider    TEXT NOT NULL DEFAULT 'deepgram' CHECK (voice_provider IN ('deepgram', 'cartesia')),
    voice_model       TEXT NOT NULL DEFAULT 'aura-asteria-en',
    language          TEXT NOT NULL DEFAULT 'en',
    system_prompt     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voice_settings_company ON voice_agent_settings(company_id);

-- Migration 011: phone_numbers pool for inbound voice agent
-- Date: 2026-05-30
--
-- A small inventory of PSTN numbers (Twilio today, provider-agnostic schema for
-- future Telnyx/EU expansion). Companies claim one during onboarding; inbound
-- calls to that number route via SIP → LiveKit → wispoke-booking-agent with
-- the resolved company_id.
--
-- Trial-account starting state: insert 1 row manually after migrating, then
-- assign it to a test company. Pool growth + selection UI lands in phase 2.
--
-- Idempotent (IF NOT EXISTS) so re-running is safe.

CREATE TABLE IF NOT EXISTS phone_numbers (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    e164                 TEXT NOT NULL UNIQUE,                       -- '+14155551234'
    country              TEXT NOT NULL,                              -- ISO 3166-1 alpha-2: 'US', 'DK', 'SE', ...
    region_label         TEXT,                                       -- human label for the picker: 'San Francisco 415', 'Toll-free 800'
    provider             TEXT NOT NULL DEFAULT 'twilio',             -- 'twilio' | 'telnyx' | ...
    provider_sid         TEXT,                                       -- Twilio PNxxxx... — useful for releasing later
    assigned_company_id  TEXT REFERENCES companies(company_id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'available',          -- 'available' | 'assigned' | 'released'
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at          TIMESTAMPTZ
);

-- CHECK constraints added separately so re-runs that already created the table
-- can still pick up new constraints (without DROP/CREATE which would lose rows).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'phone_numbers_provider_check'
  ) THEN
    ALTER TABLE phone_numbers
      ADD CONSTRAINT phone_numbers_provider_check
      CHECK (provider IN ('twilio', 'telnyx'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'phone_numbers_status_check'
  ) THEN
    ALTER TABLE phone_numbers
      ADD CONSTRAINT phone_numbers_status_check
      CHECK (status IN ('available', 'assigned', 'released'));
  END IF;

  -- A number must be assigned to a company iff status='assigned'. Catches the
  -- bug where you flip status without nulling the company_id (or vice versa)
  -- and the dispatch rule starts routing calls to an unintended tenant.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'phone_numbers_assignment_consistency'
  ) THEN
    ALTER TABLE phone_numbers
      ADD CONSTRAINT phone_numbers_assignment_consistency
      CHECK (
        (status = 'assigned' AND assigned_company_id IS NOT NULL AND assigned_at IS NOT NULL)
        OR (status <> 'assigned' AND assigned_company_id IS NULL)
      );
  END IF;
END $$;

-- Hot lookup: SIP dispatch hits this on every inbound call to resolve tenant.
CREATE INDEX IF NOT EXISTS idx_phone_numbers_e164 ON phone_numbers(e164);

-- For "show me my available pool" admin queries.
CREATE INDEX IF NOT EXISTS idx_phone_numbers_status_country
  ON phone_numbers(status, country) WHERE status = 'available';

-- A company should normally hold one number. Not enforced as UNIQUE (a tenant
-- could justifiably hold a local + a toll-free), but this partial index keeps
-- lookups fast when the dashboard shows "your number".
CREATE INDEX IF NOT EXISTS idx_phone_numbers_company
  ON phone_numbers(assigned_company_id) WHERE assigned_company_id IS NOT NULL;

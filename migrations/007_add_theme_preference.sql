-- Migration: Theme preference per company (light / dark / system)
-- Date: 2026-05-02
-- Stores the user's theme override. NULL is treated as 'system' by the client,
-- but we default to 'system' explicitly so the value is always meaningful.

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS theme_preference TEXT NOT NULL DEFAULT 'system'
    CHECK (theme_preference IN ('light', 'dark', 'system'));

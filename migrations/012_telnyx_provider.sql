-- Migration 012: switch telephony default provider to Telnyx
-- Date: 2026-05-31
--
-- Twilio is removed. Numbers now come from Telnyx and route into LiveKit via an
-- FQDN SIP Connection (no webhook). The Telnyx number/order id is stored in the
-- existing provider_sid column. The provider CHECK from migration 011 already
-- allows 'telnyx', so we only flip the default here.
ALTER TABLE phone_numbers
    ALTER COLUMN provider SET DEFAULT 'telnyx';

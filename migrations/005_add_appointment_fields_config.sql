-- Add configurable appointment fields to voice_agent_settings
ALTER TABLE voice_agent_settings
ADD COLUMN IF NOT EXISTS appointment_fields JSONB NOT NULL DEFAULT '["name", "phone"]';

-- appointment_fields is an array of field keys the agent should collect
-- Options: "name", "phone", "email", "address", "service_type", "notes"

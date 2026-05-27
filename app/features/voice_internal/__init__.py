"""
Voice Internal — service-to-service endpoints used by the wispoke-voice worker.

Separated from `voice_agent/` (dashboard-facing) because the auth boundary is
different: these routes require a service JWT, not a user/company token.
Keeping them in their own module makes the boundary visible in the URL tree
(/voice/internal/*) and prevents accidental mounting under user auth.
"""

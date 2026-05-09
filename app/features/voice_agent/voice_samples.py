"""
On-demand voice sample generation + caching for the dashboard's voice picker.

Generates a one-shot ~3-second sample via Gemini's TTS model, wraps it as WAV,
uploads to a public Supabase Storage bucket, returns the public URL. Cached so
each voice is generated exactly once across the project lifetime.
"""

import logging
from typing import Optional

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.features.voice_agent.recording_storage import encode_pcm_to_wav

logger = logging.getLogger("wispoke.voice.samples")

SAMPLES_BUCKET = "voice-samples"

# The catalog the dashboard exposes. Anything outside this set is rejected by
# the endpoint to prevent arbitrary TTS calls (and runaway quota).
GEMINI_VOICE_NAMES = {"Aoede", "Charon", "Fenrir", "Kore", "Puck"}

# What each voice says in its sample. Kept short to minimize TTS cost.
_SAMPLE_LINE = "Hi, I'm {name}. I'd love to help you book your next appointment."

# Gemini's TTS model emits 24 kHz signed-16-bit PCM mono.
_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_TTS_SAMPLE_RATE = 24000


def _ensure_bucket(supabase) -> None:
    try:
        supabase.storage.get_bucket(SAMPLES_BUCKET)
    except Exception:
        try:
            supabase.storage.create_bucket(
                SAMPLES_BUCKET,
                options={
                    "public": True,
                    "file_size_limit": 1048576,  # 1 MB — samples are tiny
                    "allowed_mime_types": ["audio/wav", "audio/x-wav"],
                },
            )
        except Exception:
            logger.debug("voice-samples bucket creation skipped (may exist)")


def _generate_sample_pcm(voice_name: str) -> Optional[bytes]:
    """Call Gemini TTS once for the given voice. Returns raw PCM, or None."""
    if not app_settings.gemini_api_key:
        logger.warning("Cannot generate voice sample: GEMINI_API_KEY unset")
        return None
    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=app_settings.gemini_api_key)
        response = client.models.generate_content(
            model=_TTS_MODEL,
            contents=_SAMPLE_LINE.format(name=voice_name),
            config=gtypes.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=gtypes.SpeechConfig(
                    voice_config=gtypes.VoiceConfig(
                        prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        )
                    )
                ),
            ),
        )
        # The audio comes back as inline_data on the first candidate's part.
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
        logger.warning("Gemini TTS returned no audio for voice=%s", voice_name)
        return None
    except Exception:
        logger.exception("Failed to generate Gemini TTS sample for voice=%s", voice_name)
        return None


def get_or_create_sample_bytes(voice_name: str) -> Optional[bytes]:
    """Return the WAV bytes for the sample, generating + uploading if needed.

    Uses Supabase Storage as a backing cache so we don't regenerate across
    process restarts, but the endpoint streams the bytes directly to the
    browser to avoid any cross-origin redirect quirks with `<audio>`.
    """
    if voice_name not in GEMINI_VOICE_NAMES:
        return None

    supabase = get_db()
    _ensure_bucket(supabase)

    file_path = f"{voice_name.lower()}.wav"

    # Cache hit: download the existing file from the bucket.
    try:
        cached = supabase.storage.from_(SAMPLES_BUCKET).download(file_path)
        if cached:
            return cached
    except Exception:
        logger.debug("Sample cache miss for %s — generating", voice_name)

    # Cache miss: generate via Gemini TTS, upload, return bytes.
    pcm = _generate_sample_pcm(voice_name)
    if not pcm:
        return None

    try:
        wav = encode_pcm_to_wav(pcm, sample_rate=_TTS_SAMPLE_RATE, num_channels=1)
        try:
            supabase.storage.from_(SAMPLES_BUCKET).upload(
                file_path,
                wav,
                file_options={"content-type": "audio/wav", "upsert": "true"},
            )
        except Exception:
            try:
                supabase.storage.from_(SAMPLES_BUCKET).remove([file_path])
            except Exception:
                pass
            try:
                supabase.storage.from_(SAMPLES_BUCKET).upload(
                    file_path,
                    wav,
                    file_options={"content-type": "audio/wav"},
                )
            except Exception:
                logger.exception("Failed to upload voice sample for %s", voice_name)
                # Even if upload fails, we still have the WAV bytes — return
                # them so the user gets a working preview this turn.
        return wav
    except Exception:
        logger.exception("Failed to encode voice sample for %s", voice_name)
        return None

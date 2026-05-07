"""
Supabase Storage helper for call recordings.

Mirrors `app.services.document_processing.storage` but uploads to a separate
public bucket so recordings can be played by an HTML5 <audio> tag in the
admin dashboard without per-request signing.
"""

import io
import logging
import wave
from typing import Optional

from app.core.database import get_db

logger = logging.getLogger("wispoke.voice.recording")

RECORDINGS_BUCKET = "call-recordings"


def _ensure_bucket(supabase) -> None:
    try:
        supabase.storage.get_bucket(RECORDINGS_BUCKET)
    except Exception:
        try:
            supabase.storage.create_bucket(
                RECORDINGS_BUCKET,
                options={
                    "public": True,
                    "file_size_limit": 104857600,  # 100 MB — long calls
                    "allowed_mime_types": ["audio/wav", "audio/x-wav", "audio/mpeg"],
                },
            )
        except Exception:
            logger.debug("Recording bucket creation skipped (may already exist)")


def encode_pcm_to_wav(pcm: bytes, sample_rate: int, num_channels: int = 1) -> bytes:
    """Wrap raw 16-bit signed PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(num_channels)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    buf.seek(0)
    return buf.read()


def upload_recording(
    company_id: str,
    call_log_id: str,
    wav_bytes: bytes,
) -> Optional[str]:
    """Upload a call recording WAV to Supabase Storage; return the public URL.

    Returns None on failure — recording is best-effort and must never block
    finalization of the call log itself.
    """
    if not wav_bytes:
        return None
    try:
        supabase = get_db()
        _ensure_bucket(supabase)

        file_path = f"{company_id}/{call_log_id}.wav"
        try:
            supabase.storage.from_(RECORDINGS_BUCKET).upload(
                file_path,
                wav_bytes,
                file_options={"content-type": "audio/wav", "upsert": "true"},
            )
        except Exception:
            try:
                supabase.storage.from_(RECORDINGS_BUCKET).remove([file_path])
            except Exception:
                logger.debug("Could not remove existing recording at %s", file_path)
            supabase.storage.from_(RECORDINGS_BUCKET).upload(
                file_path,
                wav_bytes,
                file_options={"content-type": "audio/wav"},
            )

        return supabase.storage.from_(RECORDINGS_BUCKET).get_public_url(file_path)
    except Exception:
        logger.exception("Failed to upload call recording %s", call_log_id)
        return None

"""
Voice call log persistence — transcripts + booking outcome.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import db, generate_id

logger = logging.getLogger("wispoke.voice.call_log")


def create_call_log(
    company_id: str,
    *,
    source: str = "browser",
    caller_ref: Optional[str] = None,
) -> str:
    """Open a new call log row. Returns its id so we can update it on disconnect."""
    call_log_id = generate_id()
    try:
        db.table("voice_call_logs").insert(
            {
                "call_log_id": call_log_id,
                "company_id": company_id,
                "source": source,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "transcript": [],
                "caller_ref": caller_ref,
            }
        ).execute()
    except Exception:
        # Migration may not be applied yet; don't crash the call.
        logger.exception("voice_call_logs insert failed (migration 006 missing?)")
    return call_log_id


def list_call_logs(
    company_id: str,
    *,
    limit: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return a page of call logs (newest first) plus the total row count.

    Returns: {"items": [...], "total": int}
    """
    try:
        res = (
            db.table("voice_call_logs")
            .select("*", count="exact")
            .eq("company_id", company_id)
            .order("started_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        total = res.count if res.count is not None else len(res.data or [])
        return {"items": res.data or [], "total": total}
    except Exception:
        logger.exception("voice_call_logs list failed (migration 006 missing?)")
        return {"items": [], "total": 0}


def finalize_call_log(
    call_log_id: str,
    *,
    transcript: List[Dict[str, Any]],
    started_at: datetime,
    appointment_id: Optional[str] = None,
) -> None:
    """Close out a call log with the final transcript + linked booking."""
    try:
        ended_at = datetime.now(timezone.utc)
        duration_sec = int((ended_at - started_at).total_seconds())
        update: Dict[str, Any] = {
            "ended_at": ended_at.isoformat(),
            "duration_sec": duration_sec,
            "transcript": transcript,
        }
        if appointment_id:
            update["appointment_id"] = appointment_id
        db.table("voice_call_logs").update(update).eq("call_log_id", call_log_id).execute()
    except Exception:
        logger.exception("voice_call_logs finalize failed")

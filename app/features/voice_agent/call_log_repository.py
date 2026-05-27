"""
Voice call log persistence (v2 schema — see migration 010).

Two write paths:
- `create_call_log` opens a row when the agent starts a session
- `finalize_call_log` closes it on disconnect with transcript + outcome

One read path used by the dashboard's calls page:
- `list_call_logs` (paginated, newest first)

All errors are swallowed and logged — a failing call_log write must never
crash an active voice session.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import db, generate_id

logger = logging.getLogger("wispoke.voice.call_log")


def create_call_log(
    company_id: str,
    *,
    room_name: str,
    source: str = "browser",
    language: str = "en",
    llm_model: Optional[str] = None,
    caller_ref: Optional[str] = None,
) -> str:
    """Open a new call log row. Returns its id so the caller can finalize it later."""
    call_log_id = generate_id()
    try:
        db.table("voice_call_logs").insert(
            {
                "call_log_id": call_log_id,
                "company_id": company_id,
                "room_name": room_name,
                "source": source,
                "language": language,
                "llm_model": llm_model,
                "caller_ref": caller_ref,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "transcript": [],
                "latency_metrics": {},
            }
        ).execute()
    except Exception:
        logger.exception("voice_call_logs insert failed for company=%s", company_id)
    return call_log_id


def list_call_logs(
    company_id: str,
    *,
    limit: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return one page of call logs (newest first) + total row count.

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
        logger.exception("voice_call_logs list failed for company=%s", company_id)
        return {"items": [], "total": 0}


def finalize_call_log(
    call_log_id: str,
    *,
    transcript: List[Dict[str, Any]],
    outcome: Optional[str],
    started_at: Optional[datetime] = None,
    appointment_id: Optional[str] = None,
    latency_metrics: Optional[Dict[str, Any]] = None,
    recording_url: Optional[str] = None,
    recording_format: Optional[str] = None,
) -> None:
    """Close out a call log with transcript + linked booking + metrics.

    `started_at` is optional — if provided we compute `duration_sec` so the
    dashboard can render call length without a second round-trip. If omitted,
    duration is left null and the FE falls back to "—".
    """
    try:
        ended_at = datetime.now(timezone.utc)
        update: Dict[str, Any] = {
            "ended_at": ended_at.isoformat(),
            "transcript": transcript,
        }
        if started_at is not None:
            update["duration_sec"] = max(0, int((ended_at - started_at).total_seconds()))
        if outcome is not None:
            update["outcome"] = outcome
        if appointment_id is not None:
            update["appointment_id"] = appointment_id
        if latency_metrics is not None:
            update["latency_metrics"] = latency_metrics
        if recording_url is not None:
            update["recording_url"] = recording_url
        if recording_format is not None:
            update["recording_format"] = recording_format
        db.table("voice_call_logs").update(update).eq("call_log_id", call_log_id).execute()
    except Exception:
        logger.exception("voice_call_logs finalize failed for call_log_id=%s", call_log_id)

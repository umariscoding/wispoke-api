"""
Voice Agent — database operations.
"""

import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

from app.core.database import db, generate_id

logger = logging.getLogger("wispoke.voice.repo")

# Cached set of column names actually present on `voice_agent_settings` —
# discovered lazily on first read. Lets us silently drop fields that the
# table doesn't have yet (e.g. when a migration is pending) instead of
# returning a 500 from a Postgres "column does not exist" error.
_KNOWN_COLUMNS: Optional[Set[str]] = None


def _discover_columns() -> Set[str]:
    global _KNOWN_COLUMNS
    if _KNOWN_COLUMNS is not None:
        return _KNOWN_COLUMNS
    try:
        res = db.table("voice_agent_settings").select("*").limit(1).execute()
        if res.data:
            _KNOWN_COLUMNS = set(res.data[0].keys())
        else:
            # Table exists but is empty — fall back to a known-good baseline
            # and let the upsert add new columns naturally; if a write fails
            # we'll re-discover from the error path below.
            _KNOWN_COLUMNS = set()
    except Exception:
        _KNOWN_COLUMNS = set()
    return _KNOWN_COLUMNS


def get_settings(company_id: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("voice_agent_settings")
        .select("*")
        .eq("company_id", company_id)
        .execute()
    )
    if res.data:
        # Refresh column cache from a real row.
        global _KNOWN_COLUMNS
        _KNOWN_COLUMNS = set(res.data[0].keys())
        return res.data[0]
    return None


def get_settings_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("voice_agent_settings")
        .select("*")
        .eq("twilio_phone_number", phone_number)
        .eq("is_enabled", True)
        .execute()
    )
    return res.data[0] if res.data else None


def upsert_settings(company_id: str, **kwargs: Any) -> Dict[str, Any]:
    existing = get_settings(company_id)

    data = {k: v for k, v in kwargs.items() if v is not None}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Filter out columns that don't exist on this table (e.g. pending migrations).
    cols = _discover_columns()
    if cols:
        unknown = [k for k in data if k not in cols and k not in {"settings_id", "company_id"}]
        if unknown:
            logger.warning(
                "voice_agent_settings: dropping unknown columns from upsert "
                "(missing migration?): %s",
                unknown,
            )
            for k in unknown:
                data.pop(k, None)

    if existing:
        res = (
            db.table("voice_agent_settings")
            .update(data)
            .eq("company_id", company_id)
            .execute()
        )
        return res.data[0]
    else:
        data["settings_id"] = generate_id()
        data["company_id"] = company_id
        res = db.table("voice_agent_settings").insert(data).execute()
        return res.data[0]

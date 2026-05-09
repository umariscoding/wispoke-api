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


_PGRST_MISSING_COLUMN = "PGRST204"


def _classify_error(e: Exception) -> tuple[str, str]:
    """Return (postgrest_code, message) regardless of how supabase-py wrapped it.

    `postgrest.APIError` exposes `.code`/`.message` as attributes; some versions
    only put them inside `.json()` or the str representation (which itself may
    be JSON). Be liberal about extraction so the retry path is reliable across
    library versions.
    """
    import json as _json

    code = (getattr(e, "code", "") or "").strip()
    message = (getattr(e, "message", "") or "").strip()
    # Some wrappers stash the dict on .args[0]
    if not code and getattr(e, "args", None):
        first = e.args[0]
        if isinstance(first, dict):
            code = code or str(first.get("code", "")).strip()
            message = message or str(first.get("message", "")).strip()
        elif isinstance(first, str) and first.strip().startswith("{"):
            try:
                obj = _json.loads(first)
                code = code or str(obj.get("code", "")).strip()
                message = message or str(obj.get("message", "")).strip()
            except Exception:
                pass
    raw = str(e)
    if not code or not message:
        try:
            obj = _json.loads(raw)
            code = code or str(obj.get("code", "")).strip()
            message = message or str(obj.get("message", "")).strip()
        except Exception:
            pass
    return code, message or raw


def _execute_with_column_drop(write_fn, data: Dict[str, Any], max_retries: int = 4):
    """Run a write; on missing-column errors, drop the offending column and retry.

    Lets the dashboard ship a new field (e.g. `llm_model`) before the matching
    migration is applied — instead of 500-ing, the server silently ignores the
    unknown column and persists the rest.
    """
    global _KNOWN_COLUMNS
    import re

    attempt = 0
    while True:
        try:
            return write_fn(data)
        except Exception as e:
            code, message = _classify_error(e)
            raw = str(e)
            is_missing_column = (
                code == _PGRST_MISSING_COLUMN
                or _PGRST_MISSING_COLUMN in raw
                or ("Could not find" in (message + raw) and "column" in (message + raw))
            )
            if not is_missing_column or attempt >= max_retries:
                raise
            # PostgREST: "Could not find the 'foo' column of 'voice_agent_settings'"
            m = re.search(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+column", message + " " + raw)
            if not m:
                logger.warning(
                    "voice_agent_settings: missing-column error but couldn't "
                    "extract column name from %r — re-raising.",
                    message or raw,
                )
                raise
            bad = m.group(1)
            if bad not in data:
                logger.warning(
                    "voice_agent_settings: missing-column %r not in payload — "
                    "re-raising to surface real issue.",
                    bad,
                )
                raise
            logger.warning(
                "voice_agent_settings: column %r missing (PGRST204) — dropping "
                "and retrying. Apply migrations/009_add_llm_model.sql to enable.",
                bad,
            )
            data.pop(bad, None)
            if _KNOWN_COLUMNS is not None:
                _KNOWN_COLUMNS.discard(bad)
            attempt += 1


def upsert_settings(company_id: str, **kwargs: Any) -> Dict[str, Any]:
    existing = get_settings(company_id)

    data = {k: v for k, v in kwargs.items() if v is not None}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Pre-filter known-bad columns from the cached schema (saves a round trip).
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
        def _update(d):
            return (
                db.table("voice_agent_settings")
                .update(d)
                .eq("company_id", company_id)
                .execute()
                .data[0]
            )
        return _execute_with_column_drop(_update, data)
    else:
        data["settings_id"] = generate_id()
        data["company_id"] = company_id

        def _insert(d):
            return db.table("voice_agent_settings").insert(d).execute().data[0]
        return _execute_with_column_drop(_insert, data)

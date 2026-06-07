"""
phone_numbers — DB access for the inbound number pool.

The hot path is `find_by_e164`: LiveKit's SIP dispatch (via the worker) hits it
on every inbound call to resolve which tenant owns the dialed number. Keep it
trivial — one indexed lookup, no joins.

Pool management (claim/release) lives here too but isn't wired to a router yet;
phase 2 adds the admin endpoints for the Telnyx number pool.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import db


def find_by_e164(e164: str) -> Optional[Dict[str, Any]]:
    """Return the row for this E.164 number, or None if not in the pool."""
    res = (
        db.table("phone_numbers")
        .select("*")
        .eq("e164", e164)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def list_available(country: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Numbers free to be claimed in onboarding."""
    q = db.table("phone_numbers").select("*").eq("status", "available")
    if country:
        q = q.eq("country", country.upper())
    return q.order("created_at").limit(limit).execute().data or []


def list_for_company(company_id: str) -> List[Dict[str, Any]]:
    return (
        db.table("phone_numbers")
        .select("*")
        .eq("assigned_company_id", company_id)
        .eq("status", "assigned")
        .execute()
        .data
        or []
    )


def claim(number_id: str, company_id: str) -> Optional[Dict[str, Any]]:
    """Assign an available number to a company.

    Returns None if the number isn't currently `available` — the caller should
    treat that as "someone else claimed it first" and reshow the picker.
    """
    now = datetime.now(timezone.utc).isoformat()
    res = (
        db.table("phone_numbers")
        .update({
            "assigned_company_id": company_id,
            "status": "assigned",
            "assigned_at": now,
        })
        .eq("id", number_id)
        .eq("status", "available")  # optimistic guard against a race
        .execute()
    )
    return res.data[0] if res.data else None


def release(number_id: str) -> Optional[Dict[str, Any]]:
    """Unassign a number back to the pool (e.g. tenant churn)."""
    res = (
        db.table("phone_numbers")
        .update({
            "assigned_company_id": None,
            "status": "available",
            "assigned_at": None,
        })
        .eq("id", number_id)
        .execute()
    )
    return res.data[0] if res.data else None


def insert(
    *,
    e164: str,
    country: str,
    region_label: Optional[str] = None,
    provider: str = "telnyx",
    provider_sid: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a freshly purchased number to the pool as 'available'."""
    row = {
        "e164": e164,
        "country": country.upper(),
        "region_label": region_label,
        "provider": provider,
        "provider_sid": provider_sid,
        "status": "available",
    }
    res = db.table("phone_numbers").insert(row).execute()
    return res.data[0]

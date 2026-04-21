"""
Voice Agent — database operations.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.database import db, generate_id


def get_settings(company_id: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("voice_agent_settings")
        .select("*")
        .eq("company_id", company_id)
        .execute()
    )
    return res.data[0] if res.data else None


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

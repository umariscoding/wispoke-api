"""
LiveKit Cloud Phone Number marketplace — search + purchase.

The Python SDK doesn't expose telephony yet, so we call the Twirp REST API
directly:
    POST /twirp/livekit.PhoneNumberService/SearchPhoneNumbers
    POST /twirp/livekit.PhoneNumberService/PurchasePhoneNumber

Auth is a short-lived HS256 JWT signed with the project's API secret, with
`sip.admin` set so LiveKit accepts telephony writes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx
import jwt as _jwt

from app.core.config import get_settings


_TOKEN_TTL_SEC = 600  # short — minted per request


def _mint_admin_token() -> str:
    """Mint a JWT with sip.admin scope for LiveKit's telephony REST API."""
    s = get_settings()
    if not s.livekit_api_key or not s.livekit_api_secret:
        raise RuntimeError("LIVEKIT_API_KEY / LIVEKIT_API_SECRET not configured")
    now = int(time.time())
    payload = {
        "iss": s.livekit_api_key,
        "nbf": now,
        "exp": now + _TOKEN_TTL_SEC,
        "sip": {"admin": True},
    }
    return _jwt.encode(payload, s.livekit_api_secret, algorithm="HS256")


def _http_base() -> str:
    """Convert wss://...livekit.cloud → https://...livekit.cloud."""
    s = get_settings()
    if not s.livekit_url:
        raise RuntimeError("LIVEKIT_URL not configured")
    return s.livekit_url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")


async def search_numbers(
    *,
    country_code: str = "US",
    area_code: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return up to `limit` available numbers in LiveKit's inventory."""
    body: Dict[str, Any] = {"countryCode": country_code.upper(), "limit": int(limit)}
    if area_code:
        body["areaCode"] = str(area_code)

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{_http_base()}/twirp/livekit.PhoneNumberService/SearchPhoneNumbers",
            headers={
                "Authorization": f"Bearer {_mint_admin_token()}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        data = r.json() or {}

    # LiveKit's Twirp response: top-level `items[]`, fields snake_case
    # (`e164_format`, `country_code`, `area_code`, `number_type`).
    # `country_code` is "USA" — strip to ISO-2 ("US") so the FE filter logic
    # stays clean.
    out: List[Dict[str, Any]] = []
    for n in data.get("items", []) or []:
        cc = (n.get("country_code") or "").upper()
        if cc == "USA":
            cc = "US"
        ntype_raw = (n.get("number_type") or "PHONE_NUMBER_TYPE_LOCAL")
        ntype = ntype_raw.replace("PHONE_NUMBER_TYPE_", "").lower() or "local"
        out.append({
            "e164": n.get("e164_format") or n.get("e164") or n.get("phoneNumber"),
            "country": cc or None,
            "area_code": n.get("area_code"),
            "locality": (n.get("locality") or "").title() or None,
            "region": n.get("region"),
            "type": ntype,
        })
    return out


class LiveKitQuotaExceeded(RuntimeError):
    """Raised when LiveKit refuses a purchase due to the plan's number quota."""


async def purchase_number(
    e164: str,
    *,
    sip_dispatch_rule_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Buy a number from LiveKit + optionally attach a dispatch rule in one call.

    Raises `LiveKitQuotaExceeded` when the project has hit its plan limit so
    the caller can surface a clean "upgrade required" message to the user.
    """
    body: Dict[str, Any] = {"phoneNumbers": [e164]}
    if sip_dispatch_rule_id:
        body["sipDispatchRuleId"] = sip_dispatch_rule_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_http_base()}/twirp/livekit.PhoneNumberService/PurchasePhoneNumber",
            headers={
                "Authorization": f"Bearer {_mint_admin_token()}",
                "Content-Type": "application/json",
            },
            json=body,
        )

    if r.status_code >= 400:
        text = (r.text or "").lower()
        if "quota" in text:
            raise LiveKitQuotaExceeded(r.text)
        r.raise_for_status()

    data = r.json() or {}
    nums = data.get("phoneNumbers") or data.get("numbers") or []
    purchased = nums[0] if nums else {}
    return {
        "e164": purchased.get("e164") or purchased.get("phoneNumber") or e164,
        "id": purchased.get("id") or purchased.get("sid"),
        "status": purchased.get("status") or "ACTIVE",
        "raw": data,
    }

"""Telnyx phone-number provisioning client.

Searches Telnyx inventory and orders a number bound to our FQDN SIP Connection
(whose FQDN points at LIVEKIT_SIP_URI), so inbound PSTN calls route straight
into the LiveKit SIP trunk — no webhook/TeXML bridge required.

Docs:
- Available numbers: https://developers.telnyx.com/api/numbers/list-available-phone-numbers
- Number orders:     https://developers.telnyx.com/api/numbers/create-number-order
- LiveKit + Telnyx:  https://developers.telnyx.com/docs/voice/sip-trunking/livekit-configuration-guide

Note: DK/FR geographic numbers require a completed regulatory bundle on the
Telnyx account before an order will succeed; US/test numbers do not. Telnyx
returns a 4xx with a descriptive `errors[]` payload in that case, which we
re-raise as `TelnyxError` so the router can surface it cleanly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings

BASE = "https://api.telnyx.com/v2"


class TelnyxError(RuntimeError):
    """A Telnyx API call failed — message carries the provider's detail text."""


def _headers() -> Dict[str, str]:
    s = get_settings()
    if not s.telnyx_api_key:
        raise TelnyxError("TELNYX_API_KEY not configured")
    return {
        "Authorization": f"Bearer {s.telnyx_api_key}",
        "Content-Type": "application/json",
    }


def _raise_for_telnyx(resp: httpx.Response) -> None:
    """Turn a Telnyx error response into a TelnyxError with readable detail."""
    if resp.status_code < 400:
        return
    detail = resp.text
    try:
        errs = resp.json().get("errors") or []
        if errs:
            detail = "; ".join(e.get("detail") or e.get("title") or str(e) for e in errs)
    except Exception:
        pass
    raise TelnyxError(detail)


def _region_label(item: Dict[str, Any]) -> Optional[str]:
    """Build a human label like 'Copenhagen' from region_information."""
    bits: List[str] = []
    for region in item.get("region_information", []) or []:
        name = region.get("region_name")
        rtype = region.get("region_type")
        if name and name not in ("--", "---") and rtype in ("location", "rate_center"):
            bits.append(name.title())
    seen: set[str] = set()
    out = [b for b in bits if not (b in seen or seen.add(b))]
    return " — ".join(out) if out else None


async def search_available(
    country_code: str = "DK",
    phone_number_type: str = "local",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return normalized purchasable numbers for a country/type.

    A Telnyx "no coverage" response is a 4xx — we map it to an empty list so the
    dashboard shows "none available" rather than a 502.
    """
    params = {
        "filter[country_code]": country_code.upper(),
        "filter[phone_number_type]": phone_number_type,
        "filter[limit]": int(limit),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BASE}/available_phone_numbers", headers=_headers(), params=params
        )
    if resp.status_code >= 400:
        return []

    out: List[Dict[str, Any]] = []
    for item in resp.json().get("data", []) or []:
        cost = item.get("cost_information", {}) or {}
        out.append(
            {
                "e164": item.get("phone_number"),
                "type": item.get("phone_number_type") or phone_number_type,
                "country": country_code.upper(),
                "region_label": _region_label(item),
                "monthly_cost": cost.get("monthly_cost"),
                "upfront_cost": cost.get("upfront_cost"),
                "currency": cost.get("currency"),
                "reservable": item.get("reservable", False),
            }
        )

    # Cheapest first (by monthly cost). Numbers with no price sink to the bottom.
    def _price(n: Dict[str, Any]) -> float:
        try:
            return float(n.get("monthly_cost"))
        except (TypeError, ValueError):
            return float("inf")

    out.sort(key=_price)
    return out


async def order_number(
    e164: str, requirement_group_id: Optional[str] = None
) -> Dict[str, Any]:
    """Order a specific number, bound to our LiveKit SIP connection.

    We own all numbers under our own EU company identity, so DK/FR regulatory
    requirements are satisfied by a pre-approved Requirement Group on our
    account (one per country/type). Its id is attached per phone number; with
    a pre-approved group the order typically activates without manual review.

    Set up once:  POST /requirement_groups  → PATCH it with our address/docs →
    Telnyx approves → store the id in settings.telnyx_requirement_group_dk etc.
    Docs: https://developers.telnyx.com/docs/numbers/phone-numbers/requirement-groups

    Returns {"e164", "order_id", "status", "connection_id"}.
    """
    s = get_settings()
    if not s.telnyx_connection_id:
        raise TelnyxError("TELNYX_CONNECTION_ID not configured")

    number_entry: Dict[str, Any] = {"phone_number": e164}
    if requirement_group_id:
        number_entry["requirement_group_id"] = requirement_group_id

    payload = {
        "phone_numbers": [number_entry],
        "connection_id": s.telnyx_connection_id,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{BASE}/number_orders", headers=_headers(), json=payload)
    _raise_for_telnyx(resp)

    data = resp.json().get("data", {}) or {}
    return {
        "e164": e164,
        "order_id": data.get("id"),
        "status": data.get("status") or "pending",
        "connection_id": s.telnyx_connection_id,
    }

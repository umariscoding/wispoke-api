"""
Telephony webhooks.

Twilio numbers can't forward to a SIP URI directly — they need TwiML at a
public webhook. This module is that webhook: Twilio POSTs the inbound call
here, we respond with `<Dial><Sip>sip:+E164@<livekit-sip-uri>` so the call
gets bridged to the LiveKit SIP trunk, which then dispatches the agent.

The dialed number is preserved in the SIP URI's user-part so LiveKit's
inbound trunk matches the trunk by `numbers`. The agent worker then reads
`called_number` from the dispatch metadata template `{{call.to}}` and
resolves the tenant via /voice/internal/sip/resolve.

Security: Twilio signs every webhook with an HMAC over (URL + sorted form
params), passed as `X-Twilio-Signature`. We verify it with the account's
auth token. Without verification, anyone who guesses the URL could trigger
outbound SIP calls from our LiveKit project.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Header, Request, Response, status

from app.core.config import get_settings

logger = logging.getLogger("wispoke.telephony")

router = APIRouter(prefix="/telephony", tags=["telephony"])


# ─── Twilio signature verification ─────────────────────────────────────────


def _verify_twilio_signature(
    auth_token: str,
    url: str,
    params: dict,
    signature: Optional[str],
) -> bool:
    """Reproduce Twilio's signing scheme: HMAC-SHA1 over (URL + sorted form data).

    Twilio docs: https://www.twilio.com/docs/usage/security#validating-requests
    """
    if not signature:
        return False
    payload = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _public_url_for(request: Request) -> str:
    """Twilio signs against the URL it called. Prefer the externally-visible
    URL (X-Forwarded-Proto/Host on Railway) over the internal one."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    return f"{proto}://{host}{request.url.path}"


# ─── TwiML for inbound SIP forward to LiveKit ──────────────────────────────


@router.post("/twilio/voice")
async def twilio_voice_inbound(
    request: Request,
    To: str = Form(...),
    From: str = Form(...),
    x_twilio_signature: Optional[str] = Header(default=None, alias="X-Twilio-Signature"),
) -> Response:
    """Inbound voice webhook from Twilio for any wispoke-pooled number.

    Returns TwiML that bridges the call into the LiveKit SIP trunk. The
    called number is preserved in the SIP URI user-part so LiveKit's trunk
    matching + agent dispatch can resolve which tenant owns the number.
    """
    settings = get_settings()

    sip_uri = settings.livekit_sip_uri
    if not sip_uri:
        # Misconfiguration — fail closed with TwiML that hangs up cleanly so
        # the caller hears silence-then-goodbye instead of a 5xx ring-of-death.
        logger.error("LIVEKIT_SIP_URI not configured — declining inbound call")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
            media_type="application/xml",
            status_code=200,
        )

    # Signature verification: enforce when auth token is set, otherwise warn.
    # This lets the endpoint boot before the env var lands without bricking
    # the trial, but a 401 is the right answer once configured.
    if settings.twilio_auth_token:
        form = await request.form()
        params = {k: v for k, v in form.multi_items()}
        url = _public_url_for(request)
        if not _verify_twilio_signature(
            settings.twilio_auth_token, url, params, x_twilio_signature
        ):
            logger.warning(
                "rejected Twilio webhook: bad signature",
                extra={"url": url, "from": From, "to": To},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature"
            )
    else:
        logger.warning(
            "TWILIO_AUTH_TOKEN not set — accepting unsigned webhook (DEV ONLY)",
            extra={"from": From, "to": To},
        )

    # Strip a leading `sip:` if the env var includes it, then build a SIP URI
    # whose user-part is the dialed E.164. LiveKit matches the trunk by that
    # user-part against the `numbers` field on the inbound trunk.
    host = sip_uri[4:] if sip_uri.lower().startswith("sip:") else sip_uri
    # Force TLS transport — LiveKit Cloud's SIP endpoint requires it (TCP/UDP
    # on port 5060 is silently dropped). Without `;transport=tls` Twilio's
    # `<Dial><Sip>` fails with no SIP response (silent timeout from LiveKit).
    if ";transport=" not in host.lower():
        host = f"{host};transport=tls"
    target = f"sip:{To}@{host}"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Dial answerOnBridge=\"true\"><Sip>{target}</Sip></Dial>"
        "</Response>"
    )

    logger.info(
        "twilio inbound → SIP forward",
        extra={"from": From, "to": To, "sip_target": target},
    )

    return Response(content=twiml, media_type="application/xml")

"""
Billing service — business logic for LemonSqueezy subscription management.

Handles checkout creation, webhook processing, and subscription lifecycle.
"""

import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import requests as http_requests

from app.core.config import settings
from app.core.exceptions import ValidationError, NotFoundError, AuthorizationError
from app.features.billing.repository import (
    update_subscription,
    get_company_by_ls_subscription_id,
    get_company_subscription,
    is_webhook_processed,
    log_webhook_event,
)
from app.features.auth.repository import get_company_by_id

logger = logging.getLogger("chatevo.billing")

LS_API_BASE = "https://api.lemonsqueezy.com/v1"

KNOWN_EVENTS = {
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_expired",
    "subscription_paused",
    "subscription_unpaused",
    "subscription_payment_success",
    "subscription_payment_failed",
    "subscription_payment_recovered",
}


def _ls_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    }


def _ls_request(method: str, url: str, **kwargs) -> http_requests.Response:
    """Make a request to LemonSqueezy API. No retries — let the caller handle errors.

    All billing endpoints are async and delegate to this synchronous function
    via FastAPI's threadpool, so we keep it simple and fast.
    """
    return getattr(http_requests, method)(
        url, headers=_ls_headers(), timeout=30, **kwargs
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def create_checkout_url(company_id: str, email: str) -> str:
    """Create a LemonSqueezy checkout session and return the checkout URL."""
    if not all([
        settings.lemonsqueezy_api_key,
        settings.lemonsqueezy_store_id,
        settings.lemonsqueezy_variant_id,
    ]):
        raise ValidationError("Payment system is not configured")

    response = _ls_request(
        "post",
        f"{LS_API_BASE}/checkouts",
        json={
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {
                        "email": email,
                        "custom": {
                            "company_id": company_id,
                        },
                    },
                    "product_options": {
                        "redirect_url": f"{settings.admin_dashboard_url}/settings?billing=success",
                    },
                },
                "relationships": {
                    "store": {
                        "data": {
                            "type": "stores",
                            "id": settings.lemonsqueezy_store_id,
                        }
                    },
                    "variant": {
                        "data": {
                            "type": "variants",
                            "id": settings.lemonsqueezy_variant_id,
                        }
                    },
                },
            }
        },
    )

    if not response.ok:
        logger.error(
            "LemonSqueezy checkout creation failed for company %s: %s %s",
            company_id, response.status_code, response.text,
        )
        raise ValidationError("Failed to create checkout session")

    try:
        checkout_url = response.json()["data"]["attributes"]["url"]
    except (KeyError, TypeError) as exc:
        logger.error("Unexpected checkout response for company %s: %s", company_id, exc)
        raise ValidationError("Unexpected response from payment provider")

    # Validate the returned URL is from LemonSqueezy
    if not checkout_url or "lemonsqueezy.com" not in checkout_url:
        logger.error("Unexpected checkout URL for company %s: %s", company_id, checkout_url)
        raise ValidationError("Received invalid checkout URL")

    return checkout_url


# ---------------------------------------------------------------------------
# Webhook verification & processing
# ---------------------------------------------------------------------------

def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify LemonSqueezy webhook HMAC-SHA256 signature."""
    secret = settings.lemonsqueezy_webhook_secret
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _resolve_company_id(
    custom_data: Dict[str, Any],
    ls_subscription_id: str,
    event_name: str,
) -> Optional[str]:
    """Resolve the company_id for a webhook event.

    For subscription_created, custom_data is the only source since the
    subscription ID hasn't been stored yet. For all other events, prefer
    the DB lookup by subscription ID (tamper-proof), falling back to
    custom_data only if needed.
    """
    if event_name == "subscription_created":
        return custom_data.get("company_id")

    # Primary: look up by subscription ID already stored in our DB
    if ls_subscription_id:
        company = get_company_by_ls_subscription_id(ls_subscription_id)
        if company:
            return company["company_id"]

    # Fallback: custom_data (only used if subscription ID not yet stored)
    return custom_data.get("company_id")


def handle_webhook(raw_body: bytes, signature: str) -> None:
    """Process a LemonSqueezy webhook event.

    Idempotent — duplicate events are detected and skipped.
    Signature is verified before any processing.
    Every event is logged for audit.
    """
    if not verify_webhook_signature(raw_body, signature):
        raise AuthorizationError("Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("Webhook payload is not valid JSON: %s", exc)
        raise ValidationError("Invalid webhook payload")

    meta = payload.get("meta") or {}
    event_name = meta.get("event_name", "")
    custom_data = meta.get("custom_data") or {}
    webhook_id = meta.get("webhook_id", "")
    attributes = payload.get("data", {}).get("attributes", {})

    ls_subscription_id = str(payload.get("data", {}).get("id", ""))
    ls_customer_id = str(attributes.get("customer_id", ""))

    if not event_name:
        logger.error("Webhook missing event_name in meta: %s", meta)
        raise ValidationError("Invalid webhook: missing event_name")

    # Build a stable idempotency key — webhook_id is the primary
    # disambiguator; if absent, fall back to event_name + subscription_id
    if webhook_id:
        event_id = f"{webhook_id}:{event_name}:{ls_subscription_id}"
    else:
        event_id = f"{event_name}:{ls_subscription_id}:{hashlib.sha256(raw_body).hexdigest()[:16]}"

    # Resolve company
    company_id = _resolve_company_id(custom_data, ls_subscription_id, event_name)

    # Idempotency check — skip if already processed
    if is_webhook_processed(event_id):
        logger.info("Skipping duplicate webhook %s for company %s", event_id, company_id)
        return

    # Validate event type
    if event_name not in KNOWN_EVENTS:
        logger.warning(
            "Unknown webhook event '%s' (id=%s, sub=%s)",
            event_name, webhook_id, ls_subscription_id,
        )
        log_webhook_event(event_id, event_name, company_id, ls_subscription_id, processed=False, error="unknown_event")
        return

    if not company_id:
        logger.error(
            "Webhook %s: could not resolve company_id (sub=%s, custom=%s)",
            event_name, ls_subscription_id, custom_data,
        )
        log_webhook_event(event_id, event_name, None, ls_subscription_id, processed=False, error="no_company_id")
        return

    # Verify company exists
    company = get_company_by_id(company_id)
    if not company:
        logger.error("Webhook %s: company %s not found in DB", event_name, company_id)
        log_webhook_event(event_id, event_name, company_id, ls_subscription_id, processed=False, error="company_not_found")
        return

    logger.info(
        "Processing webhook event=%s company=%s sub=%s",
        event_name, company_id, ls_subscription_id,
    )

    try:
        _process_event(event_name, company_id, ls_customer_id, ls_subscription_id, attributes)
        log_webhook_event(event_id, event_name, company_id, ls_subscription_id, processed=True)
    except Exception as exc:
        logger.error("Webhook processing failed: event=%s company=%s error=%s", event_name, company_id, exc)
        log_webhook_event(event_id, event_name, company_id, ls_subscription_id, processed=False, error=str(exc))
        raise


def _process_event(
    event_name: str,
    company_id: str,
    ls_customer_id: str,
    ls_subscription_id: str,
    attributes: Dict[str, Any],
) -> None:
    """Route and process a single webhook event."""
    renews_at = attributes.get("renews_at")
    ends_at = attributes.get("ends_at")

    if event_name == "subscription_created":
        update_subscription(
            company_id=company_id,
            ls_customer_id=ls_customer_id,
            ls_subscription_id=ls_subscription_id,
            ls_subscription_status="active",
            plan="pro",
            subscription_renews_at=renews_at,
            subscription_ends_at=ends_at,
        )

    elif event_name == "subscription_updated":
        status = attributes.get("status", "active")
        update_data = dict(
            company_id=company_id,
            ls_subscription_status=status,
            subscription_renews_at=renews_at,
            subscription_ends_at=ends_at,
        )
        if status == "active":
            update_data["plan"] = "pro"
        update_subscription(**update_data)

    elif event_name == "subscription_cancelled":
        # Keep plan as "pro" — user retains access until billing period ends
        update_subscription(
            company_id=company_id,
            ls_subscription_status="cancelled",
            subscription_ends_at=ends_at,
        )

    elif event_name == "subscription_expired":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="expired",
            plan="free",
        )

    elif event_name == "subscription_payment_success":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="active",
            plan="pro",
            subscription_renews_at=renews_at,
        )

    elif event_name == "subscription_resumed":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="active",
            plan="pro",
            subscription_renews_at=renews_at,
            subscription_ends_at=ends_at,
        )

    elif event_name == "subscription_paused":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="paused",
        )

    elif event_name == "subscription_unpaused":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="active",
            plan="pro",
            subscription_renews_at=renews_at,
        )

    elif event_name == "subscription_payment_failed":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="past_due",
        )

    elif event_name == "subscription_payment_recovered":
        update_subscription(
            company_id=company_id,
            ls_subscription_status="active",
            plan="pro",
            subscription_renews_at=renews_at,
        )


# ---------------------------------------------------------------------------
# Subscription status & management
# ---------------------------------------------------------------------------

def _get_customer_portal_url(ls_customer_id: str) -> Optional[str]:
    """Fetch the LemonSqueezy customer portal URL."""
    if not ls_customer_id or not settings.lemonsqueezy_api_key:
        return None
    try:
        response = _ls_request("get", f"{LS_API_BASE}/customers/{ls_customer_id}")
        if response.ok:
            data = response.json()
            return data.get("data", {}).get("attributes", {}).get("urls", {}).get("customer_portal")
    except Exception as exc:
        logger.warning("Failed to fetch customer portal URL: %s", exc)
    return None


def is_plan_active(company: Dict[str, Any]) -> bool:
    """Check if a company has an active Pro subscription.

    A company is considered Pro if plan == "pro" AND:
    - subscription status is "active", OR
    - subscription status is "cancelled" but subscription_ends_at is in the future
      (grace period — user keeps access until billing period ends), OR
    - subscription status is "past_due" (payment failed but LemonSqueezy is
      retrying during the dunning period — don't cut off access immediately)
    """
    if company.get("plan") != "pro":
        return False

    status = company.get("ls_subscription_status", "none")
    if status in ("active", "past_due"):
        return True

    if status == "cancelled":
        ends_at = company.get("subscription_ends_at")
        if ends_at:
            try:
                end_dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                return end_dt > datetime.now(timezone.utc)
            except (ValueError, AttributeError):
                pass
        return False

    return False


def get_subscription_status(company_id: str) -> Dict[str, Any]:
    """Get current subscription status for a company."""
    sub = get_company_subscription(company_id)
    if not sub:
        raise NotFoundError("Company not found")

    ls_customer_id = sub.get("ls_customer_id")
    manage_url = _get_customer_portal_url(ls_customer_id) if ls_customer_id else None

    return {
        "plan": sub.get("plan", "free"),
        "ls_subscription_status": sub.get("ls_subscription_status", "none"),
        "subscription_ends_at": sub.get("subscription_ends_at"),
        "subscription_renews_at": sub.get("subscription_renews_at"),
        "manage_url": manage_url,
    }


def cancel_subscription(company_id: str) -> Dict[str, Any]:
    """Cancel the company's subscription at the end of the billing period.

    Uses DELETE per LemonSqueezy docs. The subscription enters a grace
    period until the next renewal date — the user keeps Pro access until
    then. During that window, resume_subscription() can reactivate it.
    """
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    ls_subscription_id = company.get("ls_subscription_id")
    if not ls_subscription_id:
        raise ValidationError("No active subscription found")

    status = company.get("ls_subscription_status")
    if status != "active":
        raise ValidationError(f"Cannot cancel subscription with status '{status}'")

    if not settings.lemonsqueezy_api_key:
        raise ValidationError("Payment system is not configured")

    response = _ls_request(
        "delete",
        f"{LS_API_BASE}/subscriptions/{ls_subscription_id}",
    )

    if not response.ok:
        logger.error(
            "LemonSqueezy cancel failed for company %s (sub=%s): %s %s",
            company_id, ls_subscription_id, response.status_code, response.text,
        )
        raise ValidationError("Failed to cancel subscription")

    # LemonSqueezy returns the subscription with ends_at in the response
    ends_at = None
    try:
        attrs = response.json().get("data", {}).get("attributes", {})
        ends_at = attrs.get("ends_at")
    except Exception:
        pass

    # Update local status — plan stays "pro" until period ends
    update_subscription(
        company_id=company_id,
        ls_subscription_status="cancelled",
        subscription_ends_at=ends_at,
    )

    return {"message": "Subscription will be cancelled at the end of the billing period"}


def resume_subscription(company_id: str) -> Dict[str, Any]:
    """Resume a cancelled subscription during the grace period.

    Uses PATCH with cancelled=false. Only works while the subscription
    hasn't expired yet (before ends_at).
    """
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    ls_subscription_id = company.get("ls_subscription_id")
    if not ls_subscription_id:
        raise ValidationError("No subscription found")

    status = company.get("ls_subscription_status")
    if status != "cancelled":
        raise ValidationError(f"Cannot resume subscription with status '{status}'")

    # Check if still in grace period
    ends_at = company.get("subscription_ends_at")
    if ends_at:
        try:
            end_dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
            if end_dt <= datetime.now(timezone.utc):
                raise ValidationError("Subscription has already expired and cannot be resumed")
        except (ValueError, AttributeError):
            pass

    if not settings.lemonsqueezy_api_key:
        raise ValidationError("Payment system is not configured")

    response = _ls_request(
        "patch",
        f"{LS_API_BASE}/subscriptions/{ls_subscription_id}",
        json={
            "data": {
                "type": "subscriptions",
                "id": ls_subscription_id,
                "attributes": {
                    "cancelled": False,
                },
            }
        },
    )

    if not response.ok:
        logger.error(
            "LemonSqueezy resume failed for company %s (sub=%s): %s %s",
            company_id, ls_subscription_id, response.status_code, response.text,
        )
        raise ValidationError("Failed to resume subscription")

    # Read updated dates from the LemonSqueezy response
    renews_at = None
    ends_at = None
    try:
        attrs = response.json().get("data", {}).get("attributes", {})
        renews_at = attrs.get("renews_at")
        ends_at = attrs.get("ends_at")
    except Exception:
        pass

    update_subscription(
        company_id=company_id,
        ls_subscription_status="active",
        subscription_renews_at=renews_at,
        subscription_ends_at=ends_at,
    )

    return {"message": "Subscription resumed successfully"}

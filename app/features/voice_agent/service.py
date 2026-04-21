"""
Voice Agent — business logic.
"""

from typing import Dict, Any, Optional

from app.core.exceptions import NotFoundError
from app.features.voice_agent import repository as repo


def get_settings(company_id: str) -> Dict[str, Any]:
    settings = repo.get_settings(company_id)
    if not settings:
        return {
            "is_enabled": False,
            "twilio_phone_number": None,
            "greeting_message": "Hello! Thank you for calling. How can I help you today?",
            "business_name": None,
            "business_type": None,
            "appointment_duration_min": 30,
            "voice_provider": "deepgram",
            "voice_model": "aura-asteria-en",
            "language": "en",
            "system_prompt": None,
        }
    # Never expose Twilio auth token to frontend
    settings.pop("twilio_auth_token", None)
    return settings


def update_settings(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    result = repo.upsert_settings(company_id, **data)
    result.pop("twilio_auth_token", None)
    return result


def get_settings_for_call(phone_number: str) -> Optional[Dict[str, Any]]:
    """Look up voice agent settings by the Twilio phone number being called."""
    return repo.get_settings_by_phone(phone_number)


def build_system_prompt(settings: Dict[str, Any]) -> str:
    """Build the LLM system prompt for the voice agent."""
    business_name = settings.get("business_name") or "our business"
    business_type = settings.get("business_type") or "service provider"
    duration = settings.get("appointment_duration_min", 30)
    custom_prompt = settings.get("system_prompt") or ""

    return f"""You are a friendly and professional AI phone receptionist for {business_name}, a {business_type}.

Your job is to:
1. Greet the caller warmly
2. Understand what service they need
3. Check available time slots and help them book an appointment
4. Collect their name and phone number for the booking
5. Confirm the appointment details before finalizing

Important rules:
- Each appointment is {duration} minutes long
- Always confirm the date, time, and service before booking
- Be concise — callers prefer short, clear responses
- If no slots are available on the requested date, suggest the next available date
- Never make up availability — only offer slots from the provided available_slots data
- If the caller wants to cancel or reschedule, help them do so
- Be warm but efficient — no long monologues

{custom_prompt}

When you have collected all necessary information to book an appointment, respond with a JSON block:
```json
{{"action": "book_appointment", "caller_name": "...", "caller_phone": "...", "scheduled_date": "YYYY-MM-DD", "start_time": "HH:MM", "service_type": "..."}}
```

When the caller wants to end the conversation, respond with:
```json
{{"action": "end_call"}}
```
"""

"""
Voice Agent — WebSocket media stream handler.

Connects Twilio Media Streams ↔ Deepgram STT ↔ Groq LLM ↔ Deepgram TTS
for real-time voice conversations.
"""

import asyncio
import base64
import json
import logging
from typing import Optional, Dict, Any, List

import httpx
import websockets

from app.core.config import settings as app_settings

logger = logging.getLogger("wispoke.voice")

DEEPGRAM_STT_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class VoiceStreamHandler:
    """Handles a single voice call's real-time audio pipeline."""

    def __init__(
        self,
        company_id: str,
        system_prompt: str,
        greeting_message: str,
        voice_model: str = "aura-asteria-en",
        language: str = "en",
        available_slots_fn=None,
        book_appointment_fn=None,
    ):
        self.company_id = company_id
        self.system_prompt = system_prompt
        self.greeting_message = greeting_message
        self.voice_model = voice_model
        self.language = language
        self.available_slots_fn = available_slots_fn
        self.book_appointment_fn = book_appointment_fn

        self.conversation_history: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.deepgram_ws: Optional[Any] = None
        self._transcript_buffer = ""
        self._silence_task: Optional[asyncio.Task] = None
        self._is_speaking = False

    async def handle_twilio_ws(self, twilio_ws):
        """Main handler for the Twilio WebSocket connection."""
        deepgram_key = getattr(app_settings, "deepgram_api_key", None)
        if not deepgram_key:
            logger.error("DEEPGRAM_API_KEY not set")
            return

        # Connect to Deepgram STT
        stt_url = (
            f"{DEEPGRAM_STT_URL}"
            f"?encoding=mulaw&sample_rate=8000&channels=1"
            f"&model=nova-2&language={self.language}"
            f"&punctuate=true&interim_results=true"
            f"&endpointing=200&utterance_end_ms=1000"
        )
        headers = {"Authorization": f"Token {deepgram_key}"}

        try:
            async with websockets.connect(stt_url, additional_headers=headers) as dg_ws:
                self.deepgram_ws = dg_ws

                # Send greeting first
                await self._send_tts_to_twilio(twilio_ws, self.greeting_message)
                self.conversation_history.append(
                    {"role": "assistant", "content": self.greeting_message}
                )

                # Run both listeners concurrently
                await asyncio.gather(
                    self._listen_twilio(twilio_ws, dg_ws),
                    self._listen_deepgram(twilio_ws, dg_ws),
                )
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Voice call ended: {self.call_sid}")
        except Exception as e:
            logger.error(f"Voice stream error: {e}", exc_info=True)

    async def _listen_twilio(self, twilio_ws, dg_ws):
        """Forward Twilio audio to Deepgram for transcription."""
        try:
            async for message in twilio_ws.iter_text():
                data = json.loads(message)
                event = data.get("event")

                if event == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    self.call_sid = data["start"]["callSid"]
                    logger.info(f"Call started: {self.call_sid}")

                elif event == "media":
                    audio_payload = data["media"]["payload"]
                    audio_bytes = base64.b64decode(audio_payload)
                    await dg_ws.send(audio_bytes)

                elif event == "stop":
                    logger.info(f"Call stopped: {self.call_sid}")
                    await dg_ws.send(b"")  # Signal end to Deepgram
                    break

        except Exception as e:
            logger.error(f"Twilio listener error: {e}")

    async def _listen_deepgram(self, twilio_ws, dg_ws):
        """Process Deepgram transcription results."""
        try:
            async for message in dg_ws:
                result = json.loads(message)

                if result.get("type") == "Results":
                    transcript = (
                        result.get("channel", {})
                        .get("alternatives", [{}])[0]
                        .get("transcript", "")
                    )

                    if not transcript:
                        continue

                    is_final = result.get("is_final", False)

                    if is_final:
                        self._transcript_buffer += " " + transcript
                        self._transcript_buffer = self._transcript_buffer.strip()

                        # Cancel any pending silence timer
                        if self._silence_task:
                            self._silence_task.cancel()

                        # Start silence timer — process after 800ms of silence
                        self._silence_task = asyncio.create_task(
                            self._on_silence(twilio_ws)
                        )

                elif result.get("type") == "UtteranceEnd":
                    # Deepgram detected end of utterance
                    if self._transcript_buffer:
                        if self._silence_task:
                            self._silence_task.cancel()
                        await self._process_utterance(twilio_ws)

        except Exception as e:
            logger.error(f"Deepgram listener error: {e}")

    async def _on_silence(self, twilio_ws):
        """Called after silence detected — process the buffered transcript."""
        await asyncio.sleep(0.8)
        if self._transcript_buffer:
            await self._process_utterance(twilio_ws)

    async def _process_utterance(self, twilio_ws):
        """Send transcript to Groq LLM and stream TTS response back."""
        user_text = self._transcript_buffer.strip()
        self._transcript_buffer = ""

        if not user_text:
            return

        logger.info(f"Caller said: {user_text}")
        self.conversation_history.append({"role": "user", "content": user_text})

        # Inject current availability context
        await self._inject_availability_context()

        # Get LLM response from Groq
        assistant_text = await self._get_llm_response()
        if not assistant_text:
            return

        logger.info(f"Agent says: {assistant_text}")

        # Check for action JSON in response
        action = self._extract_action(assistant_text)
        if action:
            if action.get("action") == "book_appointment" and self.book_appointment_fn:
                try:
                    result = await self.book_appointment_fn(self.company_id, action)
                    confirmation = f"I've booked your appointment for {action.get('scheduled_date')} at {action.get('start_time')}. You're all set!"
                    await self._send_tts_to_twilio(twilio_ws, confirmation)
                    self.conversation_history.append(
                        {"role": "assistant", "content": confirmation}
                    )
                except Exception as e:
                    error_msg = "I'm sorry, I wasn't able to book that slot. Let me suggest another time."
                    await self._send_tts_to_twilio(twilio_ws, error_msg)
                    self.conversation_history.append(
                        {"role": "assistant", "content": error_msg}
                    )
                return

            if action.get("action") == "end_call":
                goodbye = "Thank you for calling! Have a great day. Goodbye!"
                await self._send_tts_to_twilio(twilio_ws, goodbye)
                return

        # Clean response text (remove any JSON blocks for TTS)
        clean_text = self._clean_for_tts(assistant_text)
        self.conversation_history.append({"role": "assistant", "content": assistant_text})

        # Send TTS audio
        await self._send_tts_to_twilio(twilio_ws, clean_text)

    async def _inject_availability_context(self):
        """Add current availability info to conversation context."""
        if not self.available_slots_fn:
            return

        try:
            from datetime import datetime, timedelta
            today = datetime.now()
            slots_info = []
            for i in range(7):  # Next 7 days
                date = today + timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                day_name = date.strftime("%A")
                slots = await self.available_slots_fn(self.company_id, date_str)
                if slots:
                    times = ", ".join(f"{s['start_time']}-{s['end_time']}" for s in slots[:8])
                    slots_info.append(f"  {day_name} {date_str}: {times}")
                else:
                    slots_info.append(f"  {day_name} {date_str}: No availability")

            availability_msg = "Current available appointment slots:\n" + "\n".join(slots_info)

            # Update or add system context
            if len(self.conversation_history) > 1 and self.conversation_history[1].get("role") == "system":
                self.conversation_history[1] = {"role": "system", "content": availability_msg}
            else:
                self.conversation_history.insert(1, {"role": "system", "content": availability_msg})
        except Exception as e:
            logger.error(f"Failed to inject availability: {e}")

    async def _get_llm_response(self) -> Optional[str]:
        """Get response from Groq (fastest LLM inference)."""
        groq_key = app_settings.groq_api_key
        if not groq_key:
            logger.error("GROQ_API_KEY not set")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": self.conversation_history,
                        "temperature": 0.7,
                        "max_tokens": 256,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Groq LLM error: {e}")
            return "I'm sorry, I'm having trouble processing that. Could you repeat?"

    async def _send_tts_to_twilio(self, twilio_ws, text: str):
        """Convert text to speech via Deepgram and send audio to Twilio."""
        deepgram_key = getattr(app_settings, "deepgram_api_key", None)
        if not deepgram_key or not text.strip():
            return

        self._is_speaking = True

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{DEEPGRAM_TTS_URL}?model={self.voice_model}&encoding=mulaw&sample_rate=8000&container=none",
                    headers={
                        "Authorization": f"Token {deepgram_key}",
                        "Content-Type": "application/json",
                    },
                    json={"text": text},
                )
                response.raise_for_status()

                audio_bytes = response.content

                # Send audio in chunks matching Twilio's expected format
                chunk_size = 640  # ~80ms of mulaw audio at 8kHz
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i : i + chunk_size]
                    payload = base64.b64encode(chunk).decode("utf-8")
                    media_msg = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {"payload": payload},
                    }
                    await twilio_ws.send_text(json.dumps(media_msg))

                # Mark to clear the audio buffer
                if self.stream_sid:
                    mark_msg = {
                        "event": "mark",
                        "streamSid": self.stream_sid,
                        "mark": {"name": "tts_done"},
                    }
                    await twilio_ws.send_text(json.dumps(mark_msg))

        except Exception as e:
            logger.error(f"TTS error: {e}")
        finally:
            self._is_speaking = False

    def _extract_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON action block from LLM response."""
        import re
        pattern = r"```json\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding raw JSON
        pattern2 = r'\{"action"\s*:\s*"[^"]+?".*?\}'
        match2 = re.search(pattern2, text, re.DOTALL)
        if match2:
            try:
                return json.loads(match2.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _clean_for_tts(self, text: str) -> str:
        """Remove JSON blocks and markdown from text for TTS."""
        import re
        text = re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL)
        text = re.sub(r"\{.*?\"action\".*?\}", "", text, flags=re.DOTALL)
        text = re.sub(r"[*#`]", "", text)
        return text.strip()

import httpx
import logging
from ...application.interfaces.voice_service import TTSService

logger = logging.getLogger(__name__)


class ElevenLabsAdapter(TTSService):
    """
    ElevenLabs TTS API. High quality neural voices.
    Requires ELEVENLABS_API_KEY env var.
    Optional: ELEVENLABS_VOICE_ID to override the default voice.
    """

    BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
    DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel — British, calm, conversational

    def __init__(self, api_key: str, voice_id: str = None):
        self.api_key = api_key
        self.voice_id = voice_id or self.DEFAULT_VOICE_ID

    async def synthesize_speech(self, text: str, language: str = "en") -> bytes:
        logger.info(f"[TTS] ElevenLabs using voice_id={self.voice_id!r}")
        url = f"{self.BASE_URL}/{self.voice_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.80,
                        "style": 0.25,
                        "use_speaker_boost": True,
                    },
                },
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
            )
            if not response.is_success:
                logger.error(f"[TTS] ElevenLabs error {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            logger.info(f"[TTS] ElevenLabs synthesized {len(text)} chars, {len(response.content)} bytes")
            return response.content

    async def get_available_voices(self) -> list:
        """Returns a static list — ElevenLabs voice listing requires separate API call."""
        return [{"voice_id": self.DEFAULT_VOICE_ID, "name": "ElevenLabs Default (Adam)"}]

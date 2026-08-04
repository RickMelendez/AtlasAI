import httpx
import logging
from ...application.interfaces.voice_service import TTSService

logger = logging.getLogger(__name__)


class FishAudioAdapter(TTSService):
    """
    Fish Audio TTS API. High quality, low latency.
    Requires FISH_AUDIO_API_KEY env var.
    Returns WAV so UE5 can play it natively (no plugin needed).
    """

    BASE_URL = "https://api.fish.audio/v1/tts"
    DEFAULT_VOICE_ID = "102ea81e50c64962b689c44c16931473"

    def __init__(self, api_key: str, voice_id: str = None):
        self.api_key = api_key
        self.voice_id = voice_id or self.DEFAULT_VOICE_ID

    async def synthesize_speech(self, text: str, language: str = "en") -> bytes:
        logger.info(f"[TTS] Fish Audio using voice_id={self.voice_id!r}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.BASE_URL,
                json={
                    "text": text,
                    "reference_id": self.voice_id,
                    "format": "wav",
                    "latency": "normal",
                    "normalize": True,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            if not response.is_success:
                logger.error(f"[TTS] Fish Audio error {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            logger.info(f"[TTS] Fish Audio synthesized {len(text)} chars, {len(response.content)} bytes")
            return response.content

    async def get_available_voices(self) -> list:
        return [{"voice_id": self.DEFAULT_VOICE_ID, "name": "Fish Audio Default"}]

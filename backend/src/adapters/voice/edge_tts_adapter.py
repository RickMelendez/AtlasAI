import io
import logging
import edge_tts
from ...application.interfaces.voice_service import TTSService

logger = logging.getLogger(__name__)


class EdgeTTSAdapter(TTSService):
    """
    Microsoft Edge TTS via edge-tts. Free, no API key.
    Falls back gracefully when Fish Audio key is not set.
    """

    VOICE_MAP = {
        "en": "en-US-AndrewNeural",   # conversational, podcaster-style male voice
        "es": "es-MX-JorgeNeural",    # natural Mexican Spanish male voice
        "fr": "fr-FR-HenriNeural",
        "de": "de-DE-ConradNeural",
    }

    async def synthesize_speech(self, text: str, language: str = "en") -> bytes:
        voice = self.VOICE_MAP.get(language, "en-US-AndrewNeural")
        communicate = edge_tts.Communicate(text, voice, rate="-5%", pitch="-3Hz")
        audio = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
        result = audio.getvalue()
        logger.debug(f"[TTS] Edge-TTS synthesized {len(text)} chars via {voice}")
        return result

    async def get_available_voices(self) -> list:
        """Returns the built-in voice map as a list."""
        return [
            {"voice_id": voice_id, "name": voice_id}
            for voice_id in self.VOICE_MAP.values()
        ]

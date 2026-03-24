"""
ElevenLabs Adapter - Text-to-Speech usando ElevenLabs API.

Implementa TTSService usando ElevenLabs para dar voz a Atlas AI.
ElevenLabs ofrece voces naturales de alta calidad con baja latencia.

Modelo recomendado: eleven_turbo_v2_5 (el más rápido, ideal para conversación)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ...application.interfaces.voice_service import TTSService
from ...infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsAdapter(TTSService):
    """
    Adapter para ElevenLabs TTS.

    Convierte texto a audio MP3 usando las voces de ElevenLabs.
    Atlas usa el modelo "eleven_turbo_v2_5" para minimizar latencia
    y dar respuestas conversacionales fluidas.

    Voz por defecto: Adam (pNInz6obpgDQGcFmaJgB)
    Puedes cambiarla desde la consola de ElevenLabs o via settings.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
    ):
        """
        Inicializa el adapter de ElevenLabs.

        Args:
            api_key: ElevenLabs API key (opcional, se obtiene de settings)
            voice_id: ID de la voz a usar (opcional, usa la configurada en settings)
        """
        settings = get_settings()

        self.api_key = api_key or settings.elevenlabs_api_key
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key not found. " "Set ELEVENLABS_API_KEY in .env file."
            )

        self.voice_id = voice_id or settings.elevenlabs_voice_id

        # eleven_turbo_v2_5 = lowest latency (~300ms), best for realtime conversation
        # eleven_multilingual_v2 = higher quality, more languages, but slower
        self.model_id = "eleven_turbo_v2_5"

        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        logger.info(
            f"✅ ElevenLabsAdapter initialized | voice: {self.voice_id} | model: {self.model_id}"
        )

    async def synthesize_speech(
        self,
        text: str,
        language: str = "es",
    ) -> bytes:
        """
        Convierte texto a audio MP3.

        Args:
            text: Texto a sintetizar (máx ~2500 chars por request)
            language: Idioma del texto ("es" o "en") — turbo model es bilingüe

        Returns:
            Bytes del audio en formato MP3

        Raises:
            httpx.HTTPStatusError: Si la API retorna un error HTTP
            Exception: Para otros errores de red o procesamiento
        """
        if not text or not text.strip():
            logger.warning("[ElevenLabs] Empty text received, returning empty bytes")
            return b""

        # Truncar si es muy largo (ElevenLabs tiene límite de ~5000 chars)
        if len(text) > 4500:
            logger.warning(
                f"[ElevenLabs] Text too long ({len(text)} chars), truncating to 4500"
            )
            text = text[:4500] + "..."

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,  # Balance entre consistencia y variedad expresiva
                "similarity_boost": 0.75,  # Qué tan fiel a la voz original
                "style": 0.0,  # Sin estilo exagerado para conversación natural
                "use_speaker_boost": True,  # Mejora claridad y presencia de la voz
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{ELEVENLABS_BASE_URL}/text-to-speech/{self.voice_id}",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()

            audio_bytes = response.content
            logger.info(
                f"[ElevenLabs] ✅ Synthesized {len(text)} chars → {len(audio_bytes)} bytes MP3"
            )
            return audio_bytes

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[ElevenLabs] HTTP error {e.response.status_code}: {e.response.text}"
            )
            raise
        except httpx.TimeoutException:
            logger.error("[ElevenLabs] Request timed out after 30s")
            raise
        except Exception as e:
            logger.error(f"[ElevenLabs] Unexpected error: {e}")
            raise

    async def get_available_voices(self) -> list:
        """
        Obtiene la lista de voces disponibles en la cuenta.

        Returns:
            Lista de dicts con 'voice_id' y 'name'
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{ELEVENLABS_BASE_URL}/voices",
                    headers={"xi-api-key": self.api_key},
                )
                response.raise_for_status()

            voices_data = response.json()
            voices = [
                {
                    "voice_id": v["voice_id"],
                    "name": v["name"],
                    "category": v.get("category", "unknown"),
                }
                for v in voices_data.get("voices", [])
            ]

            logger.info(f"[ElevenLabs] Found {len(voices)} available voices")
            return voices

        except Exception as e:
            logger.error(f"[ElevenLabs] Error fetching voices: {e}")
            return []

    async def stream_synthesize_speech(
        self,
        text: str,
    ):
        """
        Sintetiza y transmite audio en streaming (chunks).

        Útil para respuestas largas — empieza a reproducir antes
        de que termine toda la síntesis.

        Yields:
            Chunks de bytes del audio MP3
        """
        if not text or not text.strip():
            return

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{ELEVENLABS_BASE_URL}/text-to-speech/{self.voice_id}/stream",
                    headers=self.headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk

        except Exception as e:
            logger.error(f"[ElevenLabs] Streaming error: {e}")
            raise


# ── Singleton ─────────────────────────────────────────────────────────────────

_elevenlabs_adapter_instance: Optional[ElevenLabsAdapter] = None


def get_elevenlabs_adapter() -> ElevenLabsAdapter:
    """
    Obtiene la instancia singleton del ElevenLabsAdapter.

    Returns:
        Instancia de ElevenLabsAdapter
    """
    global _elevenlabs_adapter_instance
    if _elevenlabs_adapter_instance is None:
        _elevenlabs_adapter_instance = ElevenLabsAdapter()
    return _elevenlabs_adapter_instance

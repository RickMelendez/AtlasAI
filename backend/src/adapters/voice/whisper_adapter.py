"""
Whisper Adapter - Reconocimiento de voz usando OpenAI Whisper.

Implementa VoiceService usando el modelo Whisper de OpenAI
para transcripción de audio a texto.
"""

import io
import logging
import tempfile
from typing import Optional

from openai import AsyncOpenAI

from ...application.interfaces.voice_service import VoiceService
from ...infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class WhisperAdapter(VoiceService):
    """
    Adapter para OpenAI Whisper.

    Usa la API de OpenAI Whisper para transcribir audio a texto
    en múltiples idiomas con alta precisión.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el adapter de Whisper.

        Args:
            api_key: API key de OpenAI (opcional, se obtiene de settings)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. " "Set OPENAI_API_KEY in .env file."
            )

        # Cliente async de OpenAI
        self.client = AsyncOpenAI(api_key=self.api_key)

        # Modelo de Whisper a usar
        self.model = "whisper-1"

        logger.info(f"✅ WhisperAdapter initialized with model: {self.model}")

    async def transcribe_audio(self, audio_data: bytes, language: str = "es") -> str:
        """
        Transcribe audio a texto usando Whisper.

        Args:
            audio_data: Datos de audio en formato WAV/MP3/M4A/WEBM
            language: Idioma del audio ("es" para español, "en" para inglés)

        Returns:
            Texto transcrito

        Raises:
            Exception: Si ocurre un error en la transcripción
        """
        try:
            # Whisper espera un archivo, así que guardamos en temp
            with tempfile.NamedTemporaryFile(
                suffix=".webm", delete=False
            ) as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name

            # Transcribir con Whisper
            with open(temp_audio_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=language,
                    response_format="text",
                )

            # Limpiar archivo temporal
            import os

            os.unlink(temp_audio_path)

            logger.info(f"Transcribed audio: {transcript[:50]}...")
            return transcript.strip()

        except Exception as e:
            logger.error(f"Error transcribing audio with Whisper: {e}")
            raise


# Singleton instance
_whisper_adapter_instance: Optional[WhisperAdapter] = None


def get_whisper_adapter() -> WhisperAdapter:
    """
    Obtiene la instancia singleton del WhisperAdapter.

    Returns:
        Instancia de WhisperAdapter
    """
    global _whisper_adapter_instance
    if _whisper_adapter_instance is None:
        _whisper_adapter_instance = WhisperAdapter()
    return _whisper_adapter_instance

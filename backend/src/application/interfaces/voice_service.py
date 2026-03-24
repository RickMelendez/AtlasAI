"""
Interface para servicios de voz (Port en Clean Architecture).

Define el contrato para servicios de reconocimiento de voz,
wake word detection y síntesis de voz.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional


class VoiceService(ABC):
    """Interface abstracta para servicios de voz."""

    @abstractmethod
    async def transcribe_audio(self, audio_data: bytes, language: str = "es") -> str:
        """
        Transcribe audio a texto usando Whisper.

        Args:
            audio_data: Datos de audio en formato WAV/MP3
            language: Idioma del audio ("es" o "en")

        Returns:
            Texto transcrito
        """
        pass


class WakeWordService(ABC):
    """Interface abstracta para detección de wake words."""

    @abstractmethod
    async def detect_wake_word(
        self, audio_chunk: bytes, callback: Optional[Callable[[str], None]] = None
    ) -> Optional[str]:
        """
        Detecta wake words en un chunk de audio.

        Args:
            audio_chunk: Chunk de audio para analizar
            callback: Función a llamar cuando se detecta wake word

        Returns:
            Wake word detectado, o None si no se detectó nada
        """
        pass

    @abstractmethod
    def start_listening(self) -> None:
        """Inicia la escucha continua de wake words."""
        pass

    @abstractmethod
    def stop_listening(self) -> None:
        """Detiene la escucha de wake words."""
        pass


class TTSService(ABC):
    """Interface abstracta para síntesis de voz (Text-to-Speech)."""

    @abstractmethod
    async def synthesize_speech(self, text: str, language: str = "es") -> bytes:
        """
        Sintetiza texto a audio.

        Args:
            text: Texto a convertir en audio
            language: Idioma del texto ("es" o "en")

        Returns:
            Bytes de audio en formato MP3
        """
        pass

    @abstractmethod
    async def get_available_voices(self) -> list:
        """
        Obtiene la lista de voces disponibles.

        Returns:
            Lista de voces disponibles con id y nombre
        """
        pass

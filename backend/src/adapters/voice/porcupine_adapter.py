"""
Porcupine Adapter - Wake word detection usando Picovoice Porcupine.

Implementa WakeWordService usando Porcupine para detección de
wake words como "Hey Atlas", "Atlas", etc.
"""

import logging
import struct
from collections import deque
from typing import Callable, Optional

import pvporcupine

from ...application.interfaces.voice_service import WakeWordService
from ...infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class PorcupineAdapter(WakeWordService):
    """
    Adapter para Picovoice Porcupine.

    Usa Porcupine para detectar wake words en tiempo real
    en audio streaming.
    """

    def __init__(self, access_key: Optional[str] = None):
        """
        Inicializa el adapter de Porcupine.

        Args:
            access_key: Picovoice access key (opcional, se obtiene de settings)
        """
        settings = get_settings()
        self.access_key = access_key or settings.picovoice_access_key

        if not self.access_key:
            raise ValueError(
                "Picovoice access key not found. "
                "Set PICOVOICE_ACCESS_KEY in .env file."
            )

        self.porcupine = None
        self.is_listening = False

        # Wake words configurados
        self.wake_words = settings.wake_words

        # PCM frame buffer — accumulates samples until we have exactly frame_length.
        # deque gives O(1) popleft vs O(n) list slicing on every frame.
        self._pcm_buffer: deque[int] = deque()

        _pv_version = getattr(pvporcupine, "__version__", None) or getattr(
            pvporcupine, "VERSION", "unknown"
        )
        logger.info(f"✅ PorcupineAdapter initialized (pvporcupine {_pv_version})")

    def detect_wake_word(
        self, audio_chunk: bytes, callback: Optional[Callable[[str], None]] = None
    ) -> Optional[str]:
        """
        Detecta wake words en un chunk de audio.

        Acumula muestras en un buffer interno hasta tener exactamente
        `frame_length` muestras, luego llama a porcupine.process().

        Args:
            audio_chunk: Chunk de audio PCM de 16-bit, 16kHz (raw bytes)
            callback: Función a llamar cuando se detecta wake word

        Returns:
            Wake word detectado, o None si no se detectó nada
        """
        if not self.porcupine:
            return None

        try:
            # Decodificar bytes → int16 samples y meter al buffer
            num_samples = len(audio_chunk) // 2
            samples = list(struct.unpack_from(f"{num_samples}h", audio_chunk))
            self._pcm_buffer.extend(samples)

            frame_length = self.porcupine.frame_length  # typically 512

            # Procesar todos los frames completos disponibles en el buffer
            while len(self._pcm_buffer) >= frame_length:
                frame = [self._pcm_buffer.popleft() for _ in range(frame_length)]

                keyword_index = self.porcupine.process(frame)

                if keyword_index >= 0:
                    detected_keyword = (
                        self.wake_words[keyword_index]
                        if keyword_index < len(self.wake_words)
                        else "hey atlas"
                    )
                    logger.info(f"🎤 Wake word detected: '{detected_keyword}'")
                    if callback:
                        callback(detected_keyword)
                    return detected_keyword

            return None

        except Exception as e:
            logger.error(f"Error detecting wake word: {e}", exc_info=True)
            return None

    def start_listening(self) -> None:
        """
        Inicia la escucha continua de wake words.

        Busca el modelo custom (.ppn) en backend/models/.
        Si no existe, cae back al built-in "computer".
        """
        import os

        if self.is_listening:
            logger.warning("Porcupine already listening")
            return

        try:
            # Buscar modelo custom en backend/models/
            # El archivo puede llamarse hey-atlas_windows.ppn o similar
            models_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "models"
            )
            models_dir = os.path.abspath(models_dir)
            ppn_file = None

            if os.path.isdir(models_dir):
                for f in os.listdir(models_dir):
                    if f.endswith(".ppn"):
                        ppn_file = os.path.join(models_dir, f)
                        break

            if ppn_file:
                logger.info(
                    f"🎤 Loading custom wake word model: {os.path.basename(ppn_file)}"
                )
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keyword_paths=[ppn_file],
                )
                # Custom model — wake_words list just used for logging
                self.wake_words = [os.path.splitext(os.path.basename(ppn_file))[0]]
            else:
                # Fallback: built-in "computer" keyword while custom model isn't ready
                logger.warning(
                    "⚠️  No .ppn model found in backend/models/ — "
                    "falling back to built-in keyword 'computer'. "
                    "Say 'computer' to activate Atlas."
                )
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keywords=["computer"],
                )
                self.wake_words = ["computer"]

            self.is_listening = True
            logger.info(f"✅ Porcupine listening for: {self.wake_words}")

        except Exception as e:
            err_msg = str(e)
            if "not compatible" in err_msg or "version" in err_msg.lower():
                logger.error(
                    f"❌ Porcupine VERSION MISMATCH: {err_msg}\n"
                    f"   Installed SDK : pvporcupine {getattr(pvporcupine, '__version__', getattr(pvporcupine, 'VERSION', 'unknown'))}\n"
                    f"   Model file    : {os.path.basename(ppn_file) if ppn_file else 'N/A'}\n"
                    f"   FIX           : pip install 'pvporcupine>=4.0.0'"
                )
            else:
                logger.error(f"❌ Error starting Porcupine: {e}", exc_info=True)
            raise

    def stop_listening(self) -> None:
        """
        Detiene la escucha de wake words.

        Libera recursos de Porcupine.
        """
        try:
            if self.porcupine:
                self.porcupine.delete()
                self.porcupine = None

            self.is_listening = False
            logger.info("🛑 Porcupine stopped listening")

        except Exception as e:
            logger.error(f"Error stopping Porcupine: {e}")

    def get_sample_rate(self) -> int:
        """
        Obtiene el sample rate requerido por Porcupine.

        Returns:
            Sample rate en Hz (típicamente 16000)
        """
        if self.porcupine:
            return self.porcupine.sample_rate
        return 16000

    def get_frame_length(self) -> int:
        """
        Obtiene el tamaño de frame requerido por Porcupine.

        Returns:
            Frame length en samples
        """
        if self.porcupine:
            return self.porcupine.frame_length
        return 512


# Singleton instance
_porcupine_adapter_instance: Optional[PorcupineAdapter] = None


def get_porcupine_adapter() -> PorcupineAdapter:
    """
    Obtiene la instancia singleton del PorcupineAdapter.

    Returns:
        Instancia de PorcupineAdapter
    """
    global _porcupine_adapter_instance
    if _porcupine_adapter_instance is None:
        _porcupine_adapter_instance = PorcupineAdapter()
    return _porcupine_adapter_instance

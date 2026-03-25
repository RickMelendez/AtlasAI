import asyncio
import os
import tempfile
import logging
from faster_whisper import WhisperModel

from ...application.interfaces.voice_service import VoiceService

logger = logging.getLogger(__name__)


class FasterWhisperAdapter(VoiceService):
    """
    Local Whisper transcription using faster-whisper.
    No API key required. VAD filter eliminates hallucination on silence.
    First run downloads ~466MB model to ~/.cache/huggingface/
    """

    def __init__(self, model_size: str = "small"):
        logger.info(f"[Voice] Loading faster-whisper model: {model_size} (downloads on first run ~466MB)")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info(f"[Voice] Model loaded: {model_size}")

    async def transcribe_audio(self, audio_data: bytes, language: str = None) -> str:
        """
        Transcribe audio bytes. Returns empty string if no speech detected (VAD filtered).
        Eliminates 'thank you for watching' hallucination by filtering silence.
        """
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_data)
            path = f.name

        loop = asyncio.get_event_loop()
        try:
            segments, _info = await loop.run_in_executor(
                None,
                lambda: self.model.transcribe(
                    path,
                    language=language,
                    vad_filter=True,  # silero-VAD: returns empty on silence instead of hallucinating
                    vad_parameters={"min_silence_duration_ms": 500},
                    temperature=0,  # deterministic, less hallucination
                    condition_on_previous_text=False,
                )
            )
            text = " ".join(s.text for s in segments).strip()
            return text
        finally:
            os.unlink(path)

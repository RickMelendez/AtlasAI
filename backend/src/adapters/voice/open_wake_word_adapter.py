import logging
import numpy as np

logger = logging.getLogger(__name__)


class OpenWakeWordAdapter:
    """
    Wake word detection using openWakeWord. MIT license, fully local, no API key.
    Uses pre-trained models. Can be extended with custom 'hey_atlas' model later.
    """

    # Pre-trained models included with openwakeword package
    WAKE_WORDS = ["alexa", "hey_mycroft"]

    def __init__(self):
        from openwakeword.model import Model
        logger.info("[Voice] Loading openWakeWord models...")
        self.model = Model(wakeword_models=self.WAKE_WORDS, inference_framework="onnx")
        logger.info(f"[Voice] OpenWakeWord ready: {self.WAKE_WORDS}")

    def detect_wake_word(self, pcm_chunk: bytes) -> bool:
        """
        Process 80ms of 16kHz mono PCM audio (1280 samples, Int16 little-endian).
        Returns True if any wake word detected with confidence > 0.5.
        """
        if len(pcm_chunk) < 2560:  # 1280 samples x 2 bytes
            return False
        audio = np.frombuffer(pcm_chunk, dtype=np.int16)
        predictions = self.model.predict(audio)
        detected = any(score > 0.5 for score in predictions.values())
        if detected:
            logger.info(f"[Voice] Wake word detected! scores={predictions}")
        return detected

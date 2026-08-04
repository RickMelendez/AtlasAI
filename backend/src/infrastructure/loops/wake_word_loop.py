"""
Wake Word Loop — server-side microphone detection for local desktop mode.

Uses OpenWakeWord (local ONNX model, no API key) to detect "hey atlas"
directly from the system microphone. Only relevant when Atlas runs on the
same machine as the user (desktop mode).

For cloud deployments, wake word detection arrives via `audio_chunk` WebSocket
messages from the frontend — handled by WebSocketManager.handle_messages().

Install dependency for local mic access:
    pip install sounddevice
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# OpenWakeWord processes audio in 80ms chunks at 16 kHz mono PCM Int16
_SAMPLE_RATE = 16_000
_CHANNELS = 1
_CHUNK_DURATION_MS = 80                                      # milliseconds per chunk
_CHUNK_SAMPLES = int(_SAMPLE_RATE * _CHUNK_DURATION_MS / 1000)  # 1280 samples
_OWW_CHUNK_BYTES = _CHUNK_SAMPLES * 2                        # Int16 → 2560 bytes


async def run_wake_word_loop(
    stop_event: asyncio.Event,
    wake_word_adapter,
    on_detected: Callable[[], Awaitable[None]],
    cooldown_secs: float = 3.0,
) -> None:
    """
    Continuously listen on the system microphone for the wake word.

    Streams 80ms PCM chunks to OpenWakeWordAdapter. When the wake word is
    detected, calls on_detected() (an async callback) and then observes a
    cooldown period to avoid double-triggers.

    Args:
        stop_event:         Set this to stop the loop gracefully.
        wake_word_adapter:  OpenWakeWordAdapter instance (already initialised).
        on_detected:        Async callback fired on each wake-word detection.
        cooldown_secs:      Seconds to wait after detection before listening again.
    """
    # sounddevice is an optional dependency — only needed for local desktop mode
    try:
        import sounddevice as sd  # type: ignore
    except ImportError:
        logger.warning(
            "[WakeWord] sounddevice not installed — server-side mic loop disabled.\n"
            "  To enable: pip install sounddevice\n"
            "  (Not needed for cloud/web deployments — the frontend sends audio.)"
        )
        return

    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)

    def _audio_callback(indata, frames, time_info, status) -> None:
        """sounddevice calls this on every captured chunk (not async)."""
        if status:
            logger.debug(f"[WakeWord] Audio callback status: {status}")
        # Convert float32 → Int16 PCM
        import numpy as np  # type: ignore
        pcm = (indata[:, 0] * 32_767).clip(-32_768, 32_767).astype("int16").tobytes()
        # Non-blocking put; drop frames if queue is full (avoids backpressure)
        try:
            loop.call_soon_threadsafe(audio_queue.put_nowait, pcm)
        except asyncio.QueueFull:
            pass

    logger.info("[WakeWord] Opening system microphone — listening for 'Hey Atlas'…")

    try:
        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="float32",
            blocksize=_CHUNK_SAMPLES,
            callback=_audio_callback,
        ):
            pcm_buffer = bytearray()

            while not stop_event.is_set():
                # Drain the queue with a short timeout so we check stop_event regularly
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                pcm_buffer.extend(chunk)

                # Process complete 2560-byte frames
                while len(pcm_buffer) >= _OWW_CHUNK_BYTES:
                    oww_chunk = bytes(pcm_buffer[:_OWW_CHUNK_BYTES])
                    del pcm_buffer[:_OWW_CHUNK_BYTES]

                    try:
                        # OpenWakeWord inference is CPU-bound → run in thread pool
                        detected: bool = await loop.run_in_executor(
                            None,
                            wake_word_adapter.detect_wake_word,
                            oww_chunk,
                        )
                    except Exception as e:
                        logger.error(f"[WakeWord] Inference error: {e}")
                        break

                    if detected:
                        logger.info("[WakeWord] 🎙️  'Hey Atlas' detected from microphone")
                        pcm_buffer.clear()  # Prevent double-trigger on buffered audio
                        try:
                            await on_detected()
                        except Exception as cb_err:
                            logger.error(f"[WakeWord] on_detected callback error: {cb_err}")
                        # Cooldown: stop processing mic audio briefly
                        await asyncio.sleep(cooldown_secs)
                        # Flush any audio that arrived during cooldown
                        while not audio_queue.empty():
                            try:
                                audio_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        pcm_buffer.clear()
                        break  # Re-enter outer while loop

    except Exception as e:
        logger.error(f"[WakeWord] Microphone loop error: {e}", exc_info=True)
    finally:
        logger.info("[WakeWord] Wake word loop stopped")

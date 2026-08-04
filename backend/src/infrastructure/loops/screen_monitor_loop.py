"""
Screen Monitor Loop — server-side screen capture + Claude Vision analysis.

Runs as a background asyncio task. On each cycle it:
  1. Captures the primary monitor with MSSCaptureAdapter (no permissions dialog).
  2. Sends the JPEG to ClaudeVisionAdapter → gets structured JSON analysis.
  3. Updates the screen context for every active WebSocket session.
  4. Emits SCREEN_CONTEXT_UPDATED (picked up by main.py proactive-help handler).
  5. If errors are visible AND cooldown elapsed, emits PROACTIVE_HELP_TRIGGERED
     for each active session so Atlas can speak up without being asked.

When to use this loop vs. the frontend sending screen frames:
  - Local desktop:  this loop captures directly (no user action required).
  - Cloud/Railway:  MSS grabs the empty server screen, so disable it and rely
                    on the frontend sending `screen_capture` WebSocket messages.
  - Control flag:   set ATLAS_SCREEN_MONITOR=false in .env to disable.
"""

import asyncio
import base64
import logging
import time
from typing import Optional

from src.infrastructure.events.event_bus import event_bus
from src.infrastructure.events.event_types import EventType

logger = logging.getLogger(__name__)

# ── Tuneable constants ─────────────────────────────────────────────────────────
_DEFAULT_INTERVAL_SECS: float = 10.0    # How often to capture (seconds)
_PROACTIVE_COOLDOWN_SECS: float = 60.0  # Min gap between proactive messages
_ERROR_KEYWORDS = (
    "error",
    "exception",
    "traceback",
    "warning",
    "⚠️",
    "fatal",
    "failed",
    "undefined",
    "null pointer",
)


async def run_screen_monitor_loop(
    stop_event: asyncio.Event,
    screen_service,           # ClaudeVisionAdapter
    ws_manager,               # WebSocketManager singleton
    interval_secs: float = _DEFAULT_INTERVAL_SECS,
) -> None:
    """
    Continuously capture, analyse, and broadcast screen context.

    Args:
        stop_event:     Set to stop the loop gracefully.
        screen_service: Initialised ClaudeVisionAdapter.
        ws_manager:     WebSocketManager singleton (provides active sessions).
        interval_secs:  Seconds between capture/analysis cycles.
    """
    # MSSCaptureAdapter is an optional desktop dependency
    try:
        from src.adapters.vision.mss_capture_adapter import MSSCaptureAdapter
        mss_adapter = MSSCaptureAdapter()
    except ImportError:
        logger.warning(
            "[ScreenMonitor] mss not installed — server-side capture loop disabled.\n"
            "  To enable: pip install mss\n"
            "  (Not needed for cloud deployments — the frontend sends screen frames.)"
        )
        return
    except Exception as mss_err:
        logger.warning(
            f"[ScreenMonitor] Could not initialise MSSCaptureAdapter: {mss_err}. "
            "Loop disabled."
        )
        return

    logger.info(
        f"[ScreenMonitor] 🖥️  Starting — capture every {interval_secs}s, "
        f"proactive cooldown {_PROACTIVE_COOLDOWN_SECS}s"
    )

    loop = asyncio.get_running_loop()
    _last_proactive_ts: float = 0.0  # monotonic timestamp of last proactive trigger

    while not stop_event.is_set():
        cycle_start = time.monotonic()

        try:
            # ── 1. Capture primary screen ──────────────────────────────────────
            # MSSCaptureAdapter.capture_primary_screen() is synchronous (CPU-bound)
            b64_image: Optional[str] = await loop.run_in_executor(
                None, mss_adapter.capture_primary_screen
            )

            if not b64_image:
                logger.debug("[ScreenMonitor] Empty capture — skipping")
                await _sleep_remainder(cycle_start, interval_secs, stop_event)
                continue

            # ── 2. Analyse with Claude Vision ──────────────────────────────────
            screenshot_bytes = base64.b64decode(b64_image)
            await screen_service.extract_text_from_image(screenshot_bytes)

            description: Optional[str] = getattr(
                screen_service, "last_screen_description", None
            )

            if not description:
                logger.debug("[ScreenMonitor] No description from Vision — skipping")
                await _sleep_remainder(cycle_start, interval_secs, stop_event)
                continue

            logger.debug(f"[ScreenMonitor] Context: {description[:140]}")

            # ── 3. Push context to all active sessions ─────────────────────────
            active_sessions = list(ws_manager.active_connections.keys())
            for session_id in active_sessions:
                ws_manager.update_screen_context(session_id, description)

            # ── 4. Emit SCREEN_CONTEXT_UPDATED on event bus ────────────────────
            # main.py's handler reads this; marking source="server_loop" so it
            # can skip re-analysis if needed (avoids double Claude Vision calls).
            for session_id in active_sessions:
                await event_bus.emit(
                    EventType.SCREEN_CONTEXT_UPDATED.value,
                    {
                        "session_id": session_id,
                        "screenshot_data": b64_image,
                        "description": description,
                        "source": "server_loop",    # distinguishes from frontend frames
                        "timestamp": time.time(),
                    },
                )

            # ── 5. Proactive error detection ───────────────────────────────────
            now = time.monotonic()
            has_error = any(kw in description.lower() for kw in _ERROR_KEYWORDS)

            if has_error and (now - _last_proactive_ts) > _PROACTIVE_COOLDOWN_SECS:
                _last_proactive_ts = now
                logger.info(
                    f"[ScreenMonitor] Error keywords detected: "
                    f"'{description[:80]}…' — firing proactive help"
                )
                for session_id in active_sessions:
                    state = ws_manager.get_state(session_id)
                    # Only interrupt if Atlas is awake and not already speaking
                    if state and state.mode.value == "active":
                        await event_bus.emit(
                            EventType.PROACTIVE_HELP_TRIGGERED.value,
                            {
                                "session_id": session_id,
                                "description": description,
                                "source": "screen_monitor_loop",
                            },
                        )
                        logger.info(
                            f"[ScreenMonitor] [{session_id}] PROACTIVE_HELP_TRIGGERED"
                        )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[ScreenMonitor] Cycle error: {e}", exc_info=True)

        await _sleep_remainder(cycle_start, interval_secs, stop_event)

    logger.info("[ScreenMonitor] Screen monitor loop stopped")


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _sleep_remainder(
    cycle_start: float,
    interval_secs: float,
    stop_event: asyncio.Event,
) -> None:
    """Sleep only the remaining time in the interval (accounts for analysis time)."""
    elapsed = time.monotonic() - cycle_start
    remaining = max(0.0, interval_secs - elapsed)
    if remaining > 0:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            pass  # Normal — stop_event wasn't set, we just slept out the interval

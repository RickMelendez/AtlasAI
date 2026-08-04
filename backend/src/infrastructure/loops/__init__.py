"""
Continuous background loops for Atlas AI (local desktop mode).

  wake_word_loop    — reads system microphone → OpenWakeWord detection
  screen_monitor_loop — captures primary screen → Claude Vision analysis

Both loops are optional: they degrade gracefully when their dependencies
(sounddevice, mss) are absent or when running in a cloud environment
where the frontend provides audio/screen data via WebSocket instead.
"""

from .wake_word_loop import run_wake_word_loop
from .screen_monitor_loop import run_screen_monitor_loop

__all__ = ["run_wake_word_loop", "run_screen_monitor_loop"]

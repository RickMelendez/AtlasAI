"""
Shared slowapi Limiter — imported by main.py (registers app.state.limiter +
the exception handler) and by any route module that needs @limiter.limit(...).

Per-IP limiting only (get_remote_address). Atlas runs as a single Railway
instance with no shared cache between workers, so this is process-local —
sufficient for the current single-instance deployment, not for a future
multi-instance one (see CODE-REVIEW.md Critical: no cost controls anywhere).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

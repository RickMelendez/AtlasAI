"""
Sentry — Error monitoring for Atlas AI backend.

Captures:
  • Unhandled FastAPI/Starlette exceptions (via SentryAsgiMiddleware)
  • WebSocket errors (manual capture in ws manager)
  • Porcupine / Whisper / Claude API errors (manual capture)
  • Python unhandled exceptions & asyncio task failures

Setup:
  1. Create a project at https://sentry.io (choose Python → FastAPI)
  2. Copy the DSN and add it to backend/.env:
       SENTRY_DSN=https://xxxx@oXXXX.ingest.sentry.io/YYYY
  3. pip install "sentry-sdk[fastapi]"
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_initialized = False


def init_sentry(
    dsn: Optional[str], environment: str = "development", release: str = "dev"
) -> bool:
    """
    Initialise Sentry SDK.

    Called once from main.py lifespan startup.

    Returns True if Sentry was initialised, False if DSN is missing/empty.
    """
    global _initialized

    if not dsn:
        logger.warning("⚠️  SENTRY_DSN not set — backend error monitoring disabled")
        return False

    if _initialized:
        return True

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            integrations=[
                # Captures FastAPI route errors automatically
                FastApiIntegration(),
                # Captures Starlette middleware / websocket errors
                StarletteIntegration(),
                # Forwards ERROR+ log records to Sentry as breadcrumbs
                LoggingIntegration(
                    level=logging.INFO,  # breadcrumb level
                    event_level=logging.ERROR,  # send as event at ERROR+
                ),
            ],
            # Capture 100% of errors
            sample_rate=1.0,
            # Performance traces: 5% in production
            traces_sample_rate=0.05 if environment == "production" else 0,
            # Don't send PII (user IPs etc.)
            send_default_pii=False,
            before_send=_scrub_secrets,
        )

        _initialized = True
        logger.info(f"✅ Sentry initialised — env: {environment}")
        return True

    except ImportError:
        logger.warning(
            "⚠️  sentry-sdk not installed — run: pip install 'sentry-sdk[fastapi]'"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to initialise Sentry: {e}")
        return False


def _scrub_secrets(event: dict, hint: dict) -> dict:
    """Remove sensitive keys from Sentry events before they are sent."""
    _strip_from = [
        event.get("request", {}).get("headers", {}),
        event.get("extra", {}),
    ]
    secret_keys = {"authorization", "x-api-key", "anthropic-api-key", "cookie"}
    for d in _strip_from:
        for key in list(d.keys()):
            if key.lower() in secret_keys:
                del d[key]
    return event


# ── Convenience helpers ───────────────────────────────────────────────────────


def capture_exception(exc: Exception, **extras) -> None:
    """Capture an exception with optional extra context."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in extras.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # never let Sentry break the app


def capture_message(msg: str, level: str = "info", **extras) -> None:
    """Capture a message event."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in extras.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(msg, level=level)
    except Exception:
        pass


def set_session_context(session_id: str) -> None:
    """Tag the current scope with a WebSocket session ID."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_tag("session_id", session_id)
    except Exception:
        pass

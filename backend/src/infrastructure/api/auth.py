"""
Shared-secret authentication for HTTP routes and the WebSocket endpoint.

Atlas is designed to run locally with zero friction. When ATLAS_API_KEY is
unset, every request is allowed (local dev, matches the app's current
default deployment story). The moment a deployment sets ATLAS_API_KEY —
which any public Railway deploy must — every gated route and the WebSocket
handshake require it, closing the "anyone with the URL can burn your
Anthropic credits" hole (see CODE-REVIEW.md Security Critical #1).
"""

import logging
import secrets

from fastapi import Header, HTTPException, WebSocket, status

from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-Atlas-Key"


async def require_api_key(
    x_atlas_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """FastAPI dependency — gates a route behind ATLAS_API_KEY when one is configured."""
    settings = get_settings()
    if not settings.atlas_api_key:
        return  # no key configured — local dev, unauthenticated by design
    if not x_atlas_key or not secrets.compare_digest(x_atlas_key, settings.atlas_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def verify_websocket_key(websocket: WebSocket) -> bool:
    """
    Checks ATLAS_API_KEY against the `key` query parameter.

    Browsers' native WebSocket API cannot set custom headers, so the key
    travels as a query param on the connect URL instead — same trust
    boundary as the HTTP header, just a different transport.
    """
    settings = get_settings()
    if not settings.atlas_api_key:
        return True
    provided = websocket.query_params.get("key")
    return bool(provided) and secrets.compare_digest(provided, settings.atlas_api_key)

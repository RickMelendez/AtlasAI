"""
Settings API Routes - GET and POST endpoints for application settings.

Handles reading/writing configuration from .env file.
Only exposes non-secret settings (masks API keys).
"""

import logging
import os
from typing import Dict, Optional

from fastapi import APIRouter

from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def mask_api_key(key: Optional[str]) -> Optional[str]:
    """Mask API key for display (show first 8 chars + ...)."""
    if not key:
        return None
    if len(key) <= 8:
        return "..."
    return key[:8] + "..."


@router.get("/settings")
async def get_settings_endpoint() -> Dict:
    """
    Get current settings (masks API keys).

    Returns:
        Dictionary of settings with masked API keys
    """
    settings = get_settings()
    return {
        "anthropic_api_key": mask_api_key(settings.anthropic_api_key),
        "elevenlabs_api_key": mask_api_key(settings.elevenlabs_api_key),
        "elevenlabs_voice_id": settings.elevenlabs_voice_id,
        "fish_audio_api_key": mask_api_key(settings.fish_audio_api_key),
        "fish_audio_voice_id": settings.fish_audio_voice_id,
        "notion_api_key": mask_api_key(settings.notion_api_key),
    }


@router.post("/settings")
async def update_settings_endpoint(data: Dict) -> Dict:
    """
    Update settings from request body and write to .env file.

    Only allows updating: anthropic_api_key, elevenlabs_api_key,
    elevenlabs_voice_id, fish_audio_api_key, fish_audio_voice_id,
    notion_api_key. Never exposes sentry_dsn.

    Args:
        data: Dictionary with settings to update

    Returns:
        Updated settings (with masked keys)
    """
    allowed_settings = {
        "anthropic_api_key",
        "elevenlabs_api_key",
        "elevenlabs_voice_id",
        "fish_audio_api_key",
        "fish_audio_voice_id",
        "notion_api_key",
    }

    env_updates = {}
    for key in allowed_settings:
        if key in data and data[key]:
            env_updates[key.upper()] = str(data[key])

    # Write to .env file
    try:
        _write_env_file(env_updates)
        logger.info("Settings updated successfully")
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise

    return await get_settings_endpoint()


def _write_env_file(updates: Dict[str, str]) -> None:
    """
    Write updates to .env file.

    Args:
        updates: Dictionary of settings to write
    """
    env_path = ".env"

    # Read existing .env
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    # Update with new values
    env_vars.update(updates)

    # Write back to .env
    with open(env_path, "w") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")

    logger.info(f"Wrote {len(updates)} settings to .env")

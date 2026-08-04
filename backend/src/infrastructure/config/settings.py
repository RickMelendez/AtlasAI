"""
Configuración de la aplicación Atlas AI.

Este módulo define todas las configuraciones de la aplicación
usando Pydantic Settings para cargar desde variables de entorno.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuración de la aplicación.

    Carga automáticamente valores desde:
    1. Variables de entorno
    2. Archivo .env
    3. Valores por defecto
    """

    # Shared-secret auth for HTTP routes + WebSocket.
    # Unset (default) = unauthenticated, for local dev. Any public deployment
    # (Railway, etc.) MUST set this — see CODE-REVIEW.md Security Critical #1.
    atlas_api_key: Optional[str] = None

    # API Keys
    anthropic_api_key: str = ""
    fish_audio_api_key: Optional[str] = None   # Optional — edge-tts used as free fallback
    fish_audio_voice_id: Optional[str] = None  # Override default voice ID
    elevenlabs_api_key: Optional[str] = None   # Optional — ElevenLabs TTS
    elevenlabs_voice_id: Optional[str] = None  # Override default ElevenLabs voice
    notion_api_key: Optional[str] = None

    # Error Monitoring
    # Create a project at https://sentry.io → Python → FastAPI, then paste the DSN here
    sentry_dsn: Optional[str] = None

    # App Configuration
    app_name: str = "Atlas AI Visual Companion"
    # False by default — DEBUG=True enables verbose SQL echo (database/base.py)
    # and marks the Sentry environment "development"; only turn it on locally.
    # .env.example already documents DEBUG=false as the deployed value.
    debug: bool = False
    log_level: str = "INFO"

    # Atlas Mode — controls which system prompt/personality Atlas uses
    # "desktop" → original desktop assistant (watches screen, helps with code, Notion, etc.)
    # "game"    → gaming companion (reacts to combat, quests, health bars, stays brief)
    atlas_mode: str = "desktop"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./atlas.db"

    # WebSocket Configuration
    websocket_ping_interval: int = 30  # seconds
    websocket_timeout: int = 300  # seconds

    # Screen Capture Configuration
    screen_capture_interval: int = 3  # seconds
    screen_capture_quality: int = 80  # 0-100

    # Wake Word Configuration
    wake_words: list[str] = ["atlas", "hey atlas", "hello atlas", "hola atlas"]

    # Local Desktop Loops
    # Set these to True only when running Atlas on your own machine.
    # For Railway/cloud deployment, the frontend sends audio+screen via WebSocket.
    screen_monitor_enabled: bool = False  # server-side screen capture + Vision loop
    wake_word_local_enabled: bool = False  # server-side microphone wake word loop

    # Supervisor (Agentic OS) — ver docs/agentic-os-supervisor.md
    supervisor_enabled: bool = False  # master switch for the supervisor dispatcher
    supervisor_kill_switch: bool = False  # settings-level kill; DB flag is the 2nd layer
    supervisor_daily_budget_calls: int = 25  # "expensive" dispatches allowed per UTC day
    supervisor_default_timeout_ms: int = 60_000
    supervisor_max_timeout_ms: int = 300_000  # hard cap — planner output gets clamped
    supervisor_idempotency_window_secs: int = 600  # dedup window for repeated subtasks

    class Config:
        """Configuración de Pydantic Settings."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Obtiene la instancia singleton de Settings.

    Usa lru_cache para asegurar que solo se crea una instancia.

    Returns:
        Instancia de Settings
    """
    return Settings()

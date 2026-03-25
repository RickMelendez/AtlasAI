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
    debug: bool = True
    log_level: str = "INFO"

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

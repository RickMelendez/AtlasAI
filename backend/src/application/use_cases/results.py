"""
Tipos de retorno compartidos para los use cases de Atlas.

Centraliza las firmas de retorno para que los llamadores (p.ej. WebSocketManager)
tengan tipos explícitos en lugar de depender de dicts sin esquema.
"""

from typing import Any, Dict, Optional

from typing_extensions import TypedDict


class VoiceCommandResult(TypedDict):
    """Resultado del pipeline completo de voz: STT → AI → TTS."""

    transcription: str  # Texto transcrito por Whisper
    response: str  # Respuesta de texto generada por Claude
    audio_response_b64: Optional[
        str
    ]  # Audio MP3 base64 (ElevenLabs), None si no hay TTS
    has_audio: bool  # True si audio_response_b64 contiene datos
    success: bool  # False si el pipeline falló en algún punto
    error: Optional[str]  # Descripción del error, None en caso de éxito


class ChatMessageResult(TypedDict):
    """Resultado del procesamiento de un mensaje de chat de texto."""

    response: str  # Respuesta de texto generada por Claude
    session_id: str  # ID de la sesión que generó la respuesta
    timestamp: str  # ISO 8601 timestamp de la respuesta
    error: Optional[str]  # Descripción del error, None en caso de éxito


class ScreenAnalysisResult(TypedDict):
    """Resultado del análisis de captura de pantalla."""

    screen_text: str  # Texto extraído por OCR (truncado a 500 chars)
    app_context: Dict[str, Any]  # {"app": "vscode"|"browser"|..., "details": {...}}
    errors_detected: Dict[str, Any]  # {"has_error": bool, "error_type": ..., ...}
    ai_analysis: Dict[str, Any]  # Análisis de Claude (vacío si no hubo error)
    should_offer_help: bool  # True si Atlas debe ofrecer ayuda proactiva
    help_suggestion: Optional[str]  # Texto de sugerencia, None si no aplica

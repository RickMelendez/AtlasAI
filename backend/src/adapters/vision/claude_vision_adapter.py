"""
Claude Vision Adapter — reemplaza Tesseract OCR con análisis visual via Claude Haiku.

Envía frames JPEG/PNG directamente a Claude claude-haiku-4-5 con soporte de imágenes y obtiene
descripción estructurada de:
  - App/página visible
  - Errores en pantalla
  - Actividad actual del usuario

No requiere instalar binarios externos — usa el paquete anthropic ya instalado.
"""

import base64
import json
import logging
import time
from typing import Any, Dict, Optional

from anthropic import AsyncAnthropic

from ...application.interfaces.screen_service import ScreenService
from ...infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

# Prompt que pide a Claude Haiku analizar el screenshot y devolver JSON estructurado
_VISION_PROMPT = """Analyze this screenshot and return ONLY valid JSON with this exact structure (no extra text):
{
  "app": "vscode|browser|terminal|slack|notion|unknown",
  "url": "https://... or null",
  "visible_text_summary": "brief description of what is visible (max 200 chars)",
  "errors": [{"type": "error type", "message": "error message"}],
  "user_activity": "what the user appears to be doing"
}
Rules: app field must be one of the enum values. errors is an empty array if no errors are visible."""


class ClaudeVisionAdapter(ScreenService):
    """
    Adapter de visión usando Claude Haiku con soporte de imágenes.

    Implementa ScreenService. Un único análisis por frame: los tres métodos
    de la interfaz comparten el caché del último análisis para no duplicar
    llamadas a la API.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self._api_key = api_key or settings.anthropic_api_key
        self._client = AsyncAnthropic(api_key=self._api_key)
        self._last_analysis: Optional[Dict[str, Any]] = None
        # Último análisis como texto legible para pasar a los prompts de chat
        self._last_screen_description: Optional[str] = None
        logger.info("✅ ClaudeVisionAdapter initialized (Claude Haiku vision)")

    @property
    def last_screen_description(self) -> Optional[str]:
        """Descripción legible de la pantalla actual para incluir en prompts de chat."""
        return self._last_screen_description

    def _detect_media_type(self, image_data: bytes) -> str:
        """Detecta JPEG o PNG a partir de los primeros bytes del archivo."""
        if image_data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        return "image/jpeg"

    async def extract_text_from_image(
        self, image_data: bytes, language: str = "eng"
    ) -> str:
        """
        Analiza el screenshot con Claude Haiku vision y almacena el resultado en caché.

        Returns:
            visible_text_summary del análisis (mantiene compatibilidad con la interfaz).
        """
        try:
            media_type = self._detect_media_type(image_data)
            b64_image = base64.b64encode(image_data).decode("utf-8")

            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_image,
                                },
                            },
                            {"type": "text", "text": _VISION_PROMPT},
                        ],
                    }
                ],
            )

            raw = response.content[0].text if response.content else "{}"

            # Limpiar posibles backticks o prefijos de markdown
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            analysis = json.loads(raw)
            self._last_analysis = analysis

            # Construir descripción legible para los prompts de chat
            parts = []
            if analysis.get("app") and analysis["app"] != "unknown":
                parts.append(f"App: {analysis['app']}")
            if analysis.get("url"):
                parts.append(f"URL: {analysis['url']}")
            if analysis.get("visible_text_summary"):
                parts.append(analysis["visible_text_summary"])
            if analysis.get("user_activity"):
                parts.append(f"Actividad: {analysis['user_activity']}")
            if analysis.get("errors"):
                for err in analysis["errors"]:
                    parts.append(f"⚠️ Error: {err.get('message', '')}")

            self._last_screen_description = " | ".join(parts) if parts else None

            logger.debug(f"[Vision] Analysis: {self._last_screen_description}")
            return analysis.get("visible_text_summary", "")

        except json.JSONDecodeError as e:
            logger.warning(f"[Vision] JSON parse error: {e} — raw: {raw[:200]}")
            self._last_analysis = None
            return ""
        except Exception as e:
            logger.error(f"[Vision] Error analyzing screenshot: {e}")
            self._last_analysis = None
            return ""

    async def detect_app_context(self, screen_text: str) -> Dict[str, Any]:
        """
        Devuelve el contexto de app del último análisis cacheado.
        No hace llamadas adicionales a la API.
        """
        if not self._last_analysis:
            return {"app": "unknown", "details": {}}

        app = self._last_analysis.get("app", "unknown")
        details: Dict[str, Any] = {}
        if self._last_analysis.get("url"):
            details["url"] = self._last_analysis["url"]
        if self._last_analysis.get("user_activity"):
            details["activity"] = self._last_analysis["user_activity"]

        return {"app": app, "details": details}

    async def detect_errors(
        self, screen_text: str, app_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Devuelve errores detectados del último análisis cacheado.
        No hace llamadas adicionales a la API.
        """
        if not self._last_analysis:
            return {"has_error": False, "error_type": "", "error_message": "", "line_number": None}

        errors = self._last_analysis.get("errors", [])
        if not errors:
            return {"has_error": False, "error_type": "", "error_message": "", "line_number": None}

        first = errors[0]
        return {
            "has_error": True,
            "error_type": first.get("type", "error"),
            "error_message": first.get("message", ""),
            "line_number": None,
        }

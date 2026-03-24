"""
Interface para servicios de visión (Port en Clean Architecture).

Define el contrato para servicios de captura y análisis de pantalla.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ScreenService(ABC):
    """Interface abstracta para servicios de visión."""

    @abstractmethod
    async def extract_text_from_image(
        self, image_data: bytes, language: str = "eng"
    ) -> str:
        """
        Extrae texto de una imagen usando OCR.

        Args:
            image_data: Datos de la imagen (PNG, JPG, etc.)
            language: Idioma para OCR (tesseract format: "eng", "spa", etc.)

        Returns:
            Texto extraído de la imagen
        """
        pass

    @abstractmethod
    async def detect_app_context(self, screen_text: str) -> Dict[str, Any]:
        """
        Detecta el contexto de la aplicación activa basándose en el texto.

        Args:
            screen_text: Texto extraído de la pantalla

        Returns:
            Diccionario con información del contexto:
            {
                "app": "vscode" | "browser" | "terminal" | "unknown",
                "details": {...}  # Información adicional específica de la app
            }
        """
        pass

    @abstractmethod
    async def detect_errors(
        self, screen_text: str, app_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Detecta errores visibles en el texto de pantalla.

        Args:
            screen_text: Texto de la pantalla
            app_context: Contexto de la aplicación activa

        Returns:
            Diccionario con errores detectados:
            {
                "has_error": bool,
                "error_type": str,
                "error_message": str,
                "line_number": Optional[int]
            }
        """
        pass

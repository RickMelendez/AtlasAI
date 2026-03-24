"""
Interface para servicios de AI (Port en Clean Architecture).

Define el contrato que deben implementar todos los adapters de AI
(Claude, OpenAI, etc.) para mantener la arquitectura limpia.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AIService(ABC):
    """
    Interface abstracta para servicios de AI.

    Los adapters concretos (ClaudeAdapter, OpenAIAdapter, etc.)
    deben implementar estos métodos.
    """

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        screen_context: Optional[str] = None,
        language: str = "es",
    ) -> str:
        """
        Genera una respuesta del AI dada un mensaje del usuario.

        Args:
            user_message: Mensaje del usuario
            conversation_history: Historial de conversación (opcional)
            screen_context: Contexto de la pantalla capturada (opcional)
            language: Idioma preferido ("es" o "en")

        Returns:
            Respuesta generada por el AI
        """
        pass

    @abstractmethod
    async def analyze_screen_context(
        self, screen_text: str, app_context: Optional[str] = None, language: str = "es"
    ) -> Dict[str, Any]:
        """
        Analiza el contexto de la pantalla para detectar errores o situaciones.

        Args:
            screen_text: Texto extraído de la pantalla con OCR
            app_context: Contexto de la aplicación activa (VS Code, browser, etc.)
            language: Idioma preferido

        Returns:
            Diccionario con análisis:
            {
                "has_error": bool,
                "error_description": str,
                "suggested_help": str,
                "urgency": "low" | "medium" | "high"
            }
        """
        pass

    @abstractmethod
    async def offer_proactive_help(
        self,
        screen_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "es",
    ) -> Optional[str]:
        """
        Determina si debe ofrecer ayuda proactiva basándose en el contexto.

        Args:
            screen_context: Contexto actual de la pantalla
            conversation_history: Historial de conversación
            language: Idioma preferido

        Returns:
            Sugerencia de ayuda proactiva, o None si no es necesario
        """
        pass

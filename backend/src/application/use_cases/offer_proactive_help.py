"""
Use Case: Ofrecer Ayuda Proactiva

Determina si Atlas debe ofrecer ayuda sin que se lo pidan,
basándose en el contexto de pantalla y conversación.
"""

import logging
from typing import Dict, List, Optional

from ...application.interfaces.ai_service import AIService
from ...domain.entities.assistant_state import AssistantState

logger = logging.getLogger(__name__)


class OfferProactiveHelpUseCase:
    """
    Use case para determinar cuándo ofrecer ayuda proactiva.

    No debe ser intrusivo - solo ofrece ayuda cuando hay un problema claro.
    """

    def __init__(self, ai_service: AIService, assistant_state: AssistantState):
        """
        Inicializa el use case.

        Args:
            ai_service: Servicio de AI (Claude)
            assistant_state: Estado del asistente
        """
        self.ai_service = ai_service
        self.assistant_state = assistant_state

    async def execute(
        self,
        screen_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        errors_detected: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Determina si debe ofrecer ayuda proactiva.

        Args:
            screen_context: Contexto de pantalla
            conversation_history: Historial de conversación
            errors_detected: Errores detectados previamente

        Returns:
            Sugerencia de ayuda, o None si no debe ofrecer ayuda
        """
        try:
            # Solo ofrecer ayuda si está ACTIVE (no si está hablando o pensando)
            if not self.assistant_state.is_active():
                return None

            # Si hay errores detectados con urgencia alta, ofrecer ayuda
            if errors_detected and errors_detected.get("has_error"):
                urgency = errors_detected.get("urgency", "low")

                if urgency == "high":
                    # Usar Claude para generar sugerencia contextual
                    suggestion = await self.ai_service.offer_proactive_help(
                        screen_context=screen_context,
                        conversation_history=conversation_history,
                        language=self.assistant_state.language,
                    )

                    if suggestion:
                        logger.info(f"💡 Offering proactive help: {suggestion[:50]}...")
                        return suggestion

            return None

        except Exception as e:
            logger.error(f"Error determining proactive help: {e}")
            return None

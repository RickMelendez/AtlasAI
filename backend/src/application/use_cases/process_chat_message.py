"""
Use Case: Process Chat Message

Procesa mensajes de chat del usuario y genera respuestas usando Claude.
"""

import logging
from typing import Optional

from src.application.interfaces.ai_service import AIService
from src.application.use_cases.results import ChatMessageResult
from src.domain.entities.assistant_state import AssistantState

logger = logging.getLogger(__name__)


class ProcessChatMessageUseCase:
    """
    Procesa mensajes de chat del usuario y genera respuestas con Claude.

    Este use case:
    1. Recibe un mensaje del usuario
    2. Usa Claude para generar una respuesta conversacional
    3. Devuelve la respuesta para enviar al frontend

    Args:
        ai_service: Servicio de IA (Claude)
    """

    def __init__(self, ai_service: AIService, tool_executor=None):
        """
        Inicializa el use case con las dependencias necesarias.

        Args:
            ai_service: Servicio de IA para generar respuestas
            tool_executor: ToolExecutor opcional — activa herramientas en Claude
        """
        self.ai_service = ai_service
        self.tool_executor = tool_executor

    async def execute(
        self,
        message: str,
        assistant_state: AssistantState,
        screen_context: Optional[str] = None,
    ) -> ChatMessageResult:
        """
        Procesa un mensaje de chat y genera una respuesta.

        Args:
            message: Mensaje del usuario
            assistant_state: Estado actual del asistente
            screen_context: Contexto de pantalla opcional

        Returns:
            Diccionario con la respuesta generada:
            {
                "response": str,
                "session_id": str,
                "timestamp": str
            }
        """
        try:
            logger.info(
                f"[{assistant_state.session_id}] Processing chat message: {message[:50]}..."
            )

            # Generar respuesta con Claude (con herramientas si están disponibles)
            response = await self.ai_service.generate_response(
                user_message=message,
                screen_context=screen_context,
                language=assistant_state.language,
                tool_executor=self.tool_executor,
                session_id=assistant_state.session_id,
            )

            logger.info(
                f"[{assistant_state.session_id}] Response generated: {response[:50]}..."
            )

            from datetime import datetime

            return {
                "response": response,
                "session_id": assistant_state.session_id,
                "timestamp": datetime.now().isoformat(),
                "error": None,
            }

        except Exception as e:
            logger.error(
                f"[{assistant_state.session_id}] Error processing chat message: {e}",
                exc_info=True,
            )

            from datetime import datetime

            error_detail = type(e).__name__ + ": " + str(e)
            return {
                "response": f"❌ Error: {error_detail}",
                "session_id": assistant_state.session_id,
                "timestamp": datetime.now().isoformat(),
                "error": error_detail,
            }

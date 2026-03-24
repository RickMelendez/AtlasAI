"""
OpenAI Adapter - Implementación de AIService usando OpenAI GPT models.

Este adaptador implementa la interfaz AIService usando la API de OpenAI
para generar respuestas conversacionales.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.application.interfaces.ai_service import AIService
from src.infrastructure.config.master_prompt import get_master_prompt

logger = logging.getLogger(__name__)


class OpenAIAdapter(AIService):
    """
    Adaptador para OpenAI GPT models.

    Implementa AIService usando la API de OpenAI para generar respuestas
    conversacionales, análisis de errores y sugerencias proactivas.

    Attributes:
        client: Cliente async de OpenAI
        model: Modelo a usar (gpt-4-turbo, gpt-3.5-turbo, etc.)
    """

    def __init__(self):
        """
        Inicializa el adaptador de OpenAI.

        Raises:
            ValueError: Si no se encuentra la API key de OpenAI
        """
        self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY in .env file."
            )

        # Cliente async de OpenAI
        self.client = AsyncOpenAI(api_key=self.api_key)

        # Modelo a usar (gpt-4-turbo-preview or gpt-3.5-turbo)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

        logger.info(f"✅ OpenAIAdapter initialized with model: {self.model}")

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        screen_context: Optional[str] = None,
        language: str = "es",
    ) -> str:
        """
        Genera una respuesta conversacional usando OpenAI GPT.

        Args:
            user_message: Mensaje del usuario
            conversation_history: Historial de conversación
            screen_context: Contexto de la pantalla (OCR)
            language: Idioma ("es" o "en")

        Returns:
            Respuesta generada por GPT
        """
        try:
            # Construir el system prompt con contexto
            system_prompt = get_master_prompt(language)

            # Si hay contexto de pantalla, agregarlo al system prompt
            if screen_context:
                if language == "es":
                    system_prompt += (
                        f"\n\n## Contexto Actual de Pantalla\n\n{screen_context}"
                    )
                else:
                    system_prompt += (
                        f"\n\n## Current Screen Context\n\n{screen_context}"
                    )

            # Construir mensajes de conversación
            messages = [{"role": "system", "content": system_prompt}]

            # Agregar historial de conversación si existe
            if conversation_history:
                messages.extend(conversation_history)

            # Agregar mensaje del usuario
            messages.append({"role": "user", "content": user_message})

            logger.info(f"[OpenAI] Generating response for: {user_message[:50]}...")

            # Llamar a OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=500, temperature=0.7
            )

            # Extraer respuesta
            reply = response.choices[0].message.content

            logger.info(f"[OpenAI] Response generated: {reply[:50]}...")

            return reply

        except Exception as e:
            logger.error(f"[OpenAI] Error generating response: {e}", exc_info=True)
            if language == "es":
                return "Lo siento, tuve un problema al procesar tu mensaje. ¿Puedes intentar de nuevo?"
            else:
                return (
                    "Sorry, I had a problem processing your message. Can you try again?"
                )

    async def analyze_screen_context(
        self, screen_text: str, app_context: Optional[str] = None, language: str = "es"
    ) -> Dict[str, Any]:
        """
        Analiza el texto de pantalla en busca de errores.

        Args:
            screen_text: Texto extraído de la pantalla
            app_context: Contexto de la aplicación
            language: Idioma

        Returns:
            Diccionario con análisis de errores
        """
        try:
            # Construir prompt de análisis
            if language == "es":
                system_prompt = """Eres un asistente experto en detectar y analizar errores en pantallas de desarrollo.

Analiza el siguiente texto y determina:
1. Si hay un error presente
2. Tipo de error
3. Descripción breve del error
4. Sugerencia de ayuda
5. Nivel de urgencia (low, medium, high)

Responde SOLO con un JSON válido en este formato:
{
  "has_error": true/false,
  "error_type": "tipo de error",
  "error_description": "descripción breve",
  "suggested_help": "sugerencia de solución",
  "urgency": "low/medium/high"
}"""
            else:
                system_prompt = """You are an expert assistant at detecting and analyzing errors on development screens.

Analyze the following text and determine:
1. If an error is present
2. Type of error
3. Brief error description
4. Help suggestion
5. Urgency level (low, medium, high)

Respond ONLY with valid JSON in this format:
{
  "has_error": true/false,
  "error_type": "error type",
  "error_description": "brief description",
  "suggested_help": "solution suggestion",
  "urgency": "low/medium/high"
}"""

            user_prompt = f"Texto de pantalla:\n{screen_text}"
            if app_context:
                user_prompt += f"\n\nContexto: {app_context}"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=300,
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            # Parsear JSON
            result = json.loads(response.choices[0].message.content)

            logger.info(
                f"[OpenAI] Error analysis complete: {result.get('has_error', False)}"
            )

            return result

        except Exception as e:
            logger.error(f"[OpenAI] Error in error analysis: {e}", exc_info=True)
            return {"has_error": False, "error": str(e)}

    async def offer_proactive_help(
        self,
        screen_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "es",
    ) -> Optional[str]:
        """
        Determina si se debe ofrecer ayuda proactiva.

        Args:
            screen_context: Contexto de la pantalla
            user_activity: Actividad reciente del usuario
            language: Idioma

        Returns:
            Sugerencia de ayuda o None si no es necesaria
        """
        try:
            if language == "es":
                system_prompt = """Eres Atlas, un asistente proactivo que observa la pantalla del usuario.

Determina si deberías ofrecer ayuda basándote en lo que ves. Solo ofrece ayuda si:
- Detectas que el usuario está bloqueado
- Hay una oportunidad clara de mejorar su flujo de trabajo
- Puedes proporcionar un consejo valioso

Si NO debes ofrecer ayuda, responde solo: "NONE"
Si debes ofrecer ayuda, responde con una sugerencia breve y útil (máximo 2 oraciones)."""
            else:
                system_prompt = """You are Atlas, a proactive assistant observing the user's screen.

Determine if you should offer help based on what you see. Only offer help if:
- You detect the user is stuck
- There's a clear opportunity to improve their workflow
- You can provide valuable advice

If you should NOT offer help, respond only: "NONE"
If you should offer help, respond with a brief, useful suggestion (maximum 2 sentences)."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Screen context:\n{screen_context}"},
                ],
                max_tokens=150,
                temperature=0.6,
            )

            suggestion = response.choices[0].message.content.strip()

            if suggestion == "NONE" or not suggestion:
                return None

            logger.info(f"[OpenAI] Proactive help offered: {suggestion[:50]}...")

            return suggestion

        except Exception as e:
            logger.error(
                f"[OpenAI] Error determining proactive help: {e}", exc_info=True
            )
            return None

"""
Use Case: Analizar Pantalla

Orquesta el flujo de:
1. Extraer texto de screenshot con OCR
2. Detectar contexto de aplicación
3. Detectar errores visibles
4. Analizar con Claude para sugerencias
"""

import logging
from typing import Optional

from ...application.interfaces.ai_service import AIService
from ...application.interfaces.screen_service import ScreenService
from ...application.use_cases.results import ScreenAnalysisResult

logger = logging.getLogger(__name__)


class AnalyzeScreenUseCase:
    """
    Use case para analizar capturas de pantalla.

    Extrae texto, detecta contexto y errores, y genera insights con AI.
    """

    def __init__(self, screen_service: ScreenService, ai_service: AIService):
        """
        Inicializa el use case.

        Args:
            screen_service: Servicio de visión/OCR
            ai_service: Servicio de AI (Claude)
        """
        self.screen_service = screen_service
        self.ai_service = ai_service

    async def execute(
        self, screenshot_data: bytes, language: str = "es"
    ) -> ScreenAnalysisResult:
        """
        Analiza una captura de pantalla.

        Args:
            screenshot_data: Imagen de la pantalla (PNG/JPG)
            language: Idioma para análisis

        Returns:
            Diccionario con análisis completo:
            {
                "screen_text": str,
                "app_context": dict,
                "errors_detected": dict,
                "ai_analysis": dict,
                "should_offer_help": bool,
                "help_suggestion": Optional[str]
            }
        """
        try:
            # 1. Extraer texto con OCR
            logger.info("🔍 Extracting text from screenshot...")
            screen_text = await self.screen_service.extract_text_from_image(
                screenshot_data, language="eng+spa" if language == "es" else "eng"
            )

            if not screen_text or len(screen_text.strip()) < 10:
                logger.info("Screen text too short, skipping analysis")
                return {
                    "screen_text": screen_text,
                    "app_context": {"app": "unknown"},
                    "errors_detected": {"has_error": False},
                    "ai_analysis": {},
                    "should_offer_help": False,
                    "help_suggestion": None,
                }

            # 2. Detectar contexto de aplicación
            logger.info("🖥️  Detecting app context...")
            app_context = await self.screen_service.detect_app_context(screen_text)

            # 3. Detectar errores básicos
            logger.info("🔎 Detecting errors...")
            errors_detected = await self.screen_service.detect_errors(
                screen_text, app_context
            )

            # 4. Si hay error, analizar con Claude
            ai_analysis = {}
            help_suggestion = None

            if errors_detected["has_error"]:
                logger.info("⚠️  Error detected, analyzing with Claude...")

                ai_analysis = await self.ai_service.analyze_screen_context(
                    screen_text=screen_text,
                    app_context=app_context.get("app"),
                    language=language,
                )

                # Si el error es urgente, ofrecer ayuda
                if ai_analysis.get("urgency") in ["medium", "high"]:
                    help_suggestion = ai_analysis.get("suggested_help")

            return {
                "screen_text": screen_text[:500],  # Limitar para logging
                "app_context": app_context,
                "errors_detected": errors_detected,
                "ai_analysis": ai_analysis,
                "should_offer_help": bool(help_suggestion),
                "help_suggestion": help_suggestion,
            }

        except Exception as e:
            logger.error(f"Error analyzing screen: {e}")
            return {
                "screen_text": "",
                "app_context": {"app": "unknown"},
                "errors_detected": {"has_error": False},
                "ai_analysis": {},
                "should_offer_help": False,
                "help_suggestion": None,
            }

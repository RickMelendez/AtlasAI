"""
Use Case: Procesar Comando de Voz

Orquesta el flujo completo de conversación por voz:
1. Transcribir audio con Whisper (STT)
2. Generar respuesta con Claude (AI)
3. Sintetizar respuesta con ElevenLabs (TTS)
4. Actualizar estado del asistente
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

from ...application.interfaces.ai_service import AIService
from ...application.interfaces.voice_service import TTSService, VoiceService
from ...application.use_cases.results import VoiceCommandResult
from ...domain.entities.assistant_state import AssistantState

logger = logging.getLogger(__name__)


class ProcessVoiceCommandUseCase:
    """
    Use case para procesar comandos de voz del usuario.

    Pipeline completo: Audio → Texto → Respuesta AI → Audio de respuesta

    Flujo de estados:
      ACTIVE → (wake word) → LISTENING → (speech ends) → THINKING → SPEAKING → ACTIVE
    """

    def __init__(
        self,
        voice_service: VoiceService,
        ai_service: AIService,
        assistant_state: AssistantState,
        tts_service: Optional[TTSService] = None,
        tool_executor=None,
    ):
        """
        Inicializa el use case.

        Args:
            voice_service: Servicio de transcripción (Whisper)
            ai_service: Servicio de AI (Claude)
            assistant_state: Estado actual del asistente
            tts_service: Servicio de TTS (ElevenLabs) — opcional
            tool_executor: ToolExecutor opcional — activa herramientas en Claude
        """
        self.voice_service = voice_service
        self.ai_service = ai_service
        self.assistant_state = assistant_state
        self.tts_service = tts_service
        self.tool_executor = tool_executor

        if tts_service:
            logger.info("✅ ProcessVoiceCommandUseCase initialized with TTS support")
        else:
            logger.info(
                "⚠️  ProcessVoiceCommandUseCase initialized WITHOUT TTS (text-only mode)"
            )

    async def execute(
        self,
        audio_data: bytes,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        screen_context: Optional[str] = None,
        transcription: Optional[str] = None,
    ) -> VoiceCommandResult:
        """
        Procesa un comando de voz y genera una respuesta hablada.

        Args:
            audio_data: Audio grabado del usuario (WAV/WebM/MP3)
            conversation_history: Historial de conversación para contexto
            screen_context: Texto extraído de pantalla para contexto adicional

        Returns:
            {
                "transcription": str,      # Texto del usuario (Whisper)
                "response": str,           # Respuesta de texto de Atlas (Claude)
                "audio_response_b64": str, # Audio base64 MP3 de Atlas (ElevenLabs)
                "has_audio": bool,         # True si se generó audio
                "success": bool,
                "error": Optional[str]
            }
        """
        try:
            # ── 1. THINKING: Transcribir audio con Whisper ────────────────────
            self.assistant_state.start_thinking()

            if transcription:
                logger.info(f"[VoiceUseCase] 📝 Using pre-transcribed text: '{transcription}'")
            else:
                logger.info("[VoiceUseCase] 🎤 Transcribing audio...")
                transcription = await self.voice_service.transcribe_audio(
                    audio_data,
                    language=self.assistant_state.language,
                )
                logger.info(f"[VoiceUseCase] 📝 Transcription: '{transcription}'")

            if not transcription or not transcription.strip():
                self.assistant_state.reset_to_active()
                return {
                    "transcription": "",
                    "response": "No pude escuchar nada. ¿Puedes repetir?",
                    "audio_response_b64": None,
                    "has_audio": False,
                    "success": False,
                    "error": "Empty transcription",
                }

            # ── 2. Generar respuesta con Claude ───────────────────────────────
            logger.info("[VoiceUseCase] 🧠 Generating AI response...")

            # Señalar a Claude que es un comando de voz — sesgar hacia acción
            voice_message = (
                "[VOICE COMMAND — user spoke this aloud. "
                "If actionable, USE your tools immediately. "
                "Respond briefly after acting.]\n\n"
                + transcription
            )

            response_text = await self.ai_service.generate_response(
                user_message=voice_message,
                conversation_history=conversation_history,
                screen_context=screen_context,
                language=self.assistant_state.language,
                tool_executor=self.tool_executor,
                session_id=self.assistant_state.session_id,
            )

            logger.info(f"[VoiceUseCase] 💬 Response: '{response_text[:80]}...'")

            # ── 3. SPEAKING: Sintetizar respuesta con ElevenLabs ──────────────
            self.assistant_state.start_speaking()

            audio_response_b64: Optional[str] = None
            has_audio = False

            if self.tts_service:
                try:
                    logger.info(
                        "[VoiceUseCase] 🔊 Synthesizing speech with ElevenLabs..."
                    )
                    audio_bytes = await self.tts_service.synthesize_speech(
                        response_text,
                        language=self.assistant_state.language,
                    )

                    if audio_bytes:
                        # Codificar en base64 para enviar por WebSocket (JSON-safe)
                        audio_response_b64 = base64.b64encode(audio_bytes).decode(
                            "utf-8"
                        )
                        has_audio = True
                        logger.info(
                            f"[VoiceUseCase] ✅ TTS done: {len(audio_bytes)} bytes MP3"
                        )

                except Exception as tts_error:
                    # TTS failure no debe romper el flujo — responder en texto igual
                    logger.error(
                        f"[VoiceUseCase] TTS error (continuing text-only): {tts_error}"
                    )

            return {
                "transcription": transcription,
                "response": response_text,
                "audio_response_b64": audio_response_b64,
                "has_audio": has_audio,
                "success": True,
                "error": None,
            }

        except Exception as e:
            logger.error(f"[VoiceUseCase] Error processing voice command: {e}")

            # Volver a ACTIVE en caso de error (desde cualquier estado del pipeline)
            self.assistant_state.reset_to_active()

            return {
                "transcription": "",
                "response": f"Disculpa, ocurrió un error: {str(e)}",
                "audio_response_b64": None,
                "has_audio": False,
                "success": False,
                "error": str(e),
            }

"""
Game Chat Route — Atlas AI

Endpoint HTTP para integración con Unreal Engine.
Recibe mensaje + estado del juego → genera respuesta de texto con Claude
→ sintetiza voz con Fish Audio TTS → devuelve texto + audio base64.

UE recibe el audio, lo decodifica y lo reproduce directamente en el juego
como si el personaje estuviera hablando — sin apps externas.
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.infrastructure.api.auth import require_api_key
from src.infrastructure.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", tags=["game"], dependencies=[Depends(require_api_key)])


# ── Modelos ───────────────────────────────────────────────────────────────────

class GameChatRequest(BaseModel):
    """
    Payload que envía Unreal Engine en cada petición.
    Todos los campos de game state son opcionales.
    """
    message:     str                  # Texto del jugador (voz transcrita o hardcoded)
    health:      Optional[int]  = None  # Vida actual
    max_health:  Optional[int]  = None  # Vida máxima
    enemy:       Optional[str]  = None  # Enemigo actual
    quest:       Optional[str]  = None  # Objetivo de misión activo
    location:    Optional[str]  = None  # Zona del mapa
    image_data:  Optional[str]  = None  # Screenshot del viewport en base64 (futuro)
    language:    Optional[str]  = "en"  # Idioma de la respuesta


class GameChatResponse(BaseModel):
    """
    Respuesta que recibe Unreal Engine.
    Incluye texto Y audio WAV en base64 para reproducir en el juego.
    WAV permite que UE5 lo reproduzca nativamente sin plugins externos.
    """
    response:    str            # Texto de Atlas
    audio_b64:   Optional[str]  # Audio WAV en base64 (None si Fish Audio no está configurado)
    audio_format: str = "wav"   # WAV — UE5 lo reproduce nativamente con USoundWaveProcedural
    ok:          bool = True    # False si hubo error


# ── Endpoint principal ────────────────────────────────────────────────────────

@router.post("/chat", response_model=GameChatResponse)
@limiter.limit("20/minute")
async def game_chat(request: Request, body: GameChatRequest):
    """
    Flujo completo:
      1. Construye game context con el estado del juego recibido
      2. Llama a ClaudeAdapter → genera respuesta de texto en game mode
      3. Pasa el texto a Fish Audio TTS → obtiene MP3 bytes
      4. Codifica MP3 como base64
      5. Devuelve { response, audio_b64, audio_format } a Unreal Engine

    UE decodifica audio_b64 → lo reproduce en un UAudioComponent
    pegado al personaje → suena como si el personaje estuviera hablando.
    """
    try:
        from src.adapters.ai.claude_adapter import get_claude_adapter
        from src.infrastructure.config.settings import get_settings

        settings = get_settings()
        claude   = get_claude_adapter()

        # ── 1. Construir contexto del juego ───────────────────────────────────
        game_context_lines = []

        if body.health is not None:
            max_h = body.max_health or 100
            pct   = int((body.health / max_h) * 100)
            status = "CRITICAL" if pct <= 25 else "LOW" if pct <= 50 else "OK"
            game_context_lines.append(
                f"Player health: {body.health}/{max_h} ({pct}%) — {status}"
            )

        if body.enemy:
            game_context_lines.append(f"Current enemy: {body.enemy}")

        if body.quest:
            game_context_lines.append(f"Active quest objective: {body.quest}")

        if body.location:
            game_context_lines.append(f"Current location: {body.location}")

        screen_context = (
            "=== LIVE GAME STATE ===\n" + "\n".join(game_context_lines)
            if game_context_lines else None
        )

        # ── 2. Generar respuesta de texto con Claude (game mode forzado) ──────
        response_text = await claude.generate_response(
            user_message=body.message,
            screen_context=screen_context,
            language=body.language or "en",
        )

        logger.info(
            f"[game/chat] '{body.message[:40]}' → '{response_text[:60]}'"
        )

        # ── 3. Sintetizar voz con Fish Audio TTS ──────────────────────────────
        audio_b64 = None

        if settings.fish_audio_api_key:
            try:
                from src.adapters.voice.fish_audio_adapter import FishAudioAdapter

                tts = FishAudioAdapter(
                    api_key=settings.fish_audio_api_key,
                    voice_id=settings.fish_audio_voice_id,  # None = usa DEFAULT_VOICE_ID
                )

                # synthesize_speech devuelve bytes de MP3
                audio_bytes = await tts.synthesize_speech(
                    text=response_text,
                    language=body.language or "en",
                )

                # Codificar como base64 para enviarlo en JSON
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                logger.info(
                    f"[game/chat] Fish Audio OK — {len(audio_bytes)} bytes "
                    f"→ {len(audio_b64)} chars base64"
                )

            except Exception as tts_err:
                # TTS falla → devolvemos texto igualmente, sin audio
                logger.warning(
                    f"[game/chat] Fish Audio TTS failed (non-critical): {tts_err}"
                )
        else:
            logger.info(
                "[game/chat] FISH_AUDIO_API_KEY not set — returning text only. "
                "Add it to .env to enable in-game voice."
            )

        # ── 4. Devolver texto + audio a Unreal Engine ─────────────────────────
        return GameChatResponse(
            response=response_text,
            audio_b64=audio_b64,
            audio_format="wav",
        )

    except Exception as e:
        logger.error(f"[game/chat] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def game_health():
    """Ping para que UE verifique que el backend está vivo antes de enviar."""
    from src.infrastructure.config.settings import get_settings
    settings = get_settings()
    return {
        "status": "ok",
        "mode": settings.atlas_mode,
        "tts": "fish_audio" if settings.fish_audio_api_key else "disabled",
    }

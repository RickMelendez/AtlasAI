"""
WebSocket routes para Atlas AI.

Este módulo define el endpoint WebSocket principal que mantiene
la conexión continua con el frontend.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.infrastructure.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal para Atlas AI.

    Este endpoint:
    1. Acepta conexiones WebSocket del frontend
    2. Genera un session_id único
    3. Mantiene la conexión abierta indefinidamente
    4. El WebSocketManager maneja los loops continuos

    La conexión se mantiene hasta que:
    - El cliente se desconecta
    - Ocurre un error
    - El servidor se apaga

    Args:
        websocket: Conexión WebSocket de FastAPI
    """
    # Generar session_id único
    session_id = str(uuid.uuid4())

    try:
        # Conectar via WebSocketManager (acepta y arranca loops)
        await ws_manager.connect(websocket, session_id)

        logger.info(f"WebSocket endpoint active for session: {session_id}")

        # Mantener conexión abierta indefinidamente
        # Los loops continuos ya están corriendo en background
        while True:
            try:
                # Simplemente esperar - el manager ya procesa mensajes en los loops
                await asyncio.sleep(1)

                # Verificar que la conexión sigue viva
                if session_id not in ws_manager.active_connections:
                    logger.warning(
                        f"Session {session_id} no longer in active connections"
                    )
                    break

            except asyncio.CancelledError:
                logger.info(f"WebSocket task cancelled for session: {session_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
        ws_manager.disconnect(session_id)

    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
        ws_manager.disconnect(session_id)

    finally:
        # Asegurar limpieza
        if session_id in ws_manager.active_connections:
            ws_manager.disconnect(session_id)
        logger.info(f"WebSocket endpoint closed for session: {session_id}")


@router.get("/ws/health")
async def websocket_health():
    """
    Health check endpoint para el sistema WebSocket.

    Returns:
        Información sobre el estado del WebSocketManager
    """
    return {
        "status": "healthy",
        "active_connections": len(ws_manager.active_connections),
        "active_sessions": list(ws_manager.active_connections.keys()),
    }

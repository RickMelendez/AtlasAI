"""
Event Bus para comunicación interna asíncrona.

Este módulo implementa un sistema de eventos que permite la comunicación
desacoplada entre componentes del sistema. Es fundamental para la arquitectura
event-driven de Atlas.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventBus:
    """
    Event Bus asíncrono para comunicación interna.

    Permite registrar listeners para eventos específicos y emitir eventos
    que serán procesados por todos los listeners registrados.

    Attributes:
        listeners: Diccionario que mapea nombres de eventos a listas de handlers
    """

    def __init__(self):
        """Inicializa el Event Bus con un diccionario vacío de listeners."""
        self.listeners: Dict[str, List[Callable]] = {}
        logger.info("Event Bus initialized")

    def on(self, event_name: str, handler: Callable) -> None:
        """
        Registra un listener para un evento específico.

        Args:
            event_name: Nombre del evento a escuchar
            handler: Función a ejecutar cuando se emite el evento
                    Puede ser síncrona o asíncrona

        Example:
            >>> event_bus.on('wake_word_detected', handle_wake_word)
        """
        if event_name not in self.listeners:
            self.listeners[event_name] = []

        self.listeners[event_name].append(handler)
        logger.debug(f"Registered handler for event: {event_name}")

    async def emit(self, event_name: str, data: Any = None) -> None:
        """
        Emite un evento a todos los listeners registrados.

        Ejecuta todos los handlers asociados al evento, manejando tanto
        funciones síncronas como asíncronas. Si un handler falla, se
        registra el error pero no se interrumpe la ejecución de otros handlers.

        Args:
            event_name: Nombre del evento a emitir
            data: Datos opcionales a pasar a los handlers

        Example:
            >>> await event_bus.emit('wake_word_detected', {'keyword': 'atlas'})
        """
        if event_name not in self.listeners:
            logger.debug(f"No listeners registered for event: {event_name}")
            return

        logger.debug(
            f"Emitting event: {event_name} to {len(self.listeners[event_name])} listeners"
        )

        for handler in self.listeners[event_name]:
            try:
                # Verificar si el handler es una coroutine (async function)
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    # Ejecutar función síncrona
                    handler(data)
            except Exception as e:
                logger.error(
                    f"Error in handler for event '{event_name}': {e}", exc_info=True
                )


# Singleton instance - instancia global única del Event Bus
event_bus = EventBus()

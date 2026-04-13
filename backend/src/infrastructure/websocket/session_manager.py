"""
WebSocket Session Manager - Handles connection lifecycle and session state.

Responsible for:
- WebSocket connection lifecycle (connect, disconnect, cleanup)
- Session state management (AssistantState per session_id)
- Screen context storage per session
- Dependency injection for voice pipeline and tools
"""

import logging
from typing import TYPE_CHECKING, Callable, Dict, Optional

from fastapi import WebSocket

from src.domain.entities.assistant_state import AssistantState, AssistantMode

if TYPE_CHECKING:
    from src.application.use_cases.process_voice_command import ProcessVoiceCommandUseCase

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages WebSocket connections and session state.

    Responsibilities:
    - Accept/disconnect WebSocket connections
    - Maintain AssistantState per session
    - Store screen context per session
    - Provide dependency injection points
    """

    def __init__(self):
        """Initialize the session manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.assistant_states: Dict[str, AssistantState] = {}
        self.running_loops: Dict[str, bool] = {}
        self.screen_contexts: Dict[str, Optional[str]] = {}

        # Dependency injection
        self._voice_use_case_factory: Optional[Callable] = None
        self._tool_executor = None
        self._whisper_service = None

        logger.info("SessionManager initialized")

    def set_voice_use_case_factory(self, factory: Callable) -> None:
        """Set the factory for creating voice use cases."""
        self._voice_use_case_factory = factory
        logger.info("✅ Voice use case factory registered")

    def set_whisper_service(self, whisper_service) -> None:
        """Set the Whisper service for STT."""
        self._whisper_service = whisper_service
        logger.info("✅ Whisper service registered")

    def set_tool_executor(self, tool_executor) -> None:
        """Set the tool executor for browser/terminal/file operations."""
        self._tool_executor = tool_executor
        logger.info("✅ ToolExecutor registered")

    def update_screen_context(self, session_id: str, description: Optional[str]) -> None:
        """Store the latest screen description for a session."""
        if session_id in self.screen_contexts or session_id in self.active_connections:
            self.screen_contexts[session_id] = description

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accept a WebSocket connection and initialize session state.

        Args:
            websocket: FastAPI WebSocket connection
            session_id: Unique session identifier
        """
        await websocket.accept()

        self.active_connections[session_id] = websocket
        self.assistant_states[session_id] = AssistantState(
            session_id=session_id,
            mode=AssistantMode.INACTIVE,
            language="en",
        )
        self.running_loops[session_id] = True
        self.screen_contexts[session_id] = None

        logger.info(f"[{session_id}] ✅ WebSocket connected")

    def disconnect(self, session_id: str) -> None:
        """
        Close connection and cleanup session state.

        Args:
            session_id: Unique session identifier
        """
        self.running_loops[session_id] = False
        self.active_connections.pop(session_id, None)
        self.assistant_states.pop(session_id, None)
        self.running_loops.pop(session_id, None)
        self.screen_contexts.pop(session_id, None)

        # Playwright cleanup
        if self._tool_executor and hasattr(self._tool_executor, '_browser'):
            try:
                self._tool_executor._browser.close_session(session_id)
            except Exception as e:
                logger.warning(f"[{session_id}] Playwright cleanup error: {e}")

        logger.info(f"[{session_id}] WebSocket disconnected")

    async def send_event(self, session_id: str, event: dict) -> None:
        """
        Send a JSON event to the WebSocket client.

        Args:
            session_id: Unique session identifier
            event: Event dictionary to send
        """
        ws = self.active_connections.get(session_id)
        if not ws:
            logger.warning(f"[{session_id}] Cannot send — not connected")
            return
        try:
            await ws.send_json(event)
            logger.debug(f"[{session_id}] → {event.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"[{session_id}] Send error: {e}", exc_info=True)
            self.disconnect(session_id)

    async def broadcast_event(self, event: dict) -> None:
        """
        Send an event to all connected sessions.

        Args:
            event: Event dictionary to broadcast
        """
        for session_id in list(self.active_connections.keys()):
            await self.send_event(session_id, event)

    def get_state(self, session_id: str) -> Optional[AssistantState]:
        """
        Get the assistant state for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            AssistantState or None if session not found
        """
        return self.assistant_states.get(session_id)

    def get_websocket(self, session_id: str) -> Optional[WebSocket]:
        """
        Get the WebSocket connection for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            WebSocket or None if session not found
        """
        return self.active_connections.get(session_id)

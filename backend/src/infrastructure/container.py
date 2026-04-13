"""
Application Container - Manages service initialization and dependency injection.

This module defines the AppContainer class which owns all service initialization
in a single, testable location. This replaces the monolithic lifespan() function
in main.py.
"""

import logging
from typing import Optional

from src.adapters.ai.claude_adapter import ClaudeAdapter
from src.adapters.vision.claude_vision_adapter import ClaudeVisionAdapter
from src.adapters.voice.edge_tts_adapter import EdgeTTSAdapter
from src.adapters.voice.elevenlabs_adapter import ElevenLabsAdapter
from src.adapters.voice.faster_whisper_adapter import FasterWhisperAdapter
from src.adapters.voice.fish_audio_adapter import FishAudioAdapter
from src.adapters.web.playwright_adapter import PlaywrightAdapter
from src.adapters.notion.notion_adapter import NotionAdapter
from src.adapters.tools.tool_executor import ToolExecutor
from src.application.use_cases.process_chat_message import ProcessChatMessageUseCase
from src.application.use_cases.process_voice_command import ProcessVoiceCommandUseCase
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database import init_db, AsyncSessionFactory
from src.infrastructure.database.repositories.conversation_repository import (
    SQLiteConversationRepository,
)

logger = logging.getLogger(__name__)


class AppContainer:
    """
    Application Container - owns all service initialization and configuration.

    Responsible for:
    - Initializing Claude, Whisper, TTS, and Vision adapters
    - Setting up Playwright for browser automation
    - Creating tool executor and use cases
    - Managing service lifecycle (startup, shutdown)
    - Providing proper dependency injection throughout the app
    """

    def __init__(self):
        """Initialize all service references to None."""
        self.claude: Optional[ClaudeAdapter] = None
        self.whisper: Optional[FasterWhisperAdapter] = None
        self.tts: Optional[object] = None  # Union of TTS adapters
        self.playwright: Optional[PlaywrightAdapter] = None
        self.screen_service: Optional[ClaudeVisionAdapter] = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.chat_use_case: Optional[ProcessChatMessageUseCase] = None
        self.notion: Optional[NotionAdapter] = None

    async def initialize(self) -> None:
        """
        Initialize all services in proper dependency order.

        This replaces the monolithic lifespan() function in main.py.
        All services are initialized here to ensure consistency and testability.
        """
        logger.info("🚀 AppContainer: Initializing services...")

        # Database initialization
        await init_db()
        logger.info("✅ Database initialized")

        # Claude AI service (required)
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in environment or .env file. "
                "Please set it before starting the app."
            )
        self.claude = ClaudeAdapter(api_key=settings.anthropic_api_key)
        logger.info("✅ Claude adapter initialized")

        # Speech-to-Text: FasterWhisper (local, no API key required)
        try:
            self.whisper = FasterWhisperAdapter(model_size="small")
            logger.info("✅ FasterWhisper initialized (STT ready)")
        except Exception as e:
            logger.warning(f"⚠️  FasterWhisper not available: {e}")
            self.whisper = None

        # Text-to-Speech: ElevenLabs → Fish Audio → Edge-TTS (free fallback)
        if settings.elevenlabs_api_key:
            try:
                self.tts = ElevenLabsAdapter(
                    api_key=settings.elevenlabs_api_key,
                    voice_id=settings.elevenlabs_voice_id or None,
                )
                logger.info("[TTS] Using ElevenLabs")
            except Exception as e:
                logger.warning(f"⚠️  ElevenLabs not available: {e}")
                self.tts = None

        if self.tts is None and settings.fish_audio_api_key:
            try:
                self.tts = FishAudioAdapter(
                    api_key=settings.fish_audio_api_key,
                    voice_id=settings.fish_audio_voice_id or None,
                )
                logger.info("[TTS] Using Fish Audio")
            except Exception as e:
                logger.warning(f"⚠️  Fish Audio not available: {e}")
                self.tts = None

        if self.tts is None:
            try:
                self.tts = EdgeTTSAdapter()
                logger.info("[TTS] Using Edge-TTS (free fallback)")
            except Exception as e:
                logger.warning(f"⚠️  Edge-TTS not available: {e}")
                self.tts = None

        # Screen vision service
        self.screen_service = ClaudeVisionAdapter()
        logger.info("✅ Claude Vision adapter initialized")

        # Web automation
        self.playwright = PlaywrightAdapter()
        await self.playwright.start()
        logger.info("✅ Playwright initialized")

        # Notion integration
        self.notion = NotionAdapter()
        logger.info("✅ Notion adapter initialized")

        # Tool executor (depends on playwright, notion)
        self.tool_executor = ToolExecutor(self.playwright, self.notion)
        logger.info("✅ ToolExecutor initialized")

        # Use cases (depends on claude)
        self.chat_use_case = ProcessChatMessageUseCase(self.claude)
        self.chat_use_case.tool_executor = self.tool_executor
        logger.info("✅ Chat use case initialized")

        logger.info("🎯 AppContainer: All services initialized successfully")

    async def shutdown(self) -> None:
        """
        Clean up all services on shutdown.

        Gracefully closes connections and releases resources.
        """
        logger.info("🛑 AppContainer: Shutting down services...")

        try:
            if self.playwright:
                await self.playwright.stop()
                logger.info("✅ Playwright stopped")
        except Exception as e:
            logger.error(f"Error stopping Playwright: {e}")

        logger.info("✅ AppContainer: Shutdown complete")

    def make_voice_use_case(self, assistant_state) -> ProcessVoiceCommandUseCase:
        """
        Factory method to create a voice use case for a session.

        Args:
            assistant_state: The AssistantState for this session

        Returns:
            ProcessVoiceCommandUseCase configured with all services
        """
        if not self.whisper:
            raise RuntimeError("Whisper service not available")
        if not self.claude:
            raise RuntimeError("Claude service not available")

        return ProcessVoiceCommandUseCase(
            voice_service=self.whisper,
            ai_service=self.claude,
            assistant_state=assistant_state,
            tts_service=self.tts,
            tool_executor=self.tool_executor,
        )

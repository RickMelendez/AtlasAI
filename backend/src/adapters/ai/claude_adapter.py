"""
Claude AI Adapter - Implementación de AIService usando Anthropic Claude.

Este adapter implementa la interface AIService usando la API de Anthropic
para generar respuestas conversacionales y analizar contexto de pantalla.
"""

import asyncio
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, cast

from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import MessageParam

from ...application.interfaces.ai_service import AIService
from ...infrastructure.config.master_prompt import (get_error_analysis_prompt,
                                                    get_master_prompt,
                                                    get_proactive_help_prompt)
from ...infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

# ── Definición de herramientas disponibles para Claude ────────────────────────
ATLAS_TOOLS = [
    {
        "name": "browse_web",
        "description": "Navigate to a URL in a headless browser and get a screenshot + page title. Use for any 'go to', 'open', 'browse to', or 'show me' web requests.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL (https://...) or domain (github.com)"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "click_element",
        "description": "Click an element on the current browser page by CSS selector or visible text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector, XPath, or 'text=\"Button Label\"'"}
            },
            "required": ["selector"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into a form field on the current browser page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the input field"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "get_page_content",
        "description": "Get the visible text content of the current browser page.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_terminal_command",
        "description": "Run a shell command and get stdout/stderr output. Use for npm, git, python, file operations, etc. Windows PowerShell compatible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file on the user's computer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file on the user's computer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current dir)"}
            },
            "required": [],
        },
    },
    {
        "name": "search_notion",
        "description": "Search the user's Notion workspace for pages matching a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Maximum results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_notion_page",
        "description": "Read the content of a Notion page by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Notion page ID"}
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "create_notion_note",
        "description": "Create a new page/note in the user's Notion workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title"},
                "content": {"type": "string", "description": "Page content"},
                "parent_page_id": {"type": "string", "description": "Optional parent page ID"},
            },
            "required": ["title", "content"],
        },
    },
]


class ClaudeAdapter(AIService):
    """
    Adapter para Anthropic Claude AI.

    Implementa AIService usando Claude 3.5 Sonnet para:
    - Conversaciones naturales con contexto de pantalla
    - Análisis de errores en código
    - Sugerencias proactivas de ayuda
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el adapter de Claude.

        Args:
            api_key: API key de Anthropic (opcional, se obtiene de settings)
        """
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key

        # Allow a mock/no-op client for offline CI/testing by setting
        # ANTHROPIC_MOCK=1 or passing api_key='mock'.
        use_mock = os.environ.get("ANTHROPIC_MOCK") == "1" or (self.api_key == "mock")

        if use_mock:
            # Lazy simple mock that implements the subset of the AsyncAnthropic
            # interface used by this adapter (messages.create and messages.stream).
            class _MockStream:
                def __init__(self, chunks):
                    self._chunks = chunks

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                @property
                async def text_stream(self):
                    # text_stream used with `async for text in stream.text_stream`
                    for ch in self._chunks:
                        yield ch

            class _MockMessages:
                async def create(
                    self, *, model, max_tokens, temperature, system, messages
                ):
                    # Determine a reasonable mocked response based on `system`
                    sys_low = (system or "").lower()
                    # Try to echo last user content when possible
                    last = None
                    try:
                        last = messages[-1].get("content")
                    except Exception:
                        last = None

                    if (
                        "analiz" in sys_low
                        or "analysis" in sys_low
                        or "error_analysis" in sys_low
                    ):
                        body = json.dumps(
                            {
                                "has_error": True,
                                "error_description": "Mocked error detected",
                                "suggested_help": "Reinicia la variable o revisa la referencia nula.",
                                "urgency": "low",
                                "error_type": "TypeError",
                            }
                        )
                        return SimpleNamespace(content=[{"text": body}])

                    if "proactiv" in sys_low or "proactive" in sys_low:
                        # Offer a short suggestion
                        return SimpleNamespace(
                            content=[
                                {
                                    "text": "Puedes intentar inicializar la variable antes de usarla."
                                }
                            ]
                        )

                    # Default conversational reply
                    reply = f"[MOCK] Reply to: {last or 'hello'}"
                    return SimpleNamespace(content=[{"text": reply}])

                def stream(self, *, model, max_tokens, temperature, system, messages):
                    # Return an async context manager with a simple text_stream generator
                    return _MockStream(["[MOCK] ", "streamed ", "response"])

            class MockAsyncAnthropic:
                def __init__(self, api_key=None):
                    self.messages = _MockMessages()

            self.client = MockAsyncAnthropic(api_key=self.api_key)
        else:
            if not self.api_key:
                raise ValueError(
                    "Anthropic API key not found. Set ANTHROPIC_API_KEY in .env file."
                )

            # Cliente async de Anthropic
            self.client = AsyncAnthropic(api_key=self.api_key)

        # Modelo a usar (Claude Sonnet 4.6 — latest)
        self.model = "claude-sonnet-4-6"

        # Configuración por defecto
        self.default_max_tokens = 1024
        self.default_temperature = 0.7

        logger.info(f"✅ ClaudeAdapter initialized with model: {self.model}")

    async def _call_claude_with_retry(self, **kwargs) -> Any:
        """Call Claude API with exponential backoff on 529 overloaded errors."""
        for attempt in range(3):
            try:
                return await self.client.messages.create(**kwargs)
            except Exception as e:
                if "overloaded" in str(e).lower() and attempt < 2:
                    wait = 2 ** attempt  # 1s, then 2s
                    logger.warning(
                        f"Claude overloaded, retrying in {wait}s "
                        f"(attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

    def _extract_text_from_response(self, response) -> str:
        """
        Extrae el primer bloque de texto de la respuesta de Anthropic.

        Itera todos los bloques de contenido en lugar de asumir que content[0]
        es siempre un TextBlock — cuando hay tool_use en la respuesta los
        primeros bloques pueden ser ToolUseBlock sin atributo .text.
        """
        try:
            for block in response.content:
                # Anthropic SDK TextBlock — atributo .text es str
                if hasattr(block, "text") and isinstance(block.text, str):
                    return block.text
                # Formato dict (algunas versiones del SDK)
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    return block["text"]
        except Exception:
            pass
        return ""

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        screen_context: Optional[str] = None,
        language: str = "es",
        tool_executor=None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Genera una respuesta conversacional usando Claude.

        Si se proporciona tool_executor, Claude puede llamar herramientas
        (browser, terminal, archivos, Notion) en un loop hasta dar respuesta final.

        Args:
            user_message: Mensaje del usuario
            conversation_history: Historial de conversación
            screen_context: Descripción de la pantalla actual
            language: Idioma ("es" o "en")
            tool_executor: ToolExecutor opcional — activa el modo tool use
            session_id: ID de sesión para herramientas de browser

        Returns:
            Respuesta generada por Claude
        """
        try:
            # Construir el system prompt con contexto
            system_prompt = get_master_prompt(language)

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
            messages: List[MessageParam] = []

            if conversation_history:
                for msg in conversation_history[-10:]:
                    messages.append(
                        cast(
                            MessageParam,
                            {"role": msg["role"], "content": msg["content"]},
                        )
                    )

            messages.append({"role": "user", "content": user_message})

            # Inyectar session_id en el executor antes de entrar al loop
            if tool_executor and session_id:
                tool_executor.set_session(session_id)

            tools = ATLAS_TOOLS if tool_executor else []
            # Inicializar lista de screenshots generados en esta llamada
            self._last_tool_screenshots: List[str] = []

            # ── Tool use loop ────────────────────────────────────────────────
            # Claude puede pedir herramientas múltiples veces antes de la respuesta final
            max_iterations = 10  # evitar loops infinitos
            for _ in range(max_iterations):
                kwargs: Dict[str, Any] = dict(
                    model=self.model,
                    max_tokens=2048,
                    temperature=self.default_temperature,
                    system=system_prompt,
                    messages=messages,
                )
                if tools:
                    kwargs["tools"] = tools

                response = await self._call_claude_with_retry(**kwargs)

                if response.stop_reason == "end_turn" or not tool_executor:
                    assistant_message = self._extract_text_from_response(response)
                    logger.info(f"Response for: {user_message[:50]}...")
                    return assistant_message

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            result_str = await tool_executor.execute(
                                block.name, block.input
                            )
                            # Capturar screenshots para enviar al frontend
                            try:
                                result_data = json.loads(result_str)
                                if isinstance(result_data, dict) and "screenshot_b64" in result_data:
                                    b64 = result_data["screenshot_b64"]
                                    if b64:
                                        self._last_tool_screenshots.append(b64)
                            except (json.JSONDecodeError, TypeError):
                                pass

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            })

                    # Agregar turno del asistente con las tool calls
                    messages.append({
                        "role": "assistant",
                        "content": [
                            {"type": b.type, **{k: v for k, v in vars(b).items() if k != "type"}}
                            if hasattr(b, "__dict__") else b
                            for b in response.content
                        ],
                    })
                    # Agregar resultados de herramientas
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # stop_reason desconocido — extraer texto si existe
                return self._extract_text_from_response(response)

            # Si se agotaron las iteraciones sin end_turn, devolver mensaje de error
            logger.warning("Tool use loop exhausted max iterations without end_turn")
            return "Sorry, I had trouble processing that. Please try again."

        except Exception as e:
            logger.error(f"Error generating response with Claude: {e}")
            raise

    async def analyze_screen_context(
        self, screen_text: str, app_context: Optional[str] = None, language: str = "es"
    ) -> Dict[str, Any]:
        """
        Analiza el contexto de pantalla para detectar errores o situaciones.

        Args:
            screen_text: Texto extraído de la pantalla con OCR
            app_context: Aplicación activa (VS Code, browser, etc.)
            language: Idioma preferido

        Returns:
            Diccionario con análisis de errores y sugerencias
        """
        try:
            # Construir el prompt de análisis
            analysis_prompt = get_error_analysis_prompt(language)

            # Agregar contexto de la app si existe
            context_info = (
                f"Aplicación activa: {app_context}\n\n" if app_context else ""
            )
            context_info += f"Texto en pantalla:\n{screen_text}"

            # Llamar a Claude para análisis
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                temperature=0.3,  # Más bajo para análisis objetivo
                system=analysis_prompt,
                messages=[{"role": "user", "content": context_info}],
            )

            # Intentar parsear como JSON
            try:
                text = self._extract_text_from_response(response)
                analysis = json.loads(text)
            except json.JSONDecodeError:
                # Si no es JSON válido, crear estructura por defecto
                analysis = {
                    "has_error": False,
                    "error_description": "",
                    "suggested_help": "",
                    "urgency": "low",
                }

            logger.info(
                f"Screen analysis completed: {analysis.get('has_error', False)}"
            )
            return analysis

        except Exception as e:
            logger.error(f"Error analyzing screen context: {e}")
            return {
                "has_error": False,
                "error_description": "",
                "suggested_help": "",
                "urgency": "low",
            }

    async def offer_proactive_help(
        self,
        screen_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "es",
    ) -> Optional[str]:
        """
        Determina si debe ofrecer ayuda proactiva.

        Args:
            screen_context: Contexto actual de la pantalla
            conversation_history: Historial de conversación
            language: Idioma preferido

        Returns:
            Sugerencia de ayuda, o None si no es necesario
        """
        try:
            # Construir el prompt de ayuda proactiva
            proactive_prompt = get_proactive_help_prompt(language)

            # Agregar contexto de conversación reciente si existe
            context_info = f"Contexto de pantalla:\n{screen_context}\n\n"

            if conversation_history and len(conversation_history) > 0:
                # Últimos 3 mensajes
                recent_messages = conversation_history[-3:]
                context_info += "Conversación reciente:\n"
                for msg in recent_messages:
                    role = "Usuario" if msg["role"] == "user" else "Atlas"
                    context_info += f"{role}: {msg['content']}\n"

            # Llamar a Claude
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.5,
                system=proactive_prompt,
                messages=[{"role": "user", "content": context_info}],
            )

            suggestion = self._extract_text_from_response(response).strip()

            # Si Claude responde "null" o está vacío, no ofrecer ayuda
            if suggestion.lower() == "null" or not suggestion:
                logger.info("No proactive help needed")
                return None

            logger.info(f"Offering proactive help: {suggestion[:50]}...")
            return suggestion

        except Exception as e:
            logger.error(f"Error determining proactive help: {e}")
            return None

    async def generate_streaming_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        screen_context: Optional[str] = None,
        language: str = "es",
    ):
        """
        Genera una respuesta en streaming (para futuras mejoras).

        Args:
            user_message: Mensaje del usuario
            conversation_history: Historial
            screen_context: Contexto de pantalla
            language: Idioma

        Yields:
            Chunks de texto de la respuesta
        """
        try:
            # Construir system prompt
            system_prompt = get_master_prompt(language)
            if screen_context:
                system_prompt += f"\n\n## Screen Context\n\n{screen_context}"

            # Construir mensajes
            messages: List[MessageParam] = []
            if conversation_history:
                for msg in conversation_history[-10:]:
                    messages.append(
                        cast(
                            MessageParam,
                            {"role": msg["role"], "content": msg["content"]},
                        )
                    )
            messages.append({"role": "user", "content": user_message})

            # Stream de Claude
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=self.default_max_tokens,
                temperature=self.default_temperature,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.error(f"Error in streaming response: {e}")
            yield f"[Error: {str(e)}]"


# Singleton instance
_claude_adapter_instance: Optional[ClaudeAdapter] = None


def get_claude_adapter() -> ClaudeAdapter:
    """
    Obtiene la instancia singleton del ClaudeAdapter.

    Returns:
        Instancia de ClaudeAdapter
    """
    global _claude_adapter_instance
    if _claude_adapter_instance is None:
        _claude_adapter_instance = ClaudeAdapter()
    return _claude_adapter_instance

"""
Tool Executor — despacha las llamadas de herramientas de Claude.

Cuando Claude decide usar una tool (browse_web, run_terminal_command, etc.),
este executor recibe el nombre y los parámetros, ejecuta la acción real
y retorna el resultado como string JSON.

Todas las operaciones están en try/except — nunca lanza, siempre retorna
un JSON con "error" si algo falla.
"""

import asyncio
import json
import logging
import re
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Patrones de comandos peligrosos que nunca deben ejecutarse.
#
# Esto es defensa en profundidad, NO una sandbox real — un denylist sobre
# shell=True siempre es evadible (ver CODE-REVIEW.md Security Critical #3).
# El fix completo requeriría pasar a ejecución argv (sin shell) con allowlist
# de binarios, lo cual limitaría comandos compuestos/con pipes que el prompt
# de Atlas ofrece como capacidad legítima ("npm test | tail", etc.) — esa es
# una decisión de producto, no algo para decidir en silencio en un refactor.
_DANGEROUS_PATTERNS = [
    # Borrado destructivo — recursivo/forzado, cualquier target (no solo "/")
    r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r",
    r"format\s+[a-z]:",
    r"del\s+/[sq]",
    r"rd\s+/s|rmdir\s+/s",
    r"remove-item.*-recurse.*-force|remove-item.*-force.*-recurse",
    r"mkfs",
    r"dd\s+if=",
    r"dd\s+of=",
    r"diskpart",
    r">\s*/dev/(sd|nvme)",
    r"shutdown",
    r"reboot",
    # Fetch remoto → ejecutar directo (patrón clásico de infección)
    r"(curl|wget|iwr|invoke-webrequest).*\|\s*(sh|bash|zsh|powershell|iex|invoke-expression)",
    r"invoke-expression|iex\s*\(",
    # Escalación de privilegios
    r"\bsudo\b|\brunas\b|start-process.*-verb\s+runas",
    # Registro de Windows
    r"reg\s+delete|remove-item.*hklm|remove-item.*hkcu",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\};:",
]
_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


class ToolExecutor:
    """
    Despacha llamadas de herramientas de Claude al adapter correcto.

    Herramientas disponibles:
    - browse_web(url)                         → PlaywrightAdapter
    - click_element(selector)                 → PlaywrightAdapter
    - type_text(selector, text)               → PlaywrightAdapter
    - get_page_content()                      → PlaywrightAdapter
    - run_terminal_command(command)           → subprocess
    - read_file(path)                         → pathlib
    - write_file(path, content)               → pathlib
    - list_directory(path)                    → pathlib
    - search_notion(query)                    → NotionAdapter
    - read_notion_page(page_id)               → NotionAdapter
    - create_notion_note(title, content)      → NotionAdapter
    """

    def __init__(self, playwright_adapter=None, notion_adapter=None):
        self._browser = playwright_adapter
        self._notion = notion_adapter
        # session_id se inyecta antes de cada llamada desde el ClaudeAdapter
        self._session_id: Optional[str] = None

    def set_session(self, session_id: str) -> None:
        """Establece el session_id activo para herramientas de browser."""
        self._session_id = session_id

    async def execute(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Ejecuta una tool y retorna el resultado como string JSON.

        Args:
            tool_name: Nombre de la herramienta (tal como la define Claude)
            tool_input: Parámetros de la herramienta

        Returns:
            String JSON con el resultado o {"error": "..."}
        """
        logger.info(f"🔧 Tool call: {tool_name}({list(tool_input.keys())})")
        try:
            if tool_name == "open_in_default_browser":
                return self._open_in_default_browser(tool_input)
            elif tool_name == "browse_web":
                return await self._browse_web(tool_input)
            elif tool_name == "click_element":
                return await self._click_element(tool_input)
            elif tool_name == "type_text":
                return await self._type_text(tool_input)
            elif tool_name == "get_page_content":
                return await self._get_page_content()
            elif tool_name == "run_terminal_command":
                return await self._run_terminal(tool_input)
            elif tool_name == "read_file":
                return self._read_file(tool_input)
            elif tool_name == "write_file":
                return self._write_file(tool_input)
            elif tool_name == "list_directory":
                return self._list_directory(tool_input)
            elif tool_name == "search_notion":
                return await self._search_notion(tool_input)
            elif tool_name == "read_notion_page":
                return await self._read_notion_page(tool_input)
            elif tool_name == "create_notion_note":
                return await self._create_notion_note(tool_input)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.error(f"Tool executor error in {tool_name}: {e}", exc_info=True)
            return json.dumps({"error": str(e)})

    # ── Browser tools ──────────────────────────────────────────────────────────

    def _open_in_default_browser(self, inp: dict) -> str:
        """Open a URL in the user's default system browser (Chrome/Edge with their profile)."""
        url = inp.get("url", "")
        if not url:
            return json.dumps({"error": "url parameter required"})
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            logger.info(f"🌐 Opened in default browser: {url}")
            return json.dumps({"success": True, "url": url})
        except Exception as e:
            logger.error(f"Failed to open default browser: {e}")
            return json.dumps({"error": str(e)})

    async def _browse_web(self, inp: dict) -> str:
        url = inp.get("url", "")
        if not url:
            return json.dumps({"error": "url parameter required"})
        if not self._browser:
            return json.dumps({"error": "Browser not available"})
        sid = self._session_id or "default"
        result = await self._browser.navigate(sid, url)
        return json.dumps(result)

    async def _click_element(self, inp: dict) -> str:
        selector = inp.get("selector", "")
        if not selector:
            return json.dumps({"error": "selector parameter required"})
        if not self._browser:
            return json.dumps({"error": "Browser not available"})
        sid = self._session_id or "default"
        result = await self._browser.click(sid, selector)
        return json.dumps(result)

    async def _type_text(self, inp: dict) -> str:
        selector = inp.get("selector", "")
        text = inp.get("text", "")
        if not selector:
            return json.dumps({"error": "selector parameter required"})
        if not self._browser:
            return json.dumps({"error": "Browser not available"})
        sid = self._session_id or "default"
        result = await self._browser.type_text(sid, selector, text)
        return json.dumps(result)

    async def _get_page_content(self) -> str:
        if not self._browser:
            return json.dumps({"error": "Browser not available"})
        sid = self._session_id or "default"
        result = await self._browser.get_content(sid)
        return json.dumps(result)

    # ── Terminal ───────────────────────────────────────────────────────────────

    async def _run_terminal(self, inp: dict) -> str:
        command = inp.get("command", "").strip()
        if not command:
            return json.dumps({"error": "command parameter required"})

        # Bloquear comandos peligrosos
        if _DANGEROUS_RE.search(command):
            logger.warning(f"🚫 Blocked dangerous command: {command}")
            return json.dumps({"error": "Command blocked for safety reasons"})

        logger.info(f"💻 Running command: {command}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                proc.kill()
                return json.dumps({"error": "Command timed out after 30s"})

            return json.dumps({
                "stdout": stdout.decode("utf-8", errors="replace")[:4000],
                "stderr": stderr.decode("utf-8", errors="replace")[:1000],
                "returncode": proc.returncode,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── File system ────────────────────────────────────────────────────────────

    def _read_file(self, inp: dict) -> str:
        path_str = inp.get("path", "")
        if not path_str:
            return json.dumps({"error": "path parameter required"})
        try:
            p = Path(path_str).expanduser()
            if not p.exists():
                return json.dumps({"error": f"File not found: {path_str}"})
            if not p.is_file():
                return json.dumps({"error": f"Not a file: {path_str}"})
            content = p.read_text(encoding="utf-8", errors="replace")
            # Truncar si el archivo es muy grande
            if len(content) > 8000:
                content = content[:8000] + "\n... [truncated — file too large]"
            return content
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _write_file(self, inp: dict) -> str:
        path_str = inp.get("path", "")
        content = inp.get("content", "")
        if not path_str:
            return json.dumps({"error": "path parameter required"})
        try:
            p = Path(path_str).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} bytes to {p}"
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _list_directory(self, inp: dict) -> str:
        if "path" not in inp:
            return json.dumps({"error": "path parameter required"})
        path_str = inp.get("path", ".")
        try:
            p = Path(path_str).expanduser()
            if not p.exists():
                return json.dumps({"error": f"Path not found: {path_str}"})
            if not p.is_dir():
                return json.dumps({"error": f"Not a directory: {path_str}"})
            entries = []
            for item in sorted(p.iterdir()):
                try:
                    size = item.stat().st_size if item.is_file() else 0
                    entries.append({
                        "name": item.name,
                        "type": "file" if item.is_file() else "dir",
                        "size": size,
                    })
                except Exception:
                    entries.append({"name": item.name, "type": "unknown", "size": 0})
            return json.dumps(entries[:100])  # max 100 entries
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Notion ─────────────────────────────────────────────────────────────────

    async def _search_notion(self, inp: dict) -> str:
        query = inp.get("query", "")
        if not self._notion:
            return json.dumps({"error": "Notion adapter not configured"})
        results = await self._notion.search(query, page_size=inp.get("max_results", 5))
        return json.dumps(results)

    async def _read_notion_page(self, inp: dict) -> str:
        page_id = inp.get("page_id", "")
        if not page_id:
            return json.dumps({"error": "page_id parameter required"})
        if not self._notion:
            return json.dumps({"error": "Notion adapter not configured"})
        content = await self._notion.get_page(page_id)
        return content

    async def _create_notion_note(self, inp: dict) -> str:
        title = inp.get("title", "Nueva nota")
        content = inp.get("content", "")
        parent_id = inp.get("parent_page_id")
        if not self._notion:
            return json.dumps({"error": "Notion adapter not configured"})
        result = await self._notion.create_page(title, content, parent_id)
        return json.dumps(result)

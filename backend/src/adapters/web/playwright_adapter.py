"""
Playwright Adapter — automatización de Chrome para Atlas AI.

Gestiona un único browser Chromium headless compartido por proceso.
Cada sesión de usuario tiene su propio BrowserContext (cookies/storage aislado).

Usa la API ASYNC de Playwright en un asyncio.ProactorEventLoop dedicado
que corre en un hilo daemon. Esto evita el NotImplementedError de
asyncio.create_subprocess_exec en Python 3.13 + Windows con el
SelectorEventLoop de uvicorn, sin tocar la política global de asyncio.
"""

import asyncio
import base64
import logging
import sys
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PlaywrightAdapter:
    """
    Adapter de navegación web usando Playwright Chromium headless.

    Ejecuta la API async de Playwright en un ProactorEventLoop dedicado
    corriendo en un hilo daemon. El loop de uvicorn (SelectorEventLoop)
    se puente con asyncio.run_coroutine_threadsafe + run_in_executor.

    Ciclo de vida:
        await adapter.start()   # al iniciar la app (lifespan)
        ...uso durante runtime...
        await adapter.stop()    # al cerrar la app (lifespan)
    """

    def __init__(self):
        # Crear ProactorEventLoop en Windows para soportar subprocesos.
        # En otros sistemas, un loop nuevo estándar es suficiente.
        if sys.platform == "win32":
            self._pw_loop = asyncio.ProactorEventLoop()
        else:
            self._pw_loop = asyncio.new_event_loop()

        # Hilo daemon que mantiene el loop corriendo indefinidamente.
        self._pw_thread = threading.Thread(
            target=self._pw_loop.run_forever,
            name="playwright-loop",
            daemon=True,
        )
        self._pw_thread.start()

        self._pw = None
        self._browser = None
        # session_id → (BrowserContext, Page)
        self._contexts: Dict[str, Any] = {}
        self._available = False

    # ── Internos: corrutinas que corren en el ProactorEventLoop ──────────────

    def _schedule(self, coro) -> "asyncio.Future":
        """Envía una corrutina al ProactorEventLoop y retorna un Future."""
        return asyncio.run_coroutine_threadsafe(coro, self._pw_loop)

    async def _bridge(self, coro, timeout: float = 30.0):
        """
        Puente desde el loop de uvicorn al ProactorEventLoop.
        Schedula la corrutina y espera su resultado en un executor
        para no bloquear el loop de uvicorn.
        """
        future = self._schedule(coro)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, future.result, timeout)

    async def _async_start(self) -> None:
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    async def _async_stop(self) -> None:
        for ctx, _ in list(self._contexts.values()):
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def _async_get_page(self, session_id: str):
        """Obtiene o crea el BrowserContext y Page para la sesión."""
        if session_id not in self._contexts:
            ctx = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await ctx.new_page()
            self._contexts[session_id] = (ctx, page)
        _, page = self._contexts[session_id]
        return page

    async def _async_screenshot(self, session_id: str) -> str:
        """Toma screenshot de la página actual y retorna base64 JPEG."""
        try:
            page = await self._async_get_page(session_id)
            png_bytes = await page.screenshot(type="jpeg", quality=70, full_page=False)
            return base64.b64encode(png_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"[{session_id}] Screenshot failed: {e}")
            return ""

    async def _async_navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        page = await self._async_get_page(session_id)
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        title = await page.title()
        current_url = page.url
        screenshot_b64 = await self._async_screenshot(session_id)
        logger.info(f"[{session_id}] 🌐 Navigated to: {current_url}")
        return {
            "success": True,
            "url": current_url,
            "title": title,
            "screenshot_b64": screenshot_b64,
            "error": None,
        }

    async def _async_click(self, session_id: str, selector: str) -> Dict[str, Any]:
        page = await self._async_get_page(session_id)
        await page.click(selector, timeout=5000)
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        return {
            "success": True,
            "screenshot_b64": await self._async_screenshot(session_id),
            "error": None,
        }

    async def _async_type_text(self, session_id: str, selector: str, text: str) -> Dict[str, Any]:
        page = await self._async_get_page(session_id)
        await page.click(selector, timeout=5000)
        await page.fill(selector, text, timeout=5000)
        return {
            "success": True,
            "screenshot_b64": await self._async_screenshot(session_id),
            "error": None,
        }

    async def _async_get_content(self, session_id: str) -> Dict[str, Any]:
        page = await self._async_get_page(session_id)
        content = await page.evaluate(
            "() => document.body ? document.body.innerText.slice(0, 4000) : ''"
        )
        return {
            "content": content,
            "url": page.url,
            "title": await page.title(),
            "error": None,
        }

    # ── API pública async (bridgea desde el loop de uvicorn) ─────────────────

    async def start(self) -> None:
        """Lanza Chromium headless. Llamar en lifespan startup."""
        try:
            await self._bridge(self._async_start(), timeout=30.0)
            self._available = True
            logger.info("✅ PlaywrightAdapter: Chromium started (ProactorEventLoop thread)")
        except Exception as e:
            logger.error(f"❌ PlaywrightAdapter: Failed to start: {e}")

    async def stop(self) -> None:
        """Cierra todos los contextos y el browser."""
        try:
            await self._bridge(self._async_stop(), timeout=15.0)
        except Exception:
            pass
        self._pw_loop.call_soon_threadsafe(self._pw_loop.stop)
        logger.info("PlaywrightAdapter: browser stopped")

    async def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        """
        Navega a una URL y retorna screenshot + metadata.

        Returns:
            {success, url, title, screenshot_b64, error}
        """
        if not self._available:
            return {"success": False, "url": url, "title": "", "screenshot_b64": "", "error": "Browser not available"}
        try:
            return await self._bridge(self._async_navigate(session_id, url), timeout=30.0)
        except Exception as e:
            logger.error(f"[{session_id}] Navigate error: {e}")
            return {"success": False, "url": url, "title": "", "screenshot_b64": "", "error": str(e)}

    async def click(self, session_id: str, selector: str) -> Dict[str, Any]:
        """
        Hace click en un elemento (selector CSS o texto).

        Returns:
            {success, screenshot_b64, error}
        """
        if not self._available:
            return {"success": False, "screenshot_b64": "", "error": "Browser not available"}
        try:
            return await self._bridge(self._async_click(session_id, selector), timeout=15.0)
        except Exception as e:
            logger.error(f"[{session_id}] Click error on '{selector}': {e}")
            return {"success": False, "screenshot_b64": "", "error": str(e)}

    async def type_text(self, session_id: str, selector: str, text: str) -> Dict[str, Any]:
        """
        Escribe texto en un campo de formulario.

        Returns:
            {success, screenshot_b64, error}
        """
        if not self._available:
            return {"success": False, "screenshot_b64": "", "error": "Browser not available"}
        try:
            return await self._bridge(self._async_type_text(session_id, selector, text), timeout=15.0)
        except Exception as e:
            logger.error(f"[{session_id}] Type error on '{selector}': {e}")
            return {"success": False, "screenshot_b64": "", "error": str(e)}

    async def get_content(self, session_id: str) -> Dict[str, Any]:
        """
        Extrae el texto visible de la página actual.

        Returns:
            {content, url, title, error}
        """
        if not self._available:
            return {"content": "", "url": "", "title": "", "error": "Browser not available"}
        try:
            return await self._bridge(self._async_get_content(session_id), timeout=15.0)
        except Exception as e:
            logger.error(f"[{session_id}] Get content error: {e}")
            return {"content": "", "url": "", "title": "", "error": str(e)}

    async def screenshot(self, session_id: str) -> str:
        """Toma screenshot de la página actual. Retorna base64 JPEG."""
        if not self._available:
            return ""
        try:
            return await self._bridge(self._async_screenshot(session_id), timeout=15.0)
        except Exception as e:
            logger.error(f"[{session_id}] Screenshot error: {e}")
            return ""

    def close_session(self, session_id: str) -> None:
        """Elimina el BrowserContext de la sesión (limpieza en disconnect)."""
        entry = self._contexts.pop(session_id, None)
        if entry:
            ctx, _ = entry
            self._schedule(ctx.close())

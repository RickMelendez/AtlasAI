"""
Notion Adapter — acceso de lectura/escritura a Notion via notion-client SDK.

Requiere NOTION_API_KEY en .env (secret_...).
Si la key no está configurada, todos los métodos retornan un mensaje de error
sin lanzar excepciones.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotionAdapter:
    """
    Adapter de Notion usando el SDK oficial notion-client.

    Operaciones disponibles:
    - search(query): Busca páginas y bases de datos
    - get_page(page_id): Lee el contenido de una página como texto
    - create_page(title, content, parent_id): Crea una nueva página

    Si NOTION_API_KEY no está configurada, retorna mensajes de error
    descriptivos en lugar de lanzar excepciones.
    """

    def __init__(self, api_key: Optional[str] = None):
        from src.infrastructure.config.settings import get_settings
        settings = get_settings()
        self._api_key = api_key or getattr(settings, "notion_api_key", None)
        self._client = None

        if self._api_key:
            try:
                from notion_client import AsyncClient
                self._client = AsyncClient(auth=self._api_key)
                logger.info("✅ NotionAdapter initialized")
            except ImportError:
                logger.warning("⚠️  notion-client package not installed")
            except Exception as e:
                logger.warning(f"⚠️  NotionAdapter init error: {e}")
        else:
            logger.info("ℹ️  NOTION_API_KEY not set — Notion integration disabled")

    @property
    def available(self) -> bool:
        return self._client is not None

    async def search(self, query: str, page_size: int = 5) -> List[Dict[str, Any]]:
        """
        Busca páginas y bases de datos en Notion.

        Returns:
            Lista de dicts con {id, title, url, type} o [{"error": "..."}]
        """
        if not self._client:
            return [{"error": "Notion not configured — add NOTION_API_KEY to .env"}]
        try:
            response = await self._client.search(
                query=query,
                page_size=page_size,
                filter={"value": "page", "property": "object"},
            )
            results = []
            for item in response.get("results", []):
                title = self._extract_title(item)
                results.append({
                    "id": item.get("id", ""),
                    "title": title,
                    "url": item.get("url", ""),
                    "type": item.get("object", "page"),
                })
            return results
        except Exception as e:
            logger.error(f"Notion search error: {e}")
            return [{"error": str(e)}]

    async def get_page(self, page_id: str) -> str:
        """
        Lee el contenido de una página Notion como texto plano.

        Returns:
            Contenido de la página o mensaje de error.
        """
        if not self._client:
            return "Notion not configured — add NOTION_API_KEY to .env"
        try:
            # Obtener bloques de la página
            blocks_response = await self._client.blocks.children.list(
                block_id=page_id, page_size=50
            )
            lines = []
            for block in blocks_response.get("results", []):
                text = self._extract_block_text(block)
                if text:
                    lines.append(text)
            return "\n".join(lines) if lines else "(página vacía)"
        except Exception as e:
            logger.error(f"Notion get_page error: {e}")
            return f"Error reading page: {e}"

    async def create_page(
        self,
        title: str,
        content: str,
        parent_page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Crea una nueva página en Notion.

        Args:
            title: Título de la página
            content: Contenido de texto (se crea como bloque paragraph)
            parent_page_id: ID de la página padre (opcional)

        Returns:
            {id, url} de la nueva página, o {"error": "..."}
        """
        if not self._client:
            return {"error": "Notion not configured — add NOTION_API_KEY to .env"}
        try:
            # El parent debe ser workspace o page
            parent: Dict[str, Any]
            if parent_page_id:
                parent = {"type": "page_id", "page_id": parent_page_id}
            else:
                # Buscar el workspace root
                parent = {"type": "workspace", "workspace": True}

            new_page = await self._client.pages.create(
                parent=parent,
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    }
                },
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": content[:2000]}}
                            ]
                        },
                    }
                ],
            )
            return {"id": new_page.get("id", ""), "url": new_page.get("url", "")}
        except Exception as e:
            logger.error(f"Notion create_page error: {e}")
            return {"error": str(e)}

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _extract_title(self, item: dict) -> str:
        """Extrae el título de un resultado de búsqueda Notion."""
        try:
            props = item.get("properties", {})
            for key in ("title", "Name", "Title"):
                if key in props:
                    title_arr = props[key].get("title", [])
                    if title_arr:
                        return title_arr[0].get("plain_text", "")
        except Exception:
            pass
        return "(sin título)"

    def _extract_block_text(self, block: dict) -> str:
        """Extrae texto plano de un bloque Notion."""
        block_type = block.get("type", "")
        try:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text)
            if block_type in ("heading_1", "heading_2", "heading_3"):
                text = f"## {text}"
            elif block_type == "bulleted_list_item":
                text = f"• {text}"
            elif block_type == "numbered_list_item":
                text = f"- {text}"
            return text
        except Exception:
            return ""

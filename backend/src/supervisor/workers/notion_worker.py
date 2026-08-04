"""
Notion worker — read-only search + top-page read.

costTier "cheap", timeout 60s. Never raises: every outcome comes back in
the WorkerResult envelope.
"""

from __future__ import annotations

import logging

from src.supervisor.schema import WorkerResult

logger = logging.getLogger(__name__)

_MAX_PAGE_CHARS = 2000


async def run(task: str, ctx) -> WorkerResult:
    try:
        if ctx.notion is None:
            return WorkerResult(
                source="notion", error="Notion adapter not available", transient=False
            )

        results = await ctx.notion.search(task, page_size=5)

        # El adapter devuelve [{"error": "..."}] en vez de lanzar
        if results and isinstance(results[0], dict) and "error" in results[0]:
            return WorkerResult(
                source="notion", error=results[0]["error"], transient=False
            )

        if not results:
            return WorkerResult(
                source="notion",
                data={"results": [], "top_page": None},
                notes="no matches found",
            )

        top_page = await ctx.notion.get_page(results[0]["id"])
        truncated = len(top_page) > _MAX_PAGE_CHARS
        return WorkerResult(
            source="notion",
            data={"results": results, "top_page": top_page[:_MAX_PAGE_CHARS]},
            confidence="direct",
            truncated=truncated,
        )

    except Exception as e:  # contrato: nunca lanzar
        logger.warning(f"[notion worker] {e}")
        return WorkerResult(
            source="notion",
            error=str(e),
            transient=isinstance(e, (ConnectionError, TimeoutError, OSError)),
        )

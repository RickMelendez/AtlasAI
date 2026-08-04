"""
Research worker — browse the web via Playwright, summarize with Haiku.

costTier "expensive" (LLM call), timeout 180s. Read-only. Never raises.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

from src.supervisor.schema import WorkerResult

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")

_SUMMARIZE_SYSTEM = (
    "You summarize web page content for a research task. "
    "Answer the task directly using ONLY the page content provided. "
    "If the content does not answer the task, say so plainly. "
    "Maximum 5 sentences, no markdown."
)


def _block_text(response) -> str:
    """Content block text — dict under ANTHROPIC_MOCK, attr on the real API."""
    if not response.content:
        return ""
    block = response.content[0]
    return block["text"] if isinstance(block, dict) else block.text


async def run(task: str, ctx) -> WorkerResult:
    try:
        if ctx.playwright is None:
            return WorkerResult(
                source="research",
                error="Playwright adapter not available",
                transient=False,
            )

        if ctx.progress:
            await ctx.progress("navigating")

        match = _URL_RE.search(task)
        url = (
            match.group(0)
            if match
            else "https://duckduckgo.com/html/?q=" + urllib.parse.quote(task)
        )

        nav = await ctx.playwright.navigate(ctx.session_id, url)
        if nav.get("error"):
            return WorkerResult(source="research", error=nav["error"], transient=True)

        page = await ctx.playwright.get_content(ctx.session_id)
        if page.get("error"):
            return WorkerResult(source="research", error=page["error"], transient=True)

        content = page.get("content", "") or ""
        if not content.strip():
            return WorkerResult(
                source="research",
                data={"url": url, "summary": None},
                notes="page had no readable text",
            )

        if ctx.progress:
            await ctx.progress("summarizing")

        # Haiku para velocidad/costo — el mock exige los 5 kwargs
        response = await ctx.claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            temperature=0.2,
            system=_SUMMARIZE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Task: {task}\n\nPage content:\n{content}",
                }
            ],
        )
        summary = _block_text(response).strip()

        return WorkerResult(
            source="research",
            data={"url": url, "summary": summary},
            confidence="direct",
            truncated=len(content) >= 4000,  # el adapter corta a 4000 chars
        )

    except Exception as e:  # contrato: nunca lanzar
        logger.warning(f"[research worker] {e}")
        return WorkerResult(
            source="research",
            error=str(e),
            transient=isinstance(e, (ConnectionError, TimeoutError, OSError)),
        )

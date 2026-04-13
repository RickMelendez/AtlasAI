"""
Command Router - Fast deterministic routing for UI commands and navigation.

Handles:
- UI command detection (dismiss, open chat)
- Fast routing to known sites (0ms latency, no LLM)
- Language detection
- Transcript cleanup
- Screen context detection
"""

from typing import Optional

# UI command trigger sets
DISMISS_TRIGGERS = {
    "dismiss",
    "go away",
    "hide",
    "minimize",
    "bye atlas",
    "goodbye atlas",
}
CHAT_OPEN_TRIGGERS = {
    "open chat",
    "chat mode",
    "open chat mode",
    "show chat",
    "open chat mode",
}

WAKE_PREFIXES = ("hey atlas,", "hey atlas", "hola atlas,", "hola atlas", "atlas,", "atlas")

# Fast route mapping
KNOWN_SITES = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "twitter": "https://twitter.com",
    "dribbble": "https://dribbble.com",
    "notion": "https://notion.so",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "figma": "https://figma.com",
    "linkedin": "https://linkedin.com",
    "reddit": "https://reddit.com",
    "spotify": "https://open.spotify.com",
    "gmail": "https://mail.google.com",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "google drive": "https://drive.google.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
}

# Language detection helpers
EN_WORDS = {
    "the",
    "is",
    "it",
    "in",
    "of",
    "a",
    "an",
    "and",
    "to",
    "you",
    "i",
    "what",
    "how",
    "can",
    "do",
    "my",
    "me",
    "this",
    "that",
    "are",
    "was",
    "be",
    "have",
    "has",
    "will",
    "with",
    "for",
    "on",
    "at",
    "by",
    "from",
    "or",
    "but",
    "not",
    "yes",
    "ok",
    "please",
    "make",
    "show",
    "run",
    "open",
    "go",
    "help",
    "use",
    "get",
    "need",
    "want",
    "im",
    "i'm",
    "hey",
    "hi",
    "hello",
    "its",
    "it's",
    "just",
    "dont",
    "don't",
}
ES_CHARS = set("áéíóúüñ¿¡")

# Screen context keywords
SCREEN_KEYWORDS = {
    # English
    "this",
    "here",
    "screen",
    "error",
    "see",
    "look",
    "what",
    "window",
    "page",
    "browser",
    "terminal",
    "code",
    "file",
    "line",
    "tab",
    "site",
    "url",
    "running",
    "showing",
    "warning",
    "bug",
    "crash",
    "output",
    # Spanish
    "esto",
    "aquí",
    "aqui",
    "pantalla",
    "ves",
    "mira",
    "ver",
    "línea",
    "linea",
    "código",
    "codigo",
    "archivo",
    "página",
    "pagina",
    "navegador",
    "terminal",
    "corriendo",
    "mostrando",
    "error",
    "fallo",
}

# Filler words for transcript cleanup
FILLER_WORDS = {"uh", "um", "like", "maybe", "actually", "yeah", "so", "well", "hmm"}


def strip_wake_prefix(text: str) -> str:
    """Remove wake-word prefix from text."""
    for prefix in WAKE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def detect_language(text: str) -> str:
    """
    Detect language based on character and word heuristics.

    Args:
        text: Text to analyze

    Returns:
        "en" or "es"
    """
    if any(c in ES_CHARS for c in text):
        return "es"
    words = {w.strip("'.,!?") for w in text.lower().split()}
    return "en" if words & EN_WORDS else "es"


def needs_screen_context(text: str) -> bool:
    """
    Check if message seems to reference the screen.

    Args:
        text: User message

    Returns:
        True if screen context should be included
    """
    words = {w.strip("'.,!?") for w in text.lower().split()}
    return bool(words & SCREEN_KEYWORDS)


def clean_transcript(text: str) -> str:
    """
    Remove filler words and bias toward last intent.

    Example: "open github uh maybe actually yeah open repo" → "open repo"

    Args:
        text: Transcript to clean

    Returns:
        Cleaned transcript
    """
    words = text.lower().split()
    filtered = [w for w in words if w not in FILLER_WORDS]
    cleaned = " ".join(filtered)

    # Last-intent bias: humans correct themselves at the end
    for keyword in ("open", "search", "find", "go to"):
        if cleaned.count(keyword) > 1:
            parts = cleaned.split(keyword)
            cleaned = keyword + parts[-1].strip()
            break

    return cleaned.strip()


def fast_route(text: str) -> Optional[dict]:
    """
    Deterministic routing for high-confidence commands (0ms latency).

    Returns a tool/args dict for immediate execution, or None to fall through to Claude.

    Args:
        text: Cleaned user command

    Returns:
        Dict with tool and args, or None
    """
    t = text.lower().strip().rstrip(".")

    # Ambiguous — let Claude handle
    if "my " in t or "workspace" in t:
        return None

    # "open {site}" → direct navigation
    if t.startswith("open "):
        target = t[5:].strip()
        if target in KNOWN_SITES:
            return {"tool": "browse_web", "args": {"url": KNOWN_SITES[target]}}
        # Heuristic fallback for unknown single-word sites
        clean = target.replace(" ", "")
        if clean.isalpha() and len(clean) < 20:
            return {"tool": "browse_web", "args": {"url": f"https://{clean}.com"}}
        return None

    # "search X on Y" → direct search
    if t.startswith("search ") and " on " in t:
        parts = t[7:].split(" on ", 1)
        query = parts[0].strip()
        site = parts[1].strip()
        if site in KNOWN_SITES:
            base = KNOWN_SITES[site]
            url = f"{base}/search?q={query.replace(' ', '+')}"
            return {"tool": "browse_web", "args": {"url": url}}

    # "go to {site}" → direct navigation
    if t.startswith("go to "):
        target = t[6:].strip()
        if target in KNOWN_SITES:
            return {"tool": "browse_web", "args": {"url": KNOWN_SITES[target]}}

    return None  # Everything else → Claude

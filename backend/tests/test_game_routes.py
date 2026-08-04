"""
Game Route Tests — Atlas AI

Verifies /api/game/chat never leaks raw exception text to the client
(information-disclosure fix flagged by automated push security review).

No real API keys, no network — get_claude_adapter is monkeypatched to a
fake that raises, exercising only the route's error-handling path.

Run with: pytest tests/test_game_routes.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi.testclient import TestClient

from src.infrastructure.config.settings import get_settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    get_settings.cache_clear()
    from src.main import app

    yield TestClient(app)
    get_settings.cache_clear()


class _FakeClaudeThatFails:
    async def generate_response(self, **kwargs):
        raise RuntimeError("Traceback: sk-ant-super-secret-internal-key-detail")


class TestGameChatErrorHandling:
    def test_chat_error_does_not_leak_exception_text(self, client, monkeypatch):
        import src.adapters.ai.claude_adapter as claude_adapter_module

        monkeypatch.setattr(
            claude_adapter_module, "get_claude_adapter", lambda: _FakeClaudeThatFails()
        )

        resp = client.post("/api/game/chat", json={"message": "hello"})

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "sk-ant-super-secret-internal-key-detail" not in detail
        assert "Traceback" not in detail
        assert "ref:" in detail

    def test_chat_error_response_id_is_logged(self, client, monkeypatch, caplog):
        import logging

        import src.adapters.ai.claude_adapter as claude_adapter_module

        monkeypatch.setattr(
            claude_adapter_module, "get_claude_adapter", lambda: _FakeClaudeThatFails()
        )

        with caplog.at_level(logging.ERROR):
            resp = client.post("/api/game/chat", json={"message": "hello"})

        error_id = resp.json()["detail"].split("ref: ")[1].rstrip(")")
        assert any(error_id in record.message for record in caplog.records)

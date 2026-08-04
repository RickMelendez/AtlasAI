"""
Auth + Rate Limiting Tests — Atlas AI

Tests the shared-secret gate (require_api_key, verify_websocket_key) and the
WebSocket connection-attempt rate limiter in isolation — no real Settings
object, no network, no running server.

Run with: pytest tests/test_auth.py -v
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.infrastructure.api import auth as auth_module
from src.infrastructure.api.auth import require_api_key, verify_websocket_key
from src.infrastructure.api.routes.websocket import (
    _ws_connect_times,
    _ws_rate_limited,
    _WS_MAX_CONNECTS_PER_WINDOW,
)
from src.infrastructure.config.settings import get_settings


def run(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


def _patch_settings(monkeypatch, api_key):
    """Point auth.get_settings() at a stub Settings with a fixed atlas_api_key."""
    monkeypatch.setattr(
        auth_module, "get_settings", lambda: SimpleNamespace(atlas_api_key=api_key)
    )


class FakeWebSocket:
    """Minimal stand-in — verify_websocket_key only reads .query_params.get(...)."""

    def __init__(self, query_params: dict):
        self.query_params = query_params


# ─────────────────────────────────────────────────────────────────────────────
# require_api_key (HTTP dependency)
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireApiKey:
    def test_no_key_configured_allows_any_header(self, monkeypatch):
        _patch_settings(monkeypatch, None)
        run(require_api_key(x_atlas_key=None))
        run(require_api_key(x_atlas_key="anything"))  # neither should raise

    def test_key_configured_correct_header_passes(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        run(require_api_key(x_atlas_key="secret123"))  # should not raise

    def test_key_configured_missing_header_raises_401(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        with pytest.raises(HTTPException) as exc_info:
            run(require_api_key(x_atlas_key=None))
        assert exc_info.value.status_code == 401

    def test_key_configured_wrong_header_raises_401(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        with pytest.raises(HTTPException) as exc_info:
            run(require_api_key(x_atlas_key="wrong-key"))
        assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# verify_websocket_key (WS handshake gate)
# ─────────────────────────────────────────────────────────────────────────────


class TestVerifyWebsocketKey:
    def test_no_key_configured_allows_connection(self, monkeypatch):
        _patch_settings(monkeypatch, None)
        ws = FakeWebSocket(query_params={})
        assert verify_websocket_key(ws) is True

    def test_key_configured_correct_query_param_allows(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        ws = FakeWebSocket(query_params={"key": "secret123"})
        assert verify_websocket_key(ws) is True

    def test_key_configured_missing_query_param_denies(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        ws = FakeWebSocket(query_params={})
        assert verify_websocket_key(ws) is False

    def test_key_configured_wrong_query_param_denies(self, monkeypatch):
        _patch_settings(monkeypatch, "secret123")
        ws = FakeWebSocket(query_params={"key": "wrong"})
        assert verify_websocket_key(ws) is False


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket connection rate limiter
# ─────────────────────────────────────────────────────────────────────────────


class TestWsRateLimiter:
    def setup_method(self):
        _ws_connect_times.clear()

    def test_allows_up_to_the_limit(self):
        ip = "1.2.3.4"
        for _ in range(_WS_MAX_CONNECTS_PER_WINDOW):
            assert _ws_rate_limited(ip) is False

    def test_blocks_after_limit_exceeded(self):
        ip = "5.6.7.8"
        for _ in range(_WS_MAX_CONNECTS_PER_WINDOW):
            _ws_rate_limited(ip)
        assert _ws_rate_limited(ip) is True

    def test_different_ips_have_independent_limits(self):
        for _ in range(_WS_MAX_CONNECTS_PER_WINDOW):
            _ws_rate_limited("9.9.9.9")
        assert _ws_rate_limited("9.9.9.9") is True
        assert _ws_rate_limited("1.1.1.1") is False

    def test_old_attempts_expire_out_of_window(self):
        ip = "2.2.2.2"
        for _ in range(_WS_MAX_CONNECTS_PER_WINDOW):
            _ws_rate_limited(ip)
        assert _ws_rate_limited(ip) is True
        # Simulate the window elapsing by clearing recorded timestamps —
        # equivalent to all prior attempts aging out.
        _ws_connect_times[ip].clear()
        assert _ws_rate_limited(ip) is False


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end route wiring — exercises the real FastAPI app + dependency
# injection (not just the isolated functions above), without triggering the
# full lifespan (no Playwright/Whisper startup — TestClient isn't used as a
# context manager, so `container.initialize()` never runs).
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    get_settings.cache_clear()
    from src.main import app

    yield TestClient(app)
    get_settings.cache_clear()


class TestSettingsRouteAuthWiring:
    def test_get_settings_unauthenticated_when_no_key_configured(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_get_settings_requires_header_when_key_configured(self, client, monkeypatch):
        monkeypatch.setenv("ATLAS_API_KEY", "topsecret")
        get_settings.cache_clear()
        resp = client.get("/api/settings")
        assert resp.status_code == 401

    def test_get_settings_correct_header_succeeds_when_key_configured(self, client, monkeypatch):
        monkeypatch.setenv("ATLAS_API_KEY", "topsecret")
        get_settings.cache_clear()
        resp = client.get("/api/settings", headers={"X-Atlas-Key": "topsecret"})
        assert resp.status_code == 200


class TestGameRouteAuthWiring:
    def test_game_health_unauthenticated_when_no_key_configured(self, client):
        resp = client.get("/api/game/health")
        assert resp.status_code == 200

    def test_game_health_requires_header_when_key_configured(self, client, monkeypatch):
        monkeypatch.setenv("ATLAS_API_KEY", "topsecret")
        get_settings.cache_clear()
        resp = client.get("/api/game/health")
        assert resp.status_code == 401


class TestWebSocketAuthWiring:
    def test_ws_connects_when_no_key_configured(self, client):
        with client.websocket_connect("/api/ws") as ws:
            pass  # connecting without raising is the assertion

    def test_ws_rejected_without_key_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("ATLAS_API_KEY", "topsecret")
        get_settings.cache_clear()
        # Server accepts (needed to send a close reason) then immediately
        # closes with 4401 — the client-side handshake succeeds, so the
        # rejection surfaces on the first receive, not on connect.
        with client.websocket_connect("/api/ws") as ws:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()
        assert exc_info.value.code == 4401

    def test_ws_accepts_correct_key_query_param_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("ATLAS_API_KEY", "topsecret")
        get_settings.cache_clear()
        with client.websocket_connect("/api/ws?key=topsecret") as ws:
            pass  # connecting without raising is the assertion

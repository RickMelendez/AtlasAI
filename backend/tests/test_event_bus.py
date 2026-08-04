"""
EventBus Tests — Atlas AI

Tests for the event bus pub/sub system: emit, on, error isolation.
No API keys, no network, pure Python.

Run with: pytest tests/test_event_bus.py -v
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.infrastructure.events.event_bus import EventBus
from src.infrastructure.events.event_types import EventType


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def bus():
    """Fresh EventBus for every test."""
    return EventBus()


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusRegistration:
    def test_on_registers_handler(self, bus):
        handler = lambda d: None
        bus.on("test_event", handler)
        assert "test_event" in bus.listeners
        assert handler in bus.listeners["test_event"]

    def test_multiple_handlers_same_event(self, bus):
        h1 = lambda d: None
        h2 = lambda d: None
        bus.on("test_event", h1)
        bus.on("test_event", h2)
        assert len(bus.listeners["test_event"]) == 2

    def test_handlers_for_different_events(self, bus):
        h1 = lambda d: None
        h2 = lambda d: None
        bus.on("event_a", h1)
        bus.on("event_b", h2)
        assert "event_a" in bus.listeners
        assert "event_b" in bus.listeners

    def test_empty_bus_has_no_listeners(self, bus):
        assert len(bus.listeners) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Sync Handler Emit
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusSyncEmit:
    def test_emit_calls_sync_handler(self, bus):
        received = []

        def handler(data):
            received.append(data)

        bus.on("test_event", handler)
        run(bus.emit("test_event", {"key": "value"}))
        assert received == [{"key": "value"}]

    def test_emit_calls_multiple_sync_handlers(self, bus):
        results = []
        bus.on("evt", lambda d: results.append("h1"))
        bus.on("evt", lambda d: results.append("h2"))
        run(bus.emit("evt", None))
        assert "h1" in results
        assert "h2" in results

    def test_emit_no_data_passes_none(self, bus):
        received = []
        bus.on("evt", lambda d: received.append(d))
        run(bus.emit("evt"))
        assert received == [None]

    def test_emit_event_with_no_listeners_is_no_op(self, bus):
        # Should not raise
        run(bus.emit("unregistered_event", {"x": 1}))

    def test_emit_does_not_cross_contaminate_events(self, bus):
        a_received = []
        b_received = []
        bus.on("event_a", lambda d: a_received.append(d))
        bus.on("event_b", lambda d: b_received.append(d))
        run(bus.emit("event_a", "A"))
        assert a_received == ["A"]
        assert b_received == []


# ─────────────────────────────────────────────────────────────────────────────
# Async Handler Emit
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusAsyncEmit:
    def test_emit_calls_async_handler(self, bus):
        received = []

        async def async_handler(data):
            received.append(data)

        bus.on("async_evt", async_handler)
        run(bus.emit("async_evt", "hello"))
        assert received == ["hello"]

    def test_emit_mixed_sync_and_async_handlers(self, bus):
        results = []

        def sync_handler(data):
            results.append("sync")

        async def async_handler(data):
            results.append("async")

        bus.on("mixed", sync_handler)
        bus.on("mixed", async_handler)
        run(bus.emit("mixed", None))
        assert "sync" in results
        assert "async" in results

    def test_async_handler_receives_correct_data(self, bus):
        received = []

        async def handler(data):
            received.append(data)

        bus.on("data_evt", handler)
        run(bus.emit("data_evt", {"num": 42}))
        assert received[0]["num"] == 42


# ─────────────────────────────────────────────────────────────────────────────
# Error Isolation — Failing handler must not block others
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusErrorIsolation:
    def test_failing_sync_handler_does_not_block_next(self, bus):
        results = []

        def bad_handler(data):
            raise ValueError("intentional error")

        def good_handler(data):
            results.append("good")

        bus.on("evt", bad_handler)
        bus.on("evt", good_handler)
        run(bus.emit("evt", None))  # should not raise
        assert "good" in results

    def test_failing_async_handler_does_not_block_next(self, bus):
        results = []

        async def bad_handler(data):
            raise RuntimeError("async error")

        async def good_handler(data):
            results.append("good_async")

        bus.on("evt", bad_handler)
        bus.on("evt", good_handler)
        run(bus.emit("evt", None))
        assert "good_async" in results

    def test_emit_does_not_raise_on_handler_error(self, bus):
        """Emit must never propagate handler exceptions to the caller."""
        bus.on("evt", lambda d: (_ for _ in ()).throw(Exception("boom")))
        # Should not raise
        run(bus.emit("evt", None))

    def test_error_in_first_handler_does_not_prevent_second(self, bus):
        counter = []

        def first(d):
            raise Exception("first fails")

        def second(d):
            counter.append(1)

        bus.on("chain", first)
        bus.on("chain", second)
        run(bus.emit("chain", None))
        assert counter == [1]


# ─────────────────────────────────────────────────────────────────────────────
# EventType Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestEventTypeConstants:
    def test_wake_word_event_type_string(self):
        assert EventType.WAKE_WORD_DETECTED == "wake_word_detected"

    def test_state_changed_event_type_string(self):
        assert EventType.STATE_CHANGED == "state_changed"

    def test_memory_saved_event_type_string(self):
        assert EventType.MEMORY_SAVED == "memory_saved"

    def test_websocket_connected_defined(self):
        assert hasattr(EventType, "WEBSOCKET_CONNECTED")

    def test_websocket_disconnected_defined(self):
        assert hasattr(EventType, "WEBSOCKET_DISCONNECTED")

    def test_conversation_message_defined(self):
        assert hasattr(EventType, "CONVERSATION_MESSAGE")

    def test_all_event_type_values_are_strings(self):
        for event_type in EventType:
            assert isinstance(event_type.value, str), f"{event_type} value should be a string"

    def test_no_duplicate_event_type_values(self):
        values = [e.value for e in EventType]
        assert len(values) == len(set(values)), "Duplicate EventType values detected"

    def test_event_types_are_strings(self):
        """EventType inherits from str — usable directly as dict keys."""
        d = {EventType.WAKE_WORD_DETECTED: "handler"}
        assert d["wake_word_detected"] == "handler"

    def test_bus_accepts_event_type_enum_as_key(self, bus):
        received = []
        bus.on(EventType.WAKE_WORD_DETECTED, lambda d: received.append(d))
        run(bus.emit(EventType.WAKE_WORD_DETECTED, "atlas"))
        assert received == ["atlas"]

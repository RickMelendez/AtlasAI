"""
Domain Entity Tests — Atlas AI

Pure Python tests for domain entities. No API keys, no network, no DB.
Run with: pytest tests/test_domain.py -v

Covers:
- AssistantState: all 6+ mode transitions, guards, helper predicates
- Conversation: deactivate, update_language, touch, serialization
- Message: role helpers, Claude format, serialization
"""

import sys
import os
from datetime import datetime

import pytest

# Make sure backend/src is on the path so imports work without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.domain.entities.assistant_state import AssistantMode, AssistantState
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message, MessageRole


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def state() -> AssistantState:
    """Fresh AssistantState starting in INACTIVE mode."""
    return AssistantState(session_id="test-session-001")


@pytest.fixture
def active_state() -> AssistantState:
    """AssistantState already in ACTIVE mode."""
    s = AssistantState(session_id="test-session-002")
    s.activate()
    return s


@pytest.fixture
def conversation() -> Conversation:
    """Fresh Conversation entity."""
    return Conversation(session_id="test-session-001", language="en")


@pytest.fixture
def user_message(conversation: Conversation) -> Message:
    return Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Hello Atlas!",
    )


@pytest.fixture
def assistant_message(conversation: Conversation) -> Message:
    return Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="Hey Ricky, how can I help?",
    )


# ─────────────────────────────────────────────────────────────────────────────
# AssistantState — Mode Transitions
# ─────────────────────────────────────────────────────────────────────────────


class TestAssistantStateInitial:
    def test_default_mode_is_inactive(self, state):
        assert state.mode == AssistantMode.INACTIVE

    def test_session_id_stored(self, state):
        assert state.session_id == "test-session-001"

    def test_default_language_is_english(self, state):
        assert state.language == "en"

    def test_created_at_set_on_init(self, state):
        assert isinstance(state.created_at, datetime)


class TestAssistantStateActivate:
    def test_activate_from_inactive(self, state):
        state.activate()
        assert state.mode == AssistantMode.ACTIVE

    def test_activate_from_paused(self, state):
        state.activate()
        state.pause()
        state.activate()
        assert state.mode == AssistantMode.ACTIVE

    def test_activate_clears_paused_at(self, state):
        state.activate()
        state.pause()
        assert state.paused_at is not None
        state.activate()
        assert state.paused_at is None

    def test_activate_when_already_active_is_no_op(self, active_state):
        # Should not crash — guard only fires from INACTIVE/PAUSED
        active_state.activate()
        assert active_state.mode == AssistantMode.ACTIVE


class TestAssistantStateDeactivate:
    def test_deactivate_from_active(self, active_state):
        active_state.deactivate()
        assert active_state.mode == AssistantMode.INACTIVE

    def test_deactivate_clears_paused_at(self, active_state):
        active_state.pause()
        active_state.deactivate()
        assert active_state.paused_at is None

    def test_deactivate_updates_last_interaction(self, active_state):
        before = active_state.last_interaction
        active_state.deactivate()
        assert active_state.last_interaction >= before


class TestAssistantStatePause:
    def test_pause_from_active(self, active_state):
        active_state.pause()
        assert active_state.mode == AssistantMode.PAUSED

    def test_pause_sets_paused_at(self, active_state):
        active_state.pause()
        assert active_state.paused_at is not None
        assert isinstance(active_state.paused_at, datetime)

    def test_pause_from_listening(self, active_state):
        active_state.start_listening()
        active_state.pause()
        assert active_state.mode == AssistantMode.PAUSED

    def test_pause_from_inactive_is_no_op(self, state):
        state.pause()
        # Guard: only activates from ACTIVE or LISTENING
        assert state.mode == AssistantMode.INACTIVE
        assert state.paused_at is None


class TestAssistantStateResume:
    def test_resume_from_paused(self, active_state):
        active_state.pause()
        active_state.resume()
        assert active_state.mode == AssistantMode.ACTIVE

    def test_resume_clears_paused_at(self, active_state):
        active_state.pause()
        active_state.resume()
        assert active_state.paused_at is None

    def test_resume_from_non_paused_is_no_op(self, active_state):
        # No crash; mode stays ACTIVE
        active_state.resume()
        assert active_state.mode == AssistantMode.ACTIVE


class TestAssistantStateWakeUp:
    def test_wake_up_from_inactive(self, state):
        state.wake_up("hey atlas")
        assert state.mode == AssistantMode.ACTIVE

    def test_wake_up_stores_keyword(self, state):
        state.wake_up("atlas")
        assert state.last_wake_word == "atlas"

    def test_wake_up_clears_paused_at(self, active_state):
        active_state.pause()
        active_state.wake_up("hey atlas")
        assert active_state.paused_at is None


class TestAssistantStateVoicePipeline:
    """Tests the INACTIVE → LISTENING → THINKING → SPEAKING → ACTIVE flow."""

    def test_full_voice_pipeline(self, active_state):
        active_state.start_listening()
        assert active_state.mode == AssistantMode.LISTENING

        active_state.start_thinking()
        assert active_state.mode == AssistantMode.THINKING

        active_state.start_speaking()
        assert active_state.mode == AssistantMode.SPEAKING

        active_state.finish_speaking()
        assert active_state.mode == AssistantMode.ACTIVE

    def test_start_listening_from_inactive(self, state):
        state.start_listening()
        assert state.mode == AssistantMode.LISTENING

    def test_start_thinking_requires_listening_or_active(self, state):
        # From INACTIVE: should not transition
        state.start_thinking()
        assert state.mode == AssistantMode.INACTIVE

    def test_start_speaking_requires_thinking(self, active_state):
        # From ACTIVE (not THINKING): should not transition
        active_state.start_speaking()
        assert active_state.mode == AssistantMode.ACTIVE

    def test_finish_speaking_requires_speaking(self, active_state):
        # From ACTIVE (not SPEAKING): should not transition
        active_state.finish_speaking()
        assert active_state.mode == AssistantMode.ACTIVE

    def test_reset_to_active_from_any_mode(self, state):
        """reset_to_active is the error recovery path — works from any mode."""
        state.reset_to_active()
        assert state.mode == AssistantMode.ACTIVE


class TestAssistantStatePredicates:
    def test_is_paused_true_when_paused(self, active_state):
        active_state.pause()
        assert active_state.is_paused() is True

    def test_is_paused_false_when_active(self, active_state):
        assert active_state.is_paused() is False

    def test_is_active_true_for_active_modes(self, active_state):
        assert active_state.is_active() is True

        active_state.start_listening()
        assert active_state.is_active() is True

        active_state.start_thinking()
        assert active_state.is_active() is True

        active_state.start_speaking()
        assert active_state.is_active() is True

    def test_is_active_false_for_inactive(self, state):
        assert state.is_active() is False

    def test_can_process_messages_when_active(self, active_state):
        assert active_state.can_process_messages() is True

    def test_cannot_process_messages_when_speaking(self, active_state):
        active_state.start_listening()
        active_state.start_thinking()
        active_state.start_speaking()
        assert active_state.can_process_messages() is False

    def test_cannot_process_messages_when_inactive(self, state):
        assert state.can_process_messages() is False


class TestAssistantStateSerialization:
    def test_to_dict_contains_required_keys(self, active_state):
        d = active_state.to_dict()
        required_keys = {
            "session_id", "mode", "language", "last_interaction",
            "paused_at", "last_wake_word", "created_at",
            "is_paused", "is_active", "can_process_messages",
        }
        assert required_keys.issubset(d.keys())

    def test_to_dict_mode_is_string(self, active_state):
        d = active_state.to_dict()
        assert isinstance(d["mode"], str)
        assert d["mode"] == "active"

    def test_to_dict_paused_at_none_when_not_paused(self, active_state):
        d = active_state.to_dict()
        assert d["paused_at"] is None

    def test_to_dict_paused_at_set_when_paused(self, active_state):
        active_state.pause()
        d = active_state.to_dict()
        assert d["paused_at"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Conversation Entity
# ─────────────────────────────────────────────────────────────────────────────


class TestConversation:
    def test_id_auto_generated(self, conversation):
        assert conversation.id is not None
        assert len(conversation.id) > 0

    def test_is_active_by_default(self, conversation):
        assert conversation.is_active is True

    def test_deactivate(self, conversation):
        conversation.deactivate()
        assert conversation.is_active is False

    def test_deactivate_updates_updated_at(self, conversation):
        before = conversation.updated_at
        conversation.deactivate()
        assert conversation.updated_at >= before

    def test_update_language(self, conversation):
        conversation.update_language("es")
        assert conversation.language == "es"

    def test_update_language_updates_updated_at(self, conversation):
        before = conversation.updated_at
        conversation.update_language("es")
        assert conversation.updated_at >= before

    def test_touch_updates_updated_at(self, conversation):
        before = conversation.updated_at
        conversation.touch()
        assert conversation.updated_at >= before

    def test_to_dict_contains_required_keys(self, conversation):
        d = conversation.to_dict()
        assert "id" in d
        assert "session_id" in d
        assert "language" in d
        assert "is_active" in d
        assert "created_at" in d
        assert "updated_at" in d

    def test_two_conversations_have_different_ids(self):
        c1 = Conversation(session_id="s1")
        c2 = Conversation(session_id="s2")
        assert c1.id != c2.id


# ─────────────────────────────────────────────────────────────────────────────
# Message Entity
# ─────────────────────────────────────────────────────────────────────────────


class TestMessage:
    def test_id_auto_generated(self, user_message):
        assert user_message.id is not None

    def test_is_from_user(self, user_message):
        assert user_message.is_from_user() is True
        assert user_message.is_from_assistant() is False

    def test_is_from_assistant(self, assistant_message):
        assert assistant_message.is_from_assistant() is True
        assert assistant_message.is_from_user() is False

    def test_user_to_claude_format(self, user_message):
        fmt = user_message.to_claude_format()
        assert fmt["role"] == "user"
        assert fmt["content"] == "Hello Atlas!"

    def test_assistant_to_claude_format(self, assistant_message):
        fmt = assistant_message.to_claude_format()
        assert fmt["role"] == "assistant"
        assert fmt["content"] == "Hey Ricky, how can I help?"

    def test_system_message_becomes_assistant_in_claude_format(self, conversation):
        """System role is not valid in Claude's API — mapped to assistant."""
        msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.SYSTEM,
            content="System init",
        )
        fmt = msg.to_claude_format()
        assert fmt["role"] == "assistant"

    def test_to_dict_contains_required_keys(self, user_message):
        d = user_message.to_dict()
        required = {"id", "conversation_id", "role", "content", "created_at",
                    "is_proactive", "tokens_used", "metadata"}
        assert required.issubset(d.keys())

    def test_role_is_string_in_dict(self, user_message):
        d = user_message.to_dict()
        assert d["role"] == "user"

    def test_is_proactive_default_false(self, user_message):
        assert user_message.is_proactive is False

    def test_proactive_message(self, conversation):
        msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="I noticed an error on your screen.",
            is_proactive=True,
        )
        assert msg.is_proactive is True
        assert msg.to_dict()["is_proactive"] is True

    def test_two_messages_have_different_ids(self, conversation):
        m1 = Message(conversation_id=conversation.id, role=MessageRole.USER, content="msg1")
        m2 = Message(conversation_id=conversation.id, role=MessageRole.USER, content="msg2")
        assert m1.id != m2.id

    def test_tokens_used_optional(self, assistant_message):
        assert assistant_message.tokens_used is None
        assistant_message.tokens_used = 142
        assert assistant_message.tokens_used == 142

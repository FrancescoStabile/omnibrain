"""
Tests for OmniBrain Telegram Bot (Day 15-16).

Groups:
    Formatters       — format_proposal, format_status, format_memory_results, etc.
    Authorization    — is_authorized, chat_id filtering
    CommandHandlers  — All /command handlers via handle_command
    InlineKeyboard   — Callback query handling (approve/reject buttons)
    Notifications    — send_notification, send_proposal_notification, queue
    MessageHandler   — Free-text message handling
    Integration      — Full bot lifecycle tests
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnibrain.interfaces.telegram_bot import (
    OmniBrainTelegramBot,
    _escape_md,
    format_memory_results,
    format_proposal,
    format_settings,
    format_status,
)
from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db(tmp_dir):
    return OmniBrainDB(tmp_dir)


@pytest.fixture
def memory(tmp_dir):
    return MemoryManager(tmp_dir, enable_chroma=False)


@pytest.fixture
def bot(db, memory):
    return OmniBrainTelegramBot(
        token="test-token-123",
        db=db,
        memory_manager=memory,
        allowed_chat_ids=[12345],
    )


@pytest.fixture
def bot_no_auth(db, memory):
    """Bot with no chat ID restrictions."""
    return OmniBrainTelegramBot(
        token="test-token",
        db=db,
        memory_manager=memory,
    )


@pytest.fixture
def bot_no_memory(db):
    """Bot without memory manager."""
    return OmniBrainTelegramBot(
        token="test-token",
        db=db,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════════


class TestEscapeMd:
    """Test MarkdownV2 escaping."""

    def test_escapes_special_chars(self):
        assert _escape_md("hello_world") == "hello\\_world"
        assert _escape_md("foo*bar") == "foo\\*bar"

    def test_escapes_brackets(self):
        assert _escape_md("[link](url)") == "\\[link\\]\\(url\\)"

    def test_plain_text_unchanged(self):
        assert _escape_md("hello world") == "hello world"

    def test_empty_string(self):
        assert _escape_md("") == ""

    def test_multiple_specials(self):
        result = _escape_md("a.b!c#d")
        assert result == "a\\.b\\!c\\#d"


class TestFormatProposal:
    """Test proposal formatting."""

    def test_basic_proposal(self):
        p = {"id": 1, "title": "Draft email", "type": "email", "priority": 3, "description": "Reply to Marco"}
        text = format_proposal(p)
        assert "#1" in text
        assert "Draft email" in text
        assert "🟠" in text  # priority 3

    def test_critical_priority(self):
        p = {"id": 2, "title": "Urgent", "type": "call", "priority": 4, "description": ""}
        text = format_proposal(p)
        assert "🔴" in text

    def test_low_priority(self):
        p = {"id": 3, "title": "Archive", "type": "email", "priority": 1, "description": ""}
        text = format_proposal(p)
        assert "🟢" in text

    def test_truncates_long_description(self):
        p = {"id": 4, "title": "T", "type": "x", "priority": 2, "description": "A" * 300}
        text = format_proposal(p)
        # Description limited to 200 chars (before escaping)
        assert len(text) < 500


class TestFormatStatus:
    """Test status formatting."""

    def test_basic_stats(self):
        stats = {"events": 100, "contacts": 50, "proposals_pending": 3, "observations": 42, "briefings": 7, "active_sessions": 1}
        text = format_status(stats)
        assert "Events: 100" in text
        assert "Contacts: 50" in text
        assert "Proposals pending: 3" in text

    def test_with_engine_status(self):
        stats = {"events": 10, "contacts": 5, "proposals_pending": 0, "observations": 0, "briefings": 0, "active_sessions": 0}
        engine = {"running": True, "task_count": 6}
        text = format_status(stats, engine)
        assert "✅ Running" in text
        assert "Tasks: 6" in text

    def test_engine_stopped(self):
        stats = {"events": 0, "contacts": 0, "proposals_pending": 0, "observations": 0, "briefings": 0, "active_sessions": 0}
        engine = {"running": False, "task_count": 0}
        text = format_status(stats, engine)
        assert "⏸ Stopped" in text


class TestFormatMemoryResults:
    """Test memory result formatting."""

    def test_no_results(self):
        text = format_memory_results([], "test query")
        assert "No results" in text
        assert "test query" in text

    def test_with_results(self):
        docs = []
        for i in range(3):
            doc = MagicMock()
            doc.text = f"Result {i}"
            doc.source_type = "email"
            doc.score = 0.9 - i * 0.1
            docs.append(doc)
        text = format_memory_results(docs, "pricing")
        assert "3 results" in text
        assert "pricing" in text

    def test_more_than_5_results(self):
        docs = [MagicMock(text=f"R{i}", source_type="email", score=0.5) for i in range(8)]
        text = format_memory_results(docs, "q")
        assert "and 3 more" in text


class TestFormatSettings:
    """Test settings formatting."""

    def test_no_preferences(self):
        text = format_settings({})
        assert "No preferences" in text

    def test_with_preferences(self):
        prefs = {"briefing_time": "07:00", "language": "italian"}
        text = format_settings(prefs)
        assert "briefing\\_time" in text
        assert "07:00" in text


# ═══════════════════════════════════════════════════════════════════════════
# Authorization
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthorization:
    """Test chat ID authorization."""

    def test_authorized_chat_id(self, bot):
        assert bot.is_authorized(12345)

    def test_unauthorized_chat_id(self, bot):
        assert not bot.is_authorized(99999)

    def test_no_restrictions(self, bot_no_auth):
        assert bot_no_auth.is_authorized(12345)
        assert bot_no_auth.is_authorized(99999)
        assert bot_no_auth.is_authorized(0)


# ═══════════════════════════════════════════════════════════════════════════
# Command Handlers (via handle_command)
# ═══════════════════════════════════════════════════════════════════════════


class TestCommandStart:
    """Test /start and /help."""

    async def test_start(self, bot):
        result = await bot.handle_command("/start")
        assert "OmniBrain" in result

    async def test_help(self, bot):
        result = await bot.handle_command("/help")
        assert "OmniBrain" in result


class TestCommandBriefing:
    """Test /briefing command."""

    async def test_no_briefing_no_generator(self, db, tmp_dir):
        """No briefing and no generator → 'No briefing available.'"""
        bot = OmniBrainTelegramBot(token="t", db=db)
        result = await bot.handle_command("/briefing")
        assert "No briefing" in result

    async def test_existing_briefing(self, bot):
        """If today's briefing exists in DB, return it."""
        from omnibrain.models import Briefing
        briefing = Briefing(
            date=datetime.now().strftime("%Y-%m-%d"),
            type="morning",
            content="Today's briefing content here.",
            events_processed=10,
            actions_proposed=3,
        )
        bot._db.insert_briefing(briefing)
        result = await bot.handle_command("/briefing")
        assert "Today's briefing content here" in result

    async def test_generate_new_briefing(self, bot):
        """If no today's briefing, generate via BriefingGenerator."""
        mock_gen = MagicMock()
        mock_gen.generate_and_store.return_value = (MagicMock(), "Generated briefing text", 1)
        bot._briefing_gen = mock_gen
        result = await bot.handle_command("/briefing")
        assert "Generated briefing text" in result


class TestCommandProposals:
    """Test /proposals command."""

    async def test_no_proposals(self, bot):
        result = await bot.handle_command("/proposals")
        assert "No pending" in result

    async def test_with_proposals(self, bot):
        bot._db.insert_proposal("email", "Draft reply to Marco", "Respond to his pricing question", priority=3)
        bot._db.insert_proposal("calendar", "Schedule meeting", "With the team", priority=2)
        result = await bot.handle_command("/proposals")
        assert "Draft reply" in result
        assert "Schedule meeting" in result


class TestCommandApprove:
    """Test /approve command."""

    async def test_approve_existing(self, bot):
        pid = bot._db.insert_proposal("email", "Draft reply", "test")
        result = await bot.handle_command(f"/approve {pid}")
        assert "Approved" in result

    async def test_approve_not_found(self, bot):
        result = await bot.handle_command("/approve 9999")
        assert "Not found" in result

    async def test_approve_no_args(self, bot):
        result = await bot.handle_command("/approve")
        assert "Usage" in result

    async def test_approve_invalid_id(self, bot):
        result = await bot.handle_command("/approve abc")
        assert "Usage" in result


class TestCommandReject:
    """Test /reject command."""

    async def test_reject_existing(self, bot):
        pid = bot._db.insert_proposal("email", "Draft reply", "test")
        result = await bot.handle_command(f"/reject {pid}")
        assert "Rejected" in result

    async def test_reject_with_reason(self, bot):
        pid = bot._db.insert_proposal("email", "Draft reply", "test")
        result = await bot.handle_command(f"/reject {pid} not relevant")
        assert "Rejected" in result

    async def test_reject_not_found(self, bot):
        result = await bot.handle_command("/reject 9999")
        assert "Not found" in result


class TestCommandSearch:
    """Test /search command."""

    async def test_search_no_query(self, bot):
        result = await bot.handle_command("/search")
        assert "Usage" in result

    async def test_search_with_memory(self, bot):
        bot._memory.store("Meeting with Marco about pricing strategy", source="calendar", source_type="calendar")
        result = await bot.handle_command("/search pricing")
        assert "1 results" in result

    async def test_search_no_results(self, bot):
        result = await bot.handle_command("/search nonexistent_xyz")
        assert "No results" in result or "0 results" in result

    async def test_search_no_memory(self, bot_no_memory):
        result = await bot_no_memory.handle_command("/search test")
        assert "not available" in result


class TestCommandStatus:
    """Test /status command."""

    async def test_status(self, bot):
        result = await bot.handle_command("/status")
        assert "Events:" in result
        assert "Contacts:" in result

    async def test_status_with_engine(self, bot):
        bot._engine_status_fn = lambda: {"running": True, "task_count": 6}
        result = await bot.handle_command("/status")
        assert "Events:" in result


class TestCommandSettings:
    """Test /settings command."""

    async def test_no_settings(self, bot):
        result = await bot.handle_command("/settings")
        assert "No preferences" in result

    async def test_with_settings(self, bot):
        bot._db.set_preference("briefing_time", "07:30")
        bot._db.set_preference("language", "it")
        result = await bot.handle_command("/settings")
        assert "briefing" in result


class TestUnknownCommand:
    """Test unknown command handling."""

    async def test_unknown(self, bot):
        result = await bot.handle_command("/foobar")
        assert "Unknown" in result


# ═══════════════════════════════════════════════════════════════════════════
# Inline Keyboard Callbacks
# ═══════════════════════════════════════════════════════════════════════════


class TestCallbackHandler:
    """Test inline keyboard approve/reject callbacks."""

    async def test_approve_callback(self, bot):
        """Simulate an approval via inline keyboard."""
        pid = bot._db.insert_proposal("email", "Test", "desc")

        query = MagicMock()
        query.data = f"approve:{pid}"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        await bot._callback_handler(update, None)
        query.answer.assert_called_once()
        assert "Approved" in query.answer.call_args[0][0]

    async def test_reject_callback(self, bot):
        """Simulate a rejection via inline keyboard."""
        pid = bot._db.insert_proposal("email", "Test", "desc")

        query = MagicMock()
        query.data = f"reject:{pid}"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        await bot._callback_handler(update, None)
        query.answer.assert_called_once()
        assert "Rejected" in query.answer.call_args[0][0]

    async def test_unauthorized_callback(self, bot):
        """Unauthorized user pressing a button."""
        query = MagicMock()
        query.data = "approve:1"
        query.message = MagicMock()
        query.message.chat_id = 99999  # Not authorized
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        await bot._callback_handler(update, None)
        query.answer.assert_called_with("Unauthorized", show_alert=True)

    async def test_empty_callback(self, bot):
        """Callback with no data."""
        update = MagicMock()
        update.callback_query = None
        await bot._callback_handler(update, None)  # Should not raise

    async def test_invalid_id_callback(self, bot):
        """Callback with invalid proposal ID."""
        query = MagicMock()
        query.data = "approve:abc"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        await bot._callback_handler(update, None)
        query.answer.assert_called_with("Invalid ID", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════
# Notifications
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifications:
    """Test proactive notification system."""

    async def test_queue_when_no_app(self, bot):
        """Without a running app, notifications go to queue."""
        ok = await bot.send_notification(12345, "important", "Test", "Hello!")
        assert not ok
        assert len(bot._notification_queue) == 1
        assert bot._notification_queue[0]["title"] == "Test"

    async def test_notification_queue_persists(self, bot):
        """Multiple notifications queue up."""
        await bot.send_notification(12345, "fyi", "N1", "msg1")
        await bot.send_notification(12345, "important", "N2", "msg2")
        assert len(bot._notification_queue) == 2

    async def test_send_proposal_notification_no_app(self, bot):
        """Proposal notification fails gracefully without app."""
        ok = await bot.send_proposal_notification(12345, {"id": 1, "title": "Test", "type": "email", "priority": 2, "description": ""})
        assert not ok


# ═══════════════════════════════════════════════════════════════════════════
# Message Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestMessageHandler:
    """Test free-text message handling."""

    async def test_message_search_with_results(self, bot):
        """Free text message triggers memory search."""
        bot._memory.store("Pricing meeting with Marco", source="calendar", source_type="calendar")

        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 12345
        update.message.text = "pricing Marco"
        update.message.reply_text = AsyncMock()

        await bot._handle_message(update, None)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "results" in call_text or "pricing" in call_text.lower()

    async def test_message_no_results(self, bot):
        """Free text with no results."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 12345
        update.message.text = "quantum physics equations"
        update.message.reply_text = AsyncMock()

        await bot._handle_message(update, None)
        update.message.reply_text.assert_called_once()

    async def test_message_no_memory(self, bot_no_memory):
        """Free text without memory manager."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 12345  # Add chat_id for auth check
        update.message.text = "hello"
        update.message.reply_text = AsyncMock()

        await bot_no_memory._handle_message(update, None)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "coming soon" in call_text.lower() or "help" in call_text.lower()

    async def test_empty_message(self, bot):
        """Empty message is ignored."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 12345
        update.message.text = ""
        update.message.reply_text = AsyncMock()

        await bot._handle_message(update, None)
        update.message.reply_text.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Auth Check
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthCheck:
    """Test _check_auth helper."""

    def test_check_auth_no_message(self, bot):
        update = MagicMock()
        update.message = None
        assert not bot._check_auth(update)

    def test_check_auth_authorized(self, bot):
        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 12345
        assert bot._check_auth(update)

    def test_check_auth_unauthorized(self, bot):
        update = MagicMock()
        update.message = MagicMock()
        update.message.chat_id = 99999
        update.message.reply_text = AsyncMock()
        assert not bot._check_auth(update)


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end integration tests."""

    async def test_full_proposal_flow(self, bot):
        """Create proposal → list → approve via command."""
        # Insert
        pid = bot._db.insert_proposal("email", "Draft reply to Marco", "About pricing", priority=3)

        # List
        result = await bot.handle_command("/proposals")
        assert "Draft reply" in result

        # Approve
        result = await bot.handle_command(f"/approve {pid}")
        assert "Approved" in result

        # Verify no more pending
        result = await bot.handle_command("/proposals")
        assert "No pending" in result

    async def test_full_reject_flow(self, bot):
        """Create proposal → reject with reason."""
        pid = bot._db.insert_proposal("calendar", "Reschedule meeting", "Move to next week", priority=2)

        result = await bot.handle_command(f"/reject {pid} not needed anymore")
        assert "Rejected" in result

    async def test_memory_store_and_search(self, bot):
        """Store in memory → search via bot command."""
        bot._memory.store("Quarterly review meeting with entire team", source="calendar", source_type="calendar")
        bot._memory.store("Email from investor about Series A", source="gmail", source_type="email")

        result = await bot.handle_command("/search quarterly")
        assert "1 results" in result

    async def test_status_reflects_data(self, bot):
        """Status should show actual data counts."""
        bot._db.insert_proposal("email", "P1", "d1")
        bot._db.insert_proposal("email", "P2", "d2")

        result = await bot.handle_command("/status")
        assert "Proposals pending: 2" in result

    async def test_bot_creation_properties(self, bot):
        """Basic bot properties check."""
        assert not bot.running
        assert bot._token == "test-token-123"
        assert 12345 in bot._allowed_chat_ids

    async def test_build_app_registers_handlers(self, bot):
        """build_app should register all handlers."""
        app = bot.build_app()
        assert app is not None
        # Check handlers were registered
        assert len(app.handlers[0]) >= 9  # 9 command handlers + callback + message

"""
Tests — Email Skill handlers + SkillContext integration access.

Verifies:
    - poll.py: fetches emails, stores in memory, classifies, proposes
    - ask.py: searches memory, formats response
    - event.py: classifies, notifies
    - SkillContext.get_integration(): permission checks, caching, auth
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnibrain.skill_context import PermissionDenied, SkillContext


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_ctx(permissions: set[str] | None = None, *, db=None, memory=None, config=None):
    """Create a SkillContext with the given permissions and optional mocks."""
    perms = permissions or {
        "read_memory", "write_memory", "notify", "llm_access", "google_gmail",
    }
    return SkillContext(
        skill_name="email-manager",
        permissions=perms,
        db=db,
        memory=memory,
        config=config,
    )


def _fake_email(
    *,
    sender="marco@example.com",
    subject="Test subject",
    body="Test body",
    is_unread=True,
    date=None,
    msg_id="msg_001",
):
    return SimpleNamespace(
        id=msg_id,
        sender=sender,
        subject=subject,
        body=body,
        snippet=body[:100],
        is_unread=is_unread,
        date=date or datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════════
# SkillContext.get_integration
# ═══════════════════════════════════════════════════════════════════════════


class TestGetIntegration:
    """Test the new get_integration() method on SkillContext."""

    def test_unknown_integration_raises_value_error(self):
        ctx = _make_ctx()
        with pytest.raises(ValueError, match="Unknown integration"):
            ctx.get_integration("spotify")

    def test_gmail_needs_google_gmail_permission(self):
        ctx = _make_ctx(permissions={"read_memory"})
        with pytest.raises(PermissionDenied, match="google_gmail"):
            ctx.get_integration("gmail")

    def test_calendar_needs_read_calendar_permission(self):
        ctx = _make_ctx(permissions={"read_memory"})
        with pytest.raises(PermissionDenied, match="read_calendar"):
            ctx.get_integration("calendar")

    @patch("omnibrain.integrations.gmail.GmailClient")
    def test_gmail_returns_client_on_success(self, MockGmail):
        instance = MockGmail.return_value
        instance.authenticate.return_value = True
        ctx = _make_ctx(permissions={"google_gmail"})
        client = ctx.get_integration("gmail")
        assert client is instance
        instance.authenticate.assert_called_once()

    @patch("omnibrain.integrations.gmail.GmailClient")
    def test_gmail_returns_none_on_auth_failure(self, MockGmail):
        instance = MockGmail.return_value
        instance.authenticate.return_value = False
        ctx = _make_ctx(permissions={"google_gmail"})
        assert ctx.get_integration("gmail") is None

    @patch("omnibrain.integrations.calendar.CalendarClient")
    def test_calendar_returns_client_on_success(self, MockCal):
        instance = MockCal.return_value
        instance.authenticate.return_value = True
        ctx = _make_ctx(permissions={"read_calendar"})
        client = ctx.get_integration("calendar")
        assert client is instance

    @patch("omnibrain.integrations.gmail.GmailClient")
    def test_integration_cached_per_invocation(self, MockGmail):
        instance = MockGmail.return_value
        instance.authenticate.return_value = True
        ctx = _make_ctx(permissions={"google_gmail"})
        c1 = ctx.get_integration("gmail")
        c2 = ctx.get_integration("gmail")
        assert c1 is c2
        # authenticate only called once due to caching
        assert MockGmail.return_value.authenticate.call_count == 1

    def test_data_dir_from_config(self):
        cfg = SimpleNamespace(data_dir=Path("/tmp/test-brain"))
        ctx = _make_ctx(config=cfg)
        assert ctx._get_data_dir() == Path("/tmp/test-brain")

    def test_data_dir_default(self):
        ctx = _make_ctx()
        assert ctx._get_data_dir() == Path.home() / ".omnibrain"


# ═══════════════════════════════════════════════════════════════════════════
# Email Poll Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailPoll:
    """Test skills/email-manager/handlers/poll.py"""

    @pytest.fixture
    def handler(self, tmp_path):
        """Load the poll handler dynamically."""
        from omnibrain.skill_runtime import _load_handler

        handler_path = Path(__file__).parent.parent / "skills" / "email-manager"
        fn = _load_handler(handler_path, "handlers/poll.py")
        assert fn is not None, "Could not load email poll handler"
        return fn

    @pytest.mark.asyncio
    async def test_returns_error_when_gmail_not_authenticated(self, handler):
        ctx = _make_ctx(permissions={"google_gmail", "read_memory", "write_memory", "notify"})
        # get_integration returns None when auth fails
        ctx.get_integration = MagicMock(return_value=None)
        ctx.get_data = AsyncMock(return_value=None)

        result = await handler(ctx)
        assert result["fetched"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_emails_returns_zero(self, handler):
        gmail_mock = MagicMock()
        gmail_mock.fetch_recent.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=gmail_mock)
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()

        result = await handler(ctx)
        assert result["fetched"] == 0
        assert result["stored"] == 0

    @pytest.mark.asyncio
    async def test_stores_new_emails_in_memory(self, handler):
        emails = [_fake_email(sender="alice@co.com", subject="Hello")]
        gmail_mock = MagicMock()
        gmail_mock.fetch_recent.return_value = emails

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=gmail_mock)
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.propose_action = AsyncMock(return_value=1)

        result = await handler(ctx)
        assert result["stored"] == 1
        ctx.memory_store.assert_called_once()
        ctx.emit_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_urgent_email_proposes_action(self, handler):
        emails = [_fake_email(subject="URGENT: server down", sender="ops@co.com")]
        gmail_mock = MagicMock()
        gmail_mock.fetch_recent.return_value = emails

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=gmail_mock)
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.propose_action = AsyncMock(return_value=1)

        result = await handler(ctx)
        assert result["urgent"] == 1
        assert result["proposed"] == 1
        ctx.propose_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_old_emails_when_last_poll_set(self, handler):
        old = _fake_email(date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        new = _fake_email(date=datetime.now(timezone.utc), msg_id="msg_new")

        gmail_mock = MagicMock()
        gmail_mock.fetch_recent.return_value = [old, new]

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=gmail_mock)
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "last_poll_ts": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
            "max_fetch": 20,
        }.get(k, d))
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.propose_action = AsyncMock(return_value=1)

        result = await handler(ctx)
        # Only the new email should be stored
        assert result["new"] == 1
        assert result["stored"] == 1

    @pytest.mark.asyncio
    async def test_updates_last_poll_ts(self, handler):
        gmail_mock = MagicMock()
        gmail_mock.fetch_recent.return_value = [_fake_email()]

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=gmail_mock)
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.propose_action = AsyncMock(return_value=1)

        await handler(ctx)
        # set_data should be called with last_poll_ts
        calls = [c for c in ctx.set_data.call_args_list if c[0][0] == "last_poll_ts"]
        assert len(calls) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Email Ask Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailAsk:
    """Test skills/email-manager/handlers/ask.py"""

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        handler_path = Path(__file__).parent.parent / "skills" / "email-manager"
        fn = _load_handler(handler_path, "handlers/ask.py")
        assert fn is not None
        return fn

    @pytest.mark.asyncio
    async def test_no_results_returns_message(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.get_contacts = AsyncMock(return_value=[])

        result = await handler(ctx, "what did Marco say?")
        assert "don't have" in result["answer"].lower() or len(result["sources"]) == 0

    @pytest.mark.asyncio
    async def test_returns_sources_from_memory(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[
            {"id": "1", "text": "Email from Marco about pricing", "source": "skill:email-manager", "score": 0.9},
        ])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.llm_complete = AsyncMock(return_value="")

        result = await handler(ctx, "pricing email")
        assert len(result["sources"]) >= 1

    @pytest.mark.asyncio
    async def test_uses_llm_when_available(self, handler):
        ctx = _make_ctx(permissions={"read_memory", "llm_access"})
        ctx.memory_search = AsyncMock(return_value=[
            {"id": "1", "text": "Email from Alice about Q4 budget", "source": "skill:email-manager", "score": 0.8},
        ])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.llm_complete = AsyncMock(return_value="Alice discussed Q4 budget in her email.")

        result = await handler(ctx, "Q4 budget")
        assert "Alice" in result["answer"]


# ═══════════════════════════════════════════════════════════════════════════
# Email Event Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailEvent:
    """Test skills/email-manager/handlers/event.py"""

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        handler_path = Path(__file__).parent.parent / "skills" / "email-manager"
        fn = _load_handler(handler_path, "handlers/event.py")
        assert fn is not None
        return fn

    @pytest.mark.asyncio
    async def test_urgent_email_notifies_important(self, handler):
        ctx = _make_ctx()
        ctx.notify = AsyncMock()
        ctx.get_contacts = AsyncMock(return_value=[])

        result = await handler(ctx, {
            "sender": "boss@co.com",
            "subject": "ASAP",
            "is_urgent": True,
            "is_unread": True,
        })
        assert result["notified"] is True
        ctx.notify.assert_called_once()
        assert "important" in ctx.notify.call_args[1].get("level", ctx.notify.call_args[0][1] if len(ctx.notify.call_args[0]) > 1 else "")

    @pytest.mark.asyncio
    async def test_known_contact_notifies_fyi(self, handler):
        ctx = _make_ctx()
        ctx.notify = AsyncMock()
        ctx.get_contacts = AsyncMock(return_value=[{"name": "Marco", "email": "marco@co.com"}])

        result = await handler(ctx, {
            "sender": "marco@co.com",
            "subject": "Hi",
            "is_urgent": False,
            "is_unread": True,
        })
        assert result["action"] == "notified_known_contact"
        ctx.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_sender_skipped(self, handler):
        ctx = _make_ctx()
        ctx.notify = AsyncMock()
        ctx.get_contacts = AsyncMock(return_value=[])

        result = await handler(ctx, {
            "sender": "random@spam.com",
            "subject": "Win a prize",
            "is_urgent": False,
            "is_unread": True,
        })
        assert result["action"] == "skipped_unknown_sender"
        ctx.notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_email_no_action(self, handler):
        ctx = _make_ctx()
        ctx.notify = AsyncMock()
        ctx.get_contacts = AsyncMock(return_value=[])

        result = await handler(ctx, {
            "sender": "x@co.com",
            "subject": "FYI",
            "is_urgent": False,
            "is_unread": False,
        })
        assert result["action"] == "none"

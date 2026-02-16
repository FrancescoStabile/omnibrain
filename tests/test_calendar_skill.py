"""
Tests — Calendar Skill handlers.

Verifies:
    - poll.py: syncs events, detects conflicts, emits approaching events
    - ask.py: searches memory, formats response
    - event.py: meeting brief notification with attendee context
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import SkillContext


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_ctx(permissions: set[str] | None = None):
    perms = permissions or {
        "read_memory", "write_memory", "notify", "llm_access", "read_calendar",
    }
    return SkillContext(
        skill_name="calendar-assistant",
        permissions=perms,
    )


def _fake_event(
    *,
    title="Team standup",
    start_time=None,
    duration_minutes=30,
    location="Room A",
    attendees=None,
    event_id="ev_001",
):
    return SimpleNamespace(
        id=event_id,
        title=title,
        start_time=start_time or (datetime.now(timezone.utc) + timedelta(hours=2)),
        duration_minutes=duration_minutes,
        location=location,
        attendees=attendees or ["alice@co.com", "bob@co.com"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Poll Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarPoll:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        handler_path = Path(__file__).parent.parent / "skills" / "calendar-assistant"
        fn = _load_handler(handler_path, "handlers/poll.py")
        assert fn is not None
        return fn

    @pytest.mark.asyncio
    async def test_returns_error_when_calendar_not_authenticated(self, handler):
        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=None)
        ctx.get_data = AsyncMock(return_value=None)

        result = await handler(ctx)
        assert result["synced"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_events_returns_zero(self, handler):
        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = []
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="")
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()

        result = await handler(ctx)
        assert result["synced"] == 0
        assert result["conflicts"] == 0

    @pytest.mark.asyncio
    async def test_stores_events_in_memory(self, handler):
        events = [_fake_event(title="Planning"), _fake_event(title="Review", event_id="ev_002")]
        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = events
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="")
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["synced"] == 2
        assert ctx.memory_store.call_count == 2

    @pytest.mark.asyncio
    async def test_detects_overlapping_conflicts(self, handler):
        now = datetime.now(timezone.utc)
        ev1 = _fake_event(title="Meeting A", start_time=now, duration_minutes=60, event_id="ev_a")
        ev2 = _fake_event(title="Meeting B", start_time=now + timedelta(minutes=30), event_id="ev_b")

        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = [ev1, ev2]
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="")
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["conflicts"] == 1
        ctx.notify.assert_called_once()
        assert "conflict" in ctx.notify.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_emits_approaching_event(self, handler):
        soon = datetime.now(timezone.utc) + timedelta(minutes=15)
        ev = _fake_event(title="Standup", start_time=soon, event_id="ev_soon")

        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = [ev]
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="")
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["approaching"] == 1
        ctx.emit_event.assert_called()

        # Check event_approaching was emitted
        event_calls = [c for c in ctx.emit_event.call_args_list if c[0][0] == "event_approaching"]
        assert len(event_calls) == 1
        payload = event_calls[0][0][1]
        assert payload["title"] == "Standup"

    @pytest.mark.asyncio
    async def test_no_conflict_for_non_overlapping(self, handler):
        now = datetime.now(timezone.utc) + timedelta(hours=3)
        ev1 = _fake_event(title="A", start_time=now, duration_minutes=30, event_id="a")
        ev2 = _fake_event(title="B", start_time=now + timedelta(hours=1), event_id="b")

        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = [ev1, ev2]
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="")
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["conflicts"] == 0

    @pytest.mark.asyncio
    async def test_already_notified_not_re_emitted(self, handler):
        soon = datetime.now(timezone.utc) + timedelta(minutes=10)
        ev = _fake_event(title="Daily", start_time=soon, event_id="ev_daily")

        cal_mock = MagicMock()
        cal_mock.get_today_events.return_value = [ev]
        cal_mock.get_upcoming_events.return_value = []

        ctx = _make_ctx()
        ctx.get_integration = MagicMock(return_value=cal_mock)
        ctx.get_data = AsyncMock(return_value="ev_daily")  # Already notified
        ctx.set_data = AsyncMock()
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.emit_event = AsyncMock()
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["approaching"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Ask Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarAsk:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        handler_path = Path(__file__).parent.parent / "skills" / "calendar-assistant"
        fn = _load_handler(handler_path, "handlers/ask.py")
        assert fn is not None
        return fn

    @pytest.mark.asyncio
    async def test_no_results(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])

        result = await handler(ctx, "what's on my schedule?")
        assert "don't have" in result["answer"].lower()
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_returns_calendar_events(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[
            {"id": "1", "text": "Calendar event: Standup\nWhen: 2026-02-16T09:00", "source": "skill:calendar-assistant", "score": 0.9},
        ])
        ctx.llm_complete = AsyncMock(return_value="")

        result = await handler(ctx, "standup meeting")
        assert len(result["events"]) >= 1

    @pytest.mark.asyncio
    async def test_llm_answer_when_available(self, handler):
        ctx = _make_ctx(permissions={"read_memory", "llm_access"})
        ctx.memory_search = AsyncMock(return_value=[
            {"id": "1", "text": "Calendar event: Board meeting at 14:00", "source": "skill:calendar-assistant", "score": 0.9},
        ])
        ctx.llm_complete = AsyncMock(return_value="You have a board meeting at 2 PM.")

        result = await handler(ctx, "what's this afternoon?")
        assert "board meeting" in result["answer"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Event Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarEvent:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        handler_path = Path(__file__).parent.parent / "skills" / "calendar-assistant"
        fn = _load_handler(handler_path, "handlers/event.py")
        assert fn is not None
        return fn

    @pytest.mark.asyncio
    async def test_sends_meeting_brief(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.notify = AsyncMock()

        result = await handler(ctx, {
            "title": "Board meeting",
            "start": "2026-02-16T14:00:00+00:00",
            "minutes_until": 15,
            "attendees": ["ceo@co.com", "cto@co.com"],
            "event_id": "ev_board",
        })
        assert result["briefed"] is True
        ctx.notify.assert_called_once()
        assert "Board meeting" in ctx.notify.call_args[0][0]

    @pytest.mark.asyncio
    async def test_includes_attendee_context(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(side_effect=lambda q, **kw: [
            {"text": f"Last discussion with {q}: pricing strategy"}
        ] if "alice" in q.lower() else [])
        ctx.notify = AsyncMock()

        result = await handler(ctx, {
            "title": "Strategy sync",
            "start": "2026-02-16T10:00:00+00:00",
            "minutes_until": 25,
            "attendees": ["alice@co.com"],
            "event_id": "ev_strat",
        })
        assert len(result["attendee_context"]) == 1
        assert "pricing" in result["attendee_context"][0]["context"]

    @pytest.mark.asyncio
    async def test_imminent_meeting_uses_important_level(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.notify = AsyncMock()

        await handler(ctx, {
            "title": "Quick call",
            "start": "2026-02-16T10:00:00+00:00",
            "minutes_until": 5,
            "attendees": [],
            "event_id": "ev_quick",
        })
        # notify(text, level="important") — level passed as keyword
        assert ctx.notify.call_args[1]["level"] == "important"

    @pytest.mark.asyncio
    async def test_far_meeting_uses_fyi_level(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.notify = AsyncMock()

        await handler(ctx, {
            "title": "Later",
            "start": "2026-02-16T15:00:00+00:00",
            "minutes_until": 25,
            "attendees": [],
            "event_id": "ev_later",
        })
        assert ctx.notify.call_args[1]["level"] == "fyi"

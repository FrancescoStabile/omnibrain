"""
Tests — Morning Briefing Skill handlers.

Verifies:
    - poll.py: generates daily briefing, stores in memory, notifies
    - ask.py: returns cached briefing or searches memory
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from omnibrain.skill_context import SkillContext


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

SKILL_PATH = Path(__file__).parent.parent / "skills" / "morning-briefing"


def _make_ctx(permissions: set[str] | None = None, *, user_name: str = "Test"):
    perms = permissions or {"read_memory", "write_memory", "notify", "llm_access"}
    db = MagicMock()
    db.get_all_preferences.return_value = {}
    config = MagicMock(user_name=user_name, timezone="UTC")
    return SkillContext(skill_name="morning-briefing", permissions=perms, db=db, config=config)


# ═══════════════════════════════════════════════════════════════════════════
# Poll Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefingPoll:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        fn = _load_handler(SKILL_PATH, "handlers/poll.py")
        assert fn is not None, "Could not load morning-briefing poll handler"
        return fn

    @pytest.mark.asyncio
    async def test_skips_if_already_generated_today(self, handler):
        from datetime import date, datetime as dt
        # Determine the briefing type that the handler will compute
        btype = "morning" if dt.now().hour < 14 else "evening"
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            f"last_{btype}_date": date.today().isoformat(),
        }.get(k, d))
        ctx.set_data = AsyncMock()

        result = await handler(ctx)
        assert result.get("status") == "already_generated"

    @pytest.mark.asyncio
    async def test_generates_briefing_with_no_data(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result.get("status") == "generated"
        ctx.memory_store.assert_called_once()
        ctx.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_llm_when_available(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_search = AsyncMock(return_value=[
            {"text": "Email from boss about Q4 goals", "source": "email"},
            {"text": "Meeting at 10am", "source": "calendar"},
        ])
        ctx.has_permission = MagicMock(return_value=True)
        ctx.llm_complete = AsyncMock(return_value="Good morning! Here's your briefing...")
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.notify = AsyncMock()

        result = await handler(ctx)
        assert result["status"] == "generated"
        ctx.llm_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_briefing_text_in_skill_data(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.set_data = AsyncMock()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)
        ctx.memory_store = AsyncMock(return_value="doc_1")
        ctx.notify = AsyncMock()

        await handler(ctx)
        # Should store last_{type}_text and last_{type}_date
        from datetime import datetime as dt
        btype = "morning" if dt.now().hour < 14 else "evening"
        set_calls = {call.args[0] for call in ctx.set_data.call_args_list}
        assert f"last_{btype}_text" in set_calls
        assert f"last_{btype}_date" in set_calls


# ═══════════════════════════════════════════════════════════════════════════
# Ask Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefingAsk:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        fn = _load_handler(SKILL_PATH, "handlers/ask.py")
        assert fn is not None, "Could not load morning-briefing ask handler"
        return fn

    @pytest.mark.asyncio
    async def test_returns_cached_briefing(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "last_morning_text": "Your briefing for today...",
            "last_morning_date": "2025-01-15",
        }.get(k, d))

        result = await handler(ctx, "show me today's briefing")
        assert result["answer"] == "Your briefing for today..."
        assert result["source"] == "cached"

    @pytest.mark.asyncio
    async def test_falls_back_to_memory_search(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.memory_search = AsyncMock(return_value=[
            {
                "text": "Yesterday's briefing content",
                "metadata": {"date": "2025-01-14"},
            },
        ])

        result = await handler(ctx, "briefing")
        assert result["source"] == "memory"

    @pytest.mark.asyncio
    async def test_no_briefing_available(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value=None)
        ctx.memory_search = AsyncMock(return_value=[])

        result = await handler(ctx, "morning briefing")
        assert result["source"] == "none"
        assert "no" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_evening_type_detection(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "last_evening_text": "Evening summary...",
            "last_evening_date": "2025-01-15",
        }.get(k, d))

        result = await handler(ctx, "evening briefing")
        assert result["type"] == "evening"

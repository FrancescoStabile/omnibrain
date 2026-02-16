"""
Tests — Pattern Detector Skill handlers.

Verifies:
    - poll.py: clusters observations, detects patterns, proposes automations
    - ask.py: returns stored patterns, filters by type
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import SkillContext


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

SKILL_PATH = Path(__file__).parent.parent / "skills" / "pattern-detector"


def _make_ctx(permissions: set[str] | None = None):
    perms = permissions or {"read_memory", "write_memory", "notify", "llm_access"}
    db = MagicMock()
    db.get_all_preferences.return_value = {}
    config = MagicMock(user_name="Test", timezone="UTC")
    return SkillContext(skill_name="pattern-detector", permissions=perms, db=db, config=config)


def _fake_entry(text: str = "test", source: str = "email", timestamp: str | None = None):
    return {
        "text": text,
        "source": source,
        "metadata": {"timestamp": timestamp or datetime.now(timezone.utc).isoformat()},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Poll Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternPoll:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        fn = _load_handler(SKILL_PATH, "handlers/poll.py")
        assert fn is not None, "Could not load pattern-detector poll handler"
        return fn

    @pytest.mark.asyncio
    async def test_no_data_returns_no_data(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])

        result = await handler(ctx)
        assert result["status"] == "no_data"
        assert result["patterns"] == 0

    @pytest.mark.asyncio
    async def test_detects_source_frequency_pattern(self, handler):
        entries = [_fake_entry(source="email")] * 5 + [_fake_entry(source="calendar")]
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=entries)
        ctx.get_data = AsyncMock(return_value="[]")
        ctx.set_data = AsyncMock()
        ctx.notify = AsyncMock()
        ctx.propose_action = AsyncMock()

        result = await handler(ctx)
        assert result["status"] == "detected"
        assert result["new_patterns"] >= 1

    @pytest.mark.asyncio
    async def test_skips_known_patterns(self, handler):
        # Create entries that only produce one cluster type (source_frequency:email)
        entries = [_fake_entry(source="email", text="x")] * 5
        # Pre-populate known patterns with ALL possible clusters from these entries.
        # The handler also clusters by time_pattern — suppress by using entries without timestamps.
        bare_entries = [{"text": "x", "source": "email", "metadata": {}} for _ in range(5)]
        known = json.dumps([{
            "id": "source_frequency:email",
            "type": "source_frequency",
            "key": "email",
            "count": 5,
            "description": "Frequent activity from email (5 times)",
            "detected_at": datetime.now().isoformat(),
        }])

        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=bare_entries)
        ctx.get_data = AsyncMock(return_value=known)
        ctx.set_data = AsyncMock()
        ctx.notify = AsyncMock()
        ctx.propose_action = AsyncMock()

        result = await handler(ctx)
        assert result["new_patterns"] == 0

    @pytest.mark.asyncio
    async def test_proposes_automation_for_strong_patterns(self, handler):
        # min_occurrences=3, need ≥6 for proposal
        entries = [_fake_entry(source="slack")] * 8
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=entries)
        ctx.get_data = AsyncMock(return_value="[]")
        ctx.set_data = AsyncMock()
        ctx.notify = AsyncMock()
        ctx.propose_action = AsyncMock()

        result = await handler(ctx)
        assert result["proposals"] >= 1
        ctx.propose_action.assert_called()

    @pytest.mark.asyncio
    async def test_notifies_on_new_patterns(self, handler):
        entries = [_fake_entry(source="github")] * 4
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=entries)
        ctx.get_data = AsyncMock(return_value="[]")
        ctx.set_data = AsyncMock()
        ctx.notify = AsyncMock()
        ctx.propose_action = AsyncMock()

        await handler(ctx)
        ctx.notify.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Ask Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternAsk:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        fn = _load_handler(SKILL_PATH, "handlers/ask.py")
        assert fn is not None, "Could not load pattern-detector ask handler"
        return fn

    @pytest.mark.asyncio
    async def test_no_patterns_returns_not_yet(self, handler):
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(return_value="[]")
        ctx.has_permission = MagicMock(return_value=False)

        result = await handler(ctx, "what patterns have you found?")
        assert "no patterns" in result["answer"].lower() or "not" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_returns_patterns_manual_format(self, handler):
        patterns = json.dumps([
            {"id": "source_frequency:email", "type": "source_frequency",
             "key": "email", "count": 10, "description": "Frequent email activity"},
            {"id": "time_pattern:hour_9", "type": "time_pattern",
             "key": "hour_9", "count": 7, "description": "Morning spike at 9:00"},
        ])
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "known_patterns": patterns,
            "last_detection": "2025-01-15T10:00:00",
        }.get(k, d))
        ctx.has_permission = MagicMock(return_value=False)

        result = await handler(ctx, "show patterns")
        assert result["total"] == 2
        assert len(result["patterns"]) == 2
        assert "Frequent email activity" in result["answer"]

    @pytest.mark.asyncio
    async def test_filters_by_time_pattern(self, handler):
        patterns = json.dumps([
            {"id": "source_frequency:email", "type": "source_frequency",
             "key": "email", "count": 10, "description": "Email freq"},
            {"id": "time_pattern:hour_9", "type": "time_pattern",
             "key": "hour_9", "count": 7, "description": "Morning spike"},
        ])
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "known_patterns": patterns,
            "last_detection": "2025-01-15T10:00:00",
        }.get(k, d))
        ctx.has_permission = MagicMock(return_value=False)

        result = await handler(ctx, "when am I most active?")
        # Should filter to time_pattern types
        types = {p["type"] for p in result["patterns"]}
        assert "time_pattern" in types

    @pytest.mark.asyncio
    async def test_uses_llm_when_available(self, handler):
        patterns = json.dumps([
            {"id": "recurring_topic:python", "type": "recurring_topic",
             "key": "python", "count": 15, "description": "Python topic"},
        ])
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "known_patterns": patterns,
            "last_detection": "2025-01-15T10:00:00",
        }.get(k, d))
        ctx.has_permission = MagicMock(return_value=True)
        ctx.llm_complete = AsyncMock(return_value="You frequently discuss Python...")

        result = await handler(ctx, "what topics come up a lot?")
        assert result["answer"] == "You frequently discuss Python..."

    @pytest.mark.asyncio
    async def test_filters_by_source_keyword(self, handler):
        patterns = json.dumps([
            {"id": "source_frequency:email", "type": "source_frequency",
             "key": "email", "count": 10, "description": "Email freq"},
            {"id": "time_pattern:hour_9", "type": "time_pattern",
             "key": "hour_9", "count": 7, "description": "Morning spike"},
        ])
        ctx = _make_ctx()
        ctx.get_data = AsyncMock(side_effect=lambda k, d=None: {
            "known_patterns": patterns,
            "last_detection": "2025-01-15T10:00:00",
        }.get(k, d))
        ctx.has_permission = MagicMock(return_value=False)

        result = await handler(ctx, "where does most activity come from?")
        types = {p["type"] for p in result["patterns"]}
        assert "source_frequency" in types

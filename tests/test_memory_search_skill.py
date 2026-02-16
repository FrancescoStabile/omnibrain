"""
Tests — Memory Search Skill handler.

Verifies:
    - ask.py: searches memory via FTS5 + KG, composes answer
    - Person/topic parsing
    - LLM composition path + fallback formatting
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import SkillContext


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

SKILL_PATH = Path(__file__).parent.parent / "skills" / "memory-search"


def _make_ctx(permissions: set[str] | None = None):
    perms = permissions or {"read_memory", "llm_access"}
    return SkillContext(skill_name="memory-search", permissions=perms)


def _fake_result(text: str = "Test memory", source: str = "email", score: float = 0.9):
    return {"text": text, "source": source, "score": score, "metadata": {}}


# ═══════════════════════════════════════════════════════════════════════════
# Ask Handler
# ═══════════════════════════════════════════════════════════════════════════


class TestMemorySearchAsk:

    @pytest.fixture
    def handler(self):
        from omnibrain.skill_runtime import _load_handler
        fn = _load_handler(SKILL_PATH, "handlers/ask.py")
        assert fn is not None, "Could not load memory-search ask handler"
        return fn

    @pytest.mark.asyncio
    async def test_no_results_returns_not_found(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.who_said_what = AsyncMock(return_value=[])
        ctx.correlate = AsyncMock(return_value=[])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)

        result = await handler(ctx, "something obscure")
        assert "couldn't find" in result["answer"].lower() or "sources" in result

    @pytest.mark.asyncio
    async def test_returns_results_without_llm(self, handler):
        results = [_fake_result("Meeting notes from Monday"), _fake_result("Email about project")]
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=results)
        ctx.who_said_what = AsyncMock(return_value=[])
        ctx.correlate = AsyncMock(return_value=[])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)

        result = await handler(ctx, "meeting notes")
        assert "answer" in result
        assert "sources" in result

    @pytest.mark.asyncio
    async def test_llm_composition_used_when_available(self, handler):
        results = [_fake_result("Budget report Q3")]
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=results)
        ctx.who_said_what = AsyncMock(return_value=[])
        ctx.correlate = AsyncMock(return_value=[])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=True)
        ctx.llm_complete = AsyncMock(return_value="The Q3 budget report shows...")

        result = await handler(ctx, "budget report")
        assert result["answer"] == "The Q3 budget report shows..."

    @pytest.mark.asyncio
    async def test_person_query_triggers_who_said_what(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.who_said_what = AsyncMock(return_value=[{"text": "Marco said pricing is 50k"}])
        ctx.correlate = AsyncMock(return_value=[])
        ctx.get_contacts = AsyncMock(return_value=[{"name": "Marco", "email": "marco@co.com"}])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)

        result = await handler(ctx, "what did Marco say about pricing")
        ctx.who_said_what.assert_called_once()
        assert "contacts" in result

    @pytest.mark.asyncio
    async def test_correlation_query_triggers_correlate(self, handler):
        ctx = _make_ctx()
        ctx.memory_search = AsyncMock(return_value=[])
        ctx.who_said_what = AsyncMock(return_value=[])
        ctx.correlate = AsyncMock(return_value=[{"summary": "X relates to Y via Z"}])
        ctx.get_contacts = AsyncMock(return_value=[])
        ctx.has_permission = MagicMock(return_value=False)
        ctx.llm_complete = AsyncMock(return_value=None)

        result = await handler(ctx, "connection between sales and marketing")
        ctx.correlate.assert_called_once()
        assert "answer" in result

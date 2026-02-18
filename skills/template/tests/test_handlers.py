"""Tests for skill handlers."""

from __future__ import annotations

import pytest


class TestPollHandler:
    """Tests for the poll handler."""

    @pytest.mark.asyncio
    async def test_poll_returns_ok(self):
        """Poll handler should return status ok."""
        from handlers.poll import handle

        # Create a minimal mock context
        class MockContext:
            async def llm(self, prompt: str) -> str:
                return "mock response"

            def notify(self, message: str) -> None:
                pass

        result = await handle(MockContext())
        assert result["status"] == "ok"


class TestAskHandler:
    """Tests for the ask handler."""

    @pytest.mark.asyncio
    async def test_ask_returns_response(self):
        """Ask handler should return a response."""
        from handlers.ask import handle

        class MockContext:
            async def llm(self, prompt: str) -> str:
                return "mock response"

        result = await handle(MockContext(), "test question")
        assert "response" in result


class TestEventHandler:
    """Tests for the event handler."""

    @pytest.mark.asyncio
    async def test_event_returns_handled(self):
        """Event handler should return status handled."""
        from handlers.event import handle

        class MockContext:
            def notify(self, message: str) -> None:
                pass

        result = await handle(MockContext(), {"type": "test", "data": {}})
        assert result["status"] == "handled"

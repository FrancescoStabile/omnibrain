"""
Tests for Skill Context — the sandboxed interface between Skills and Core.

Groups:
    Permissions   — permission checking and denial
    Memory        — memory_search, memory_store
    Notifications — notify, propose_action
    LocalStorage  — get_data, set_data, delete_data
    LLM           — llm_complete placeholder
    EventBus      — emit, subscribe, unsubscribe
    Properties    — user_name, user_preferences, user_timezone
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnibrain.skill_context import EventBus, NotifyLevel, PermissionDeniedError, SkillContext
from omnibrain.db import OmniBrainDB


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh OmniBrainDB in a temp directory."""
    return OmniBrainDB(tmp_path)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def full_ctx(tmp_db, event_bus):
    """SkillContext with all permissions."""
    return SkillContext(
        skill_name="test-skill",
        permissions={
            "read_memory", "write_memory", "notify", "propose_action",
            "llm_access", "read_profile", "skill_storage",
        },
        db=tmp_db,
        event_bus=event_bus,
    )


@pytest.fixture
def readonly_ctx(tmp_db, event_bus):
    """SkillContext with only read_memory."""
    return SkillContext(
        skill_name="readonly-skill",
        permissions={"read_memory"},
        db=tmp_db,
        event_bus=event_bus,
    )


@pytest.fixture
def empty_ctx():
    """SkillContext with no permissions and no services."""
    return SkillContext(
        skill_name="bare-skill",
        permissions=set(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Permission Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPermissions:
    def test_has_permission_true(self, full_ctx):
        assert full_ctx.has_permission("read_memory") is True

    def test_has_permission_false(self, full_ctx):
        assert full_ctx.has_permission("google_gmail") is False

    def test_require_raises(self, empty_ctx):
        with pytest.raises(PermissionDeniedError, match="bare-skill"):
            empty_ctx._require("read_memory")

    def test_require_passes(self, full_ctx):
        full_ctx._require("read_memory")  # Should not raise

    @pytest.mark.asyncio
    async def test_memory_search_denied(self, empty_ctx):
        with pytest.raises(PermissionDeniedError):
            await empty_ctx.memory_search("hello")

    @pytest.mark.asyncio
    async def test_memory_store_denied(self, readonly_ctx):
        with pytest.raises(PermissionDeniedError):
            await readonly_ctx.memory_store("data")

    @pytest.mark.asyncio
    async def test_notify_denied(self, readonly_ctx):
        with pytest.raises(PermissionDeniedError):
            await readonly_ctx.notify("message")

    @pytest.mark.asyncio
    async def test_llm_denied(self, empty_ctx):
        with pytest.raises(PermissionDeniedError):
            await empty_ctx.llm_complete("prompt")

    def test_permissions_are_frozen(self, full_ctx):
        assert isinstance(full_ctx.permissions, frozenset)


# ═══════════════════════════════════════════════════════════════════════════
# Memory Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMemory:
    @pytest.mark.asyncio
    async def test_search_no_memory_returns_empty(self, empty_ctx):
        """With no memory backend, search returns []."""
        ctx = SkillContext(
            skill_name="t", permissions={"read_memory"}
        )
        result = await ctx.memory_search("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_store_no_memory_returns_empty(self):
        ctx = SkillContext(
            skill_name="t", permissions={"write_memory"}
        )
        result = await ctx.memory_store("stuff")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════
# Notification Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifications:
    @pytest.mark.asyncio
    async def test_notify_emits_event(self, full_ctx, event_bus):
        received = []

        async def listener(event_type, data):
            received.append(data)

        event_bus.subscribe("notification", listener)
        await full_ctx.notify("test message", level="important")
        assert len(received) == 1
        assert received[0]["skill"] == "test-skill"
        assert received[0]["message"] == "test message"
        assert received[0]["level"] == "important"

    @pytest.mark.asyncio
    async def test_propose_action(self, full_ctx, tmp_db):
        pid = await full_ctx.propose_action(
            type="email_draft",
            title="Send report",
            description="Weekly report to Marco",
            priority=3,
        )
        assert pid > 0
        proposals = tmp_db.get_pending_proposals()
        assert len(proposals) >= 1
        found = [p for p in proposals if p["id"] == pid]
        assert found[0]["title"] == "[test-skill] Send report"

    @pytest.mark.asyncio
    async def test_propose_action_no_db(self, empty_ctx):
        ctx = SkillContext(skill_name="t", permissions={"notify", "propose_action"})
        result = await ctx.propose_action("t", "t", "d")
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# Skill-Local Storage Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalStorage:
    @pytest.mark.asyncio
    async def test_set_and_get(self, full_ctx):
        await full_ctx.set_data("counter", 42)
        val = await full_ctx.get_data("counter")
        assert val == 42

    @pytest.mark.asyncio
    async def test_get_default(self, full_ctx):
        val = await full_ctx.get_data("nonexistent", "fallback")
        assert val == "fallback"

    @pytest.mark.asyncio
    async def test_delete(self, full_ctx):
        await full_ctx.set_data("temp", "value")
        await full_ctx.delete_data("temp")
        val = await full_ctx.get_data("temp")
        assert val is None

    @pytest.mark.asyncio
    async def test_no_db_returns_default(self):
        ctx = SkillContext(skill_name="t", permissions={"skill_storage"})
        val = await ctx.get_data("key", "default")
        assert val == "default"

    @pytest.mark.asyncio
    async def test_isolation_between_skills(self, tmp_db, event_bus):
        """Data written by skill A should not be accessible by skill B."""
        ctx_a = SkillContext(
            skill_name="skill-a", permissions={"skill_storage"},
            db=tmp_db, event_bus=event_bus,
        )
        ctx_b = SkillContext(
            skill_name="skill-b", permissions={"skill_storage"},
            db=tmp_db, event_bus=event_bus,
        )
        await ctx_a.set_data("secret", "a-value")
        val = await ctx_b.get_data("secret")
        assert val is None  # skill-b can't see skill-a's data


# ═══════════════════════════════════════════════════════════════════════════
# LLM Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLLM:
    @pytest.mark.asyncio
    async def test_llm_complete_placeholder(self, full_ctx):
        """Placeholder returns empty string (no router wired yet)."""
        result = await full_ctx.llm_complete("test prompt")
        assert result == ""

    @pytest.mark.asyncio
    async def test_llm_stream_placeholder(self, full_ctx):
        chunks = []
        async for chunk in full_ctx.llm_stream("test"):
            chunks.append(chunk)
        assert chunks == [""]


# ═══════════════════════════════════════════════════════════════════════════
# EventBus Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self, event_bus):
        received = []

        async def cb(et, data):
            received.append((et, data))

        event_bus.subscribe("test_event", cb)
        await event_bus.emit("test_event", {"value": 1})
        assert len(received) == 1
        assert received[0][0] == "test_event"

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus):
        received = []

        async def cb(et, data):
            received.append(data)

        event_bus.subscribe("ev", cb)
        event_bus.unsubscribe("ev", cb)
        await event_bus.emit("ev", {})
        assert received == []

    @pytest.mark.asyncio
    async def test_multiple_listeners(self, event_bus):
        count = {"a": 0, "b": 0}

        async def cb_a(et, data):
            count["a"] += 1

        async def cb_b(et, data):
            count["b"] += 1

        event_bus.subscribe("ev", cb_a)
        event_bus.subscribe("ev", cb_b)
        await event_bus.emit("ev", {})
        assert count["a"] == 1
        assert count["b"] == 1

    @pytest.mark.asyncio
    async def test_listener_error_isolated(self, event_bus):
        """A failing listener should not prevent others from running."""
        called = []

        async def bad_cb(et, data):
            raise ValueError("oops")

        async def good_cb(et, data):
            called.append(True)

        event_bus.subscribe("ev", bad_cb)
        event_bus.subscribe("ev", good_cb)
        await event_bus.emit("ev", {})
        assert called == [True]

    def test_listener_count(self, event_bus):
        async def cb(et, data): ...
        event_bus.subscribe("a", cb)
        event_bus.subscribe("b", cb)
        assert event_bus.listener_count == 2

    @pytest.mark.asyncio
    async def test_emit_event_from_context(self, full_ctx, event_bus):
        received = []

        async def cb(et, data):
            received.append(data)

        event_bus.subscribe("custom", cb)
        await full_ctx.emit_event("custom", {"payload": 123})
        assert received[0]["skill"] == "test-skill"
        assert received[0]["payload"] == 123


# ═══════════════════════════════════════════════════════════════════════════
# User Properties
# ═══════════════════════════════════════════════════════════════════════════


class TestUserProperties:
    def test_defaults_without_config(self, empty_ctx):
        assert empty_ctx.user_name == "User"
        assert empty_ctx.user_timezone == "UTC"

    def test_preferences_without_db(self, empty_ctx):
        with pytest.raises(PermissionDeniedError):
            _ = empty_ctx.user_preferences

    def test_preferences_from_db(self, full_ctx, tmp_db):
        tmp_db.set_preference("theme", "dark")
        prefs = full_ctx.user_preferences
        assert prefs.get("theme") == "dark"


# ═══════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════


class TestSkillLogging:
    def test_log_appends_to_buffer(self, full_ctx):
        full_ctx.log("step 1")
        full_ctx.log("step 2", level="warning")
        assert len(full_ctx._log_buffer) == 2
        assert full_ctx._log_buffer[0]["skill"] == "test-skill"
        assert full_ctx._log_buffer[1]["level"] == "warning"


# ═══════════════════════════════════════════════════════════════════════════
# NotifyLevel constants
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifyLevelConstants:
    def test_values(self):
        assert NotifyLevel.SILENT == "silent"
        assert NotifyLevel.FYI == "fyi"
        assert NotifyLevel.IMPORTANT == "important"
        assert NotifyLevel.CRITICAL == "critical"

"""
Tests for daemon wiring — verify that the daemon properly integrates
EventBus, SkillRuntime, ProactiveEngine, API server, and Telegram bot.

These are unit-level tests that mock external services to verify the
wiring is correct without needing real credentials.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnibrain.daemon import OmniBrainDaemon
from omnibrain.config import OmniBrainConfig
from omnibrain.skill_context import EventBus


# ═══════════════════════════════════════════════════════════════════════════
# Initialisation
# ═══════════════════════════════════════════════════════════════════════════


class TestDaemonInit:
    def test_has_event_bus(self):
        d = OmniBrainDaemon()
        assert isinstance(d._event_bus, EventBus)

    def test_has_skill_runtime_none_before_run(self):
        d = OmniBrainDaemon()
        assert d._skill_runtime is None

    def test_has_proactive_engine_none_before_run(self):
        d = OmniBrainDaemon()
        assert d._proactive_engine is None

    def test_custom_config(self, tmp_path):
        cfg = OmniBrainConfig()
        d = OmniBrainDaemon(config=cfg)
        assert d.config is cfg

    def test_tasks_empty_before_run(self):
        d = OmniBrainDaemon()
        assert d._tasks == []


# ═══════════════════════════════════════════════════════════════════════════
# Task creation
# ═══════════════════════════════════════════════════════════════════════════


class TestTaskCreation:
    @pytest.mark.asyncio
    async def test_run_creates_seven_tasks(self, tmp_path):
        """The daemon should create exactly 7 tasks."""
        cfg = OmniBrainConfig()
        # Override data dir so DB goes to tmp_path
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)

        # Immediately cancel after tasks are created
        async def cancel_fast():
            await asyncio.sleep(0.05)
            d._running = False
            for t in d._tasks:
                if not t.done():
                    t.cancel()

        # Mock everything that talks to external services
        with (
            patch.object(d, "_collector_loop", new_callable=AsyncMock),
            patch.object(d, "_proactive_loop", new_callable=AsyncMock),
            patch.object(d, "_telegram_bot", new_callable=AsyncMock),
            patch.object(d, "_api_server", new_callable=AsyncMock),
            patch.object(d, "_skill_runtime_loop", new_callable=AsyncMock),
            patch.object(d, "_cleanup_loop", new_callable=AsyncMock),
            patch.object(d, "_heartbeat_loop", new_callable=AsyncMock),
            patch.object(d, "_setup_logging"),
            patch.object(d, "_setup_signals"),
            patch.object(d, "_print_banner"),
        ):
            cancel_task = asyncio.create_task(cancel_fast())
            try:
                await asyncio.wait_for(d.run(), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            await cancel_task

            assert len(d._tasks) == 7
            task_names = {t.get_name() for t in d._tasks}
            assert task_names == {
                "heartbeat",
                "collector",
                "proactive",
                "cleanup",
                "skill_runtime",
                "api",
                "telegram",
            }


# ═══════════════════════════════════════════════════════════════════════════
# Skill runtime loop
# ═══════════════════════════════════════════════════════════════════════════


class TestSkillRuntimeLoop:
    @pytest.mark.asyncio
    async def test_skill_runtime_loop_discovers_skills(self, tmp_path):
        """_skill_runtime_loop should create a SkillRuntime and call discover."""
        cfg = OmniBrainConfig()
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)
        d.db = MagicMock()

        mock_runtime = MagicMock()
        mock_runtime.discover = MagicMock(return_value=[])
        mock_runtime.run = AsyncMock()

        with patch(
            "omnibrain.skill_runtime.SkillRuntime",
            return_value=mock_runtime,
        ) as mock_cls:
            # Cancel quickly
            async def cancel():
                await asyncio.sleep(0.05)
                mock_runtime.run.side_effect = asyncio.CancelledError()

            task = asyncio.create_task(cancel())
            try:
                await d._skill_runtime_loop()
            except asyncio.CancelledError:
                pass
            await task

            mock_cls.assert_called_once()
            mock_runtime.discover.assert_called_once()
            # The dirs argument should be a list of 2 directories
            call_args = mock_runtime.discover.call_args
            assert len(call_args[0][0]) == 2

    @pytest.mark.asyncio
    async def test_skill_runtime_loop_uses_event_bus(self, tmp_path):
        """_skill_runtime_loop should pass the daemon's event bus."""
        cfg = OmniBrainConfig()
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)
        d.db = MagicMock()

        mock_runtime = MagicMock()
        mock_runtime.discover = MagicMock(return_value=[])
        mock_runtime.run = AsyncMock()
        mock_runtime.stop = AsyncMock()

        with patch(
            "omnibrain.skill_runtime.SkillRuntime",
            return_value=mock_runtime,
        ) as mock_cls:
            mock_runtime.run.side_effect = asyncio.CancelledError()
            try:
                await d._skill_runtime_loop()
            except asyncio.CancelledError:
                pass

            kwargs = mock_cls.call_args.kwargs
            assert kwargs["event_bus"] is d._event_bus


# ═══════════════════════════════════════════════════════════════════════════
# Proactive loop
# ═══════════════════════════════════════════════════════════════════════════


class TestProactiveLoop:
    @pytest.mark.asyncio
    async def test_proactive_loop_creates_engine(self, tmp_path):
        """_proactive_loop should create the ProactiveEngine and register defaults."""
        cfg = OmniBrainConfig()
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)
        d.db = MagicMock()

        mock_engine = MagicMock()
        mock_engine.register_defaults = MagicMock()
        mock_engine.run = AsyncMock(side_effect=asyncio.CancelledError())
        mock_engine.stop = AsyncMock()
        mock_engine.tasks = []

        with (
            patch("omnibrain.memory.MemoryManager", return_value=MagicMock()),
            patch("omnibrain.briefing.BriefingGenerator", return_value=MagicMock()),
            patch("omnibrain.proactive.engine.ProactiveEngine", return_value=mock_engine),
        ):
            try:
                await d._proactive_loop()
            except asyncio.CancelledError:
                pass

            assert d._proactive_engine is mock_engine
            mock_engine.register_defaults.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Telegram bot
# ═══════════════════════════════════════════════════════════════════════════


class TestTelegramBot:
    @pytest.mark.asyncio
    async def test_telegram_disabled_without_config(self, tmp_path):
        """If telegram is not configured, the bot should not start."""
        cfg = OmniBrainConfig()
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)
        # has_telegram() → False by default (no token set)
        await d._telegram_bot()  # Should return immediately, no error


# ═══════════════════════════════════════════════════════════════════════════
# API server
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIServer:
    @pytest.mark.asyncio
    async def test_api_server_creates_uvicorn(self, tmp_path):
        """_api_server should create an OmniBrainAPIServer and run uvicorn."""
        cfg = OmniBrainConfig()
        cfg._data_dir = tmp_path
        d = OmniBrainDaemon(config=cfg)
        d.db = MagicMock()

        mock_server = MagicMock()
        mock_server.app = MagicMock()

        mock_uvi_server = MagicMock()
        mock_uvi_server.serve = AsyncMock(side_effect=asyncio.CancelledError())

        with (
            patch("omnibrain.interfaces.api_server.OmniBrainAPIServer", return_value=mock_server) as mock_api_cls,
            patch("uvicorn.Config", return_value=MagicMock()) as mock_uvi_config,
            patch("uvicorn.Server", return_value=mock_uvi_server),
            patch("omnibrain.memory.MemoryManager", return_value=MagicMock()),
            patch("omnibrain.briefing.BriefingGenerator", return_value=MagicMock()),
        ):
            try:
                await d._api_server()
            except asyncio.CancelledError:
                pass

            mock_api_cls.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Shutdown
# ═══════════════════════════════════════════════════════════════════════════


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self):
        d = OmniBrainDaemon()
        d._running = True

        t1 = asyncio.create_task(asyncio.sleep(999))
        t1.set_name("test1")
        t2 = asyncio.create_task(asyncio.sleep(999))
        t2.set_name("test2")
        d._tasks = [t1, t2]

        await d._shutdown()

        assert d._running is False
        assert t1.cancelled() or t1.done()
        assert t2.cancelled() or t2.done()

    def test_uptime_format(self):
        from datetime import datetime, timedelta

        d = OmniBrainDaemon()
        d._start_time = datetime.now() - timedelta(hours=2, minutes=15)
        uptime = d._get_uptime()
        assert "2h" in uptime
        assert "15m" in uptime

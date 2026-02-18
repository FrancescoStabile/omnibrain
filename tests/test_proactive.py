"""
Tests for OmniBrain Proactive Engine (Day 13-14).

Groups:
    NotificationLevel — Notification constants
    ScheduledTask     — Task scheduling logic
    ProactiveEngine   — Engine lifecycle, task execution
    DefaultTasks      — check_emails, check_calendar, briefing, patterns
    Integration       — End-to-end flows
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

from omnibrain.proactive import (
    NotificationLevel,
    ProactiveEngine,
    ScheduledTask,
)
from omnibrain.briefing import BriefingGenerator
from omnibrain.db import OmniBrainDB
from omnibrain.models import Observation


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
def engine(db):
    return ProactiveEngine(db)


@pytest.fixture
def briefing_gen(db):
    return BriefingGenerator(db)


# ═══════════════════════════════════════════════════════════════════════════
# Notification Level Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationLevel:
    def test_levels(self):
        assert NotificationLevel.SILENT == "silent"
        assert NotificationLevel.FYI == "fyi"
        assert NotificationLevel.IMPORTANT == "important"
        assert NotificationLevel.CRITICAL == "critical"


# ═══════════════════════════════════════════════════════════════════════════
# ScheduledTask Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestScheduledTask:
    def test_interval_task_creation(self):
        task = ScheduledTask(
            name="test",
            handler=AsyncMock(),
            interval_seconds=300,
        )
        assert task.name == "test"
        assert task.is_interval_task is True
        assert task.is_daily_task is False
        assert task.is_weekly_task is False
        assert task.run_count == 0
        assert task.error_count == 0

    def test_daily_task_creation(self):
        task = ScheduledTask(
            name="morning",
            handler=AsyncMock(),
            run_at_time="07:00",
        )
        assert task.is_interval_task is False
        assert task.is_daily_task is True
        assert task.is_weekly_task is False

    def test_weekly_task_creation(self):
        task = ScheduledTask(
            name="weekly",
            handler=AsyncMock(),
            run_at_time="08:00",
            run_on_day="monday",
        )
        assert task.is_interval_task is False
        assert task.is_daily_task is False
        assert task.is_weekly_task is True

    def test_should_run_interval_first_time(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), interval_seconds=60)
        assert task.should_run(datetime.now()) is True

    def test_should_run_interval_not_elapsed(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), interval_seconds=60)
        task.last_run = datetime.now()
        assert task.should_run(datetime.now()) is False

    def test_should_run_interval_elapsed(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), interval_seconds=60)
        task.last_run = datetime.now() - timedelta(seconds=120)
        assert task.should_run(datetime.now()) is True

    def test_should_run_disabled(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), interval_seconds=60, enabled=False)
        assert task.should_run(datetime.now()) is False

    def test_should_run_daily_not_yet_time(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), run_at_time="23:59")
        now = datetime.now().replace(hour=6, minute=0)
        assert task.should_run(now) is False

    def test_should_run_daily_past_time(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), run_at_time="06:00")
        now = datetime.now().replace(hour=10, minute=0)
        assert task.should_run(now) is True

    def test_should_run_daily_already_ran_today(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), run_at_time="06:00")
        task.last_run = datetime.now()
        assert task.should_run(datetime.now()) is False

    def test_should_run_weekly_wrong_day(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), run_at_time="08:00", run_on_day="monday")
        # Force a day that's not Monday
        now = datetime(2024, 1, 17, 10, 0)  # Wednesday
        assert task.should_run(now) is False

    def test_should_run_weekly_correct_day(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), run_at_time="08:00", run_on_day="monday")
        now = datetime(2024, 1, 15, 10, 0)  # Monday
        assert task.should_run(now) is True

    def test_to_dict(self):
        task = ScheduledTask(name="t", handler=AsyncMock(), interval_seconds=300)
        d = task.to_dict()
        assert d["name"] == "t"
        assert d["interval_seconds"] == 300
        assert d["run_count"] == 0
        assert d["enabled"] is True


# ═══════════════════════════════════════════════════════════════════════════
# ProactiveEngine Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestProactiveEngine:
    def test_creation(self, engine):
        assert engine.running is False
        assert len(engine.tasks) == 0

    def test_register_task(self, engine):
        task = ScheduledTask(name="test", handler=AsyncMock(), interval_seconds=60)
        engine.register_task(task)
        assert len(engine.tasks) == 1
        assert engine.tasks[0].name == "test"

    def test_register_defaults(self, engine, briefing_gen):
        engine.register_defaults(briefing_generator=briefing_gen)
        assert len(engine.tasks) == 7
        names = [t.name for t in engine.tasks]
        assert "check_emails" in names
        assert "check_calendar" in names
        assert "detect_patterns" in names
        assert "check_dormant_projects" in names
        assert "morning_briefing" in names
        assert "evening_summary" in names
        assert "weekly_review" in names

    def test_get_status(self, engine):
        status = engine.get_status()
        assert status["running"] is False
        assert status["task_count"] == 0
        assert status["tasks"] == []

    def test_get_status_with_tasks(self, engine, briefing_gen):
        engine.register_defaults(briefing_generator=briefing_gen)
        status = engine.get_status()
        assert status["task_count"] == 7

    @pytest.mark.asyncio
    async def test_run_task_by_name(self, engine):
        handler = AsyncMock()
        task = ScheduledTask(name="manual_test", handler=handler, interval_seconds=9999)
        engine.register_task(task)

        found = await engine.run_task_by_name("manual_test")
        assert found is True
        handler.assert_called_once()
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_run_task_by_name_not_found(self, engine):
        found = await engine.run_task_by_name("nonexistent")
        assert found is False

    @pytest.mark.asyncio
    async def test_execute_task_increments_count(self, engine):
        handler = AsyncMock()
        task = ScheduledTask(name="test", handler=handler, interval_seconds=60)
        await engine._execute_task(task)
        assert task.run_count == 1
        assert task.last_run is not None

    @pytest.mark.asyncio
    async def test_execute_task_error_handling(self, engine):
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        task = ScheduledTask(name="fail", handler=handler, interval_seconds=60)
        await engine._execute_task(task)
        assert task.error_count == 1
        assert task.last_error == "boom"
        assert task.run_count == 0  # Failed, not counted

    def test_notify_callback(self, engine):
        notifications = []
        engine.set_notify_callback(lambda lvl, title, msg: notifications.append((lvl, title, msg)))
        engine._notify("important", "Test", "Hello")
        assert len(notifications) == 1
        assert notifications[0] == ("important", "Test", "Hello")

    def test_notify_no_callback(self, engine):
        # Should not crash without callback
        engine._notify("important", "Test", "Hello")

    @pytest.mark.asyncio
    async def test_tick_runs_due_tasks(self, engine):
        handler = AsyncMock()
        task = ScheduledTask(name="due", handler=handler, interval_seconds=0)
        engine.register_task(task)
        await engine._tick()
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_skips_not_due(self, engine):
        handler = AsyncMock()
        task = ScheduledTask(name="nope", handler=handler, interval_seconds=9999)
        task.last_run = datetime.now()
        engine.register_task(task)
        await engine._tick()
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop(self, engine):
        engine._running = True
        await engine.stop()
        assert engine.running is False


# ═══════════════════════════════════════════════════════════════════════════
# Default Task Handler Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckEmails:
    @pytest.mark.asyncio
    async def test_processes_unread_events(self, db):
        # Add unprocessed email events
        db.insert_event(
            source="gmail", event_type="email", title="Urgent email",
            metadata={"urgency": "high"},
        )
        db.insert_event(
            source="gmail", event_type="email", title="Normal email",
            metadata={"urgency": "low"},
        )

        engine = ProactiveEngine(db)
        engine.register_defaults()
        notifications = []
        engine.set_notify_callback(lambda *a: notifications.append(a))

        await engine._check_emails()
        assert len(notifications) == 1
        assert "urgent" in notifications[0][1].lower() or "urgent" in notifications[0][2].lower()

    @pytest.mark.asyncio
    async def test_no_emails(self, engine):
        engine.register_defaults()
        # Should not crash with empty DB
        await engine._check_emails()


class TestCheckCalendar:
    @pytest.mark.asyncio
    async def test_upcoming_meeting_notification(self, db):
        now = datetime.now()
        start = now + timedelta(minutes=30)
        end = start + timedelta(hours=1)

        db.insert_event(
            source="calendar", event_type="calendar", title="Big Meeting",
            metadata={
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "attendees": json.dumps(["a@t.com", "b@t.com", "c@t.com"]),
            },
        )

        engine = ProactiveEngine(db)
        engine.register_defaults()
        notifications = []
        engine.set_notify_callback(lambda *a: notifications.append(a))

        await engine._check_calendar()
        assert len(notifications) == 1
        assert "Big Meeting" in notifications[0][2]

    @pytest.mark.asyncio
    async def test_no_upcoming_meetings(self, engine):
        engine.register_defaults()
        await engine._check_calendar()  # Should not crash


class TestMorningBriefing:
    @pytest.mark.asyncio
    async def test_generates_briefing(self, db):
        engine = ProactiveEngine(db)
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)
        notifications = []
        engine.set_notify_callback(lambda *a: notifications.append(a))

        await engine._morning_briefing()
        assert len(notifications) == 1
        assert "Morning" in notifications[0][1]

        # Check stored in DB
        stored = db.get_latest_briefing("morning")
        assert stored is not None

    @pytest.mark.asyncio
    async def test_no_generator(self, engine):
        engine.register_defaults()
        # No briefing_gen, should not crash
        await engine._morning_briefing()


class TestDetectPatterns:
    @pytest.mark.asyncio
    async def test_detects_pattern(self, db):
        # Insert 3+ observations of same type with high confidence
        for i in range(4):
            db.insert_observation(Observation(
                type="communication",
                detail=f"User responds fast to VIPs (occurrence {i})",
                confidence=0.85,
            ))

        engine = ProactiveEngine(db)
        engine.register_defaults()
        notifications = []
        engine.set_notify_callback(lambda *a: notifications.append(a))

        await engine._detect_patterns()
        assert len(notifications) >= 1
        assert "communication" in notifications[0][2].lower()

    @pytest.mark.asyncio
    async def test_no_patterns(self, engine):
        engine.register_defaults()
        await engine._detect_patterns()  # Should not crash

    @pytest.mark.asyncio
    async def test_low_confidence_not_promoted(self, db):
        for i in range(3):
            db.insert_observation(Observation(
                type="test_weak",
                detail=f"Weak observation {i}",
                confidence=0.3,
            ))

        engine = ProactiveEngine(db)
        engine.register_defaults()
        notifications = []
        engine.set_notify_callback(lambda *a: notifications.append(a))

        await engine._detect_patterns()
        # Low confidence should not trigger notification
        pattern_notifications = [n for n in notifications if "test_weak" in n[2]]
        assert len(pattern_notifications) == 0


class TestEveningSummary:
    @pytest.mark.asyncio
    async def test_generates_evening(self, db):
        engine = ProactiveEngine(db)
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)

        await engine._evening_summary()
        stored = db.get_latest_briefing("evening")
        assert stored is not None


class TestWeeklyReview:
    @pytest.mark.asyncio
    async def test_generates_weekly(self, db):
        engine = ProactiveEngine(db)
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)

        await engine._weekly_review()
        stored = db.get_latest_briefing("weekly")
        assert stored is not None


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_engine_tick(self, db):
        """Register defaults, tick once, verify tasks ran."""
        engine = ProactiveEngine(db)
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)

        # Force all interval tasks to be "due"
        for task in engine.tasks:
            if task.is_interval_task:
                task.last_run = None

        await engine._tick()

        # All interval tasks should have run
        for task in engine.tasks:
            if task.is_interval_task:
                assert task.run_count >= 1, f"{task.name} didn't run"

    @pytest.mark.asyncio
    async def test_status_updates_after_run(self, db):
        engine = ProactiveEngine(db)
        handler = AsyncMock()
        engine.register_task(ScheduledTask(name="test", handler=handler, interval_seconds=0))

        await engine._tick()

        status = engine.get_status()
        assert status["tasks"][0]["run_count"] == 1
        assert status["tasks"][0]["last_run"] is not None

    @pytest.mark.asyncio
    async def test_error_recovery(self, db):
        """Engine continues after task failure."""
        engine = ProactiveEngine(db)
        fail_handler = AsyncMock(side_effect=RuntimeError("boom"))
        pass_handler = AsyncMock()

        engine.register_task(ScheduledTask(name="fail", handler=fail_handler, interval_seconds=0))
        engine.register_task(ScheduledTask(name="pass", handler=pass_handler, interval_seconds=0))

        await engine._tick()

        # Both should have been attempted
        fail_handler.assert_called_once()
        pass_handler.assert_called_once()

        # First failed, second succeeded
        assert engine.tasks[0].error_count == 1
        assert engine.tasks[1].run_count == 1

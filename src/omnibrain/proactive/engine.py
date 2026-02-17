"""
OmniBrain — Proactive Engine

The engine that makes OmniBrain proactive: runs scheduled tasks,
observes context, proposes actions — all without user prompting.

Architecture (from manifesto Section 10):
    ProactiveEngine
    ├── check_emails()        — every N minutes
    ├── check_calendar()      — every N minutes
    ├── morning_briefing()    — daily at configured time
    ├── evening_summary()     — daily at configured time
    ├── detect_patterns()     — hourly
    └── weekly_review()       — weekly

Each task:
    1. Gathers context from DB + integrations
    2. Calls BriefingGenerator or individual tools
    3. Stores results/proposals in DB
    4. Emits notifications if needed

The engine uses asyncio tasks with simple sleep-based scheduling.
APScheduler integration is optional and added in Phase 2.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine

from omnibrain.briefing import BriefingGenerator
from omnibrain.models import BriefingType, Observation

logger = logging.getLogger("omnibrain.proactive")


# ═══════════════════════════════════════════════════════════════════════════
# Notification Levels
# ═══════════════════════════════════════════════════════════════════════════


class NotificationLevel:
    """Notification urgency levels from manifesto Section 10."""
    SILENT = "silent"       # Stored only, no notification
    FYI = "fyi"             # Batched into next briefing
    IMPORTANT = "important" # Immediate, non-intrusive
    CRITICAL = "critical"   # Immediate, persistent


# ═══════════════════════════════════════════════════════════════════════════
# Scheduled Task
# ═══════════════════════════════════════════════════════════════════════════


class ScheduledTask:
    """A single scheduled task in the proactive engine."""

    def __init__(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        interval_seconds: int = 300,
        run_at_time: str = "",
        run_on_day: str = "",
        enabled: bool = True,
    ):
        self.name = name
        self.handler = handler
        self.interval_seconds = interval_seconds
        self.run_at_time = run_at_time       # "HH:MM" for daily tasks
        self.run_on_day = run_on_day          # "monday" for weekly tasks
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.run_count: int = 0
        self.error_count: int = 0
        self.last_error: str = ""

    @property
    def is_interval_task(self) -> bool:
        return not self.run_at_time

    @property
    def is_daily_task(self) -> bool:
        return bool(self.run_at_time) and not self.run_on_day

    @property
    def is_weekly_task(self) -> bool:
        return bool(self.run_at_time) and bool(self.run_on_day)

    def should_run(self, now: datetime) -> bool:
        """Check if this task should run now."""
        if not self.enabled:
            return False

        if self.is_interval_task:
            if self.last_run is None:
                return True
            elapsed = (now - self.last_run).total_seconds()
            return elapsed >= self.interval_seconds

        if self.is_daily_task:
            if self.last_run and self.last_run.date() == now.date():
                return False  # Already ran today
            try:
                h, m = self.run_at_time.split(":")
                target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                return now >= target
            except (ValueError, TypeError):
                return False

        if self.is_weekly_task:
            if self.last_run and self.last_run.isocalendar()[1] == now.isocalendar()[1] and self.last_run.year == now.year:
                return False  # Already ran this ISO week
            current_day = now.strftime("%A").lower()
            if current_day != self.run_on_day.lower():
                return False
            try:
                h, m = self.run_at_time.split(":")
                target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                return now >= target
            except (ValueError, TypeError):
                return False

        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "run_at_time": self.run_at_time,
            "run_on_day": self.run_on_day,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Proactive Engine
# ═══════════════════════════════════════════════════════════════════════════


class ProactiveEngine:
    """Runs proactive tasks on schedule.

    Usage:
        engine = ProactiveEngine(db, config)
        engine.register_defaults(briefing_gen, memory_mgr)
        await engine.run()   # Runs forever
    """

    def __init__(self, db: Any, config: Any = None):
        self._db = db
        self._config = config
        self._tasks: list[ScheduledTask] = []
        self._running = False
        self._tick_interval = 30  # Check every 30 seconds
        self._notify_callback: Callable[[str, str, str], None] | None = None
        self._briefing_gen: BriefingGenerator | None = None
        self._review_engine: Any = None
        self._pattern_detector: Any = None
        self._memory: Any = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def tasks(self) -> list[ScheduledTask]:
        return list(self._tasks)

    def register_task(self, task: ScheduledTask) -> None:
        """Register a scheduled task."""
        self._tasks.append(task)
        logger.info(f"Registered proactive task: {task.name}")

    def set_notify_callback(self, callback: Callable[[str, str, str], None]) -> None:
        """Set notification callback: callback(level, title, message)."""
        self._notify_callback = callback

    def register_defaults(
        self,
        briefing_generator: BriefingGenerator | None = None,
        memory_manager: Any = None,
        review_engine: Any = None,
        pattern_detector: Any = None,
        check_interval_minutes: int = 5,
        briefing_time: str = "07:00",
        evening_time: str = "22:00",
        weekly_day: str = "monday",
        weekly_time: str = "08:00",
    ) -> None:
        """Register all default proactive tasks from manifesto.

        Args:
            briefing_generator: BriefingGenerator instance.
            memory_manager: MemoryManager instance.
            review_engine: ReviewEngine for evening/weekly summaries.
            pattern_detector: PatternDetector for pattern detection.
            check_interval_minutes: How often to check emails/calendar.
            briefing_time: Morning briefing time (HH:MM).
            evening_time: Evening summary time (HH:MM).
            weekly_day: Day for weekly review.
            weekly_time: Time for weekly review (HH:MM).
        """
        self._briefing_gen = briefing_generator
        self._memory = memory_manager
        self._review_engine = review_engine
        self._pattern_detector = pattern_detector

        # Interval tasks
        self.register_task(ScheduledTask(
            name="check_emails",
            handler=self._check_emails,
            interval_seconds=check_interval_minutes * 60,
        ))
        self.register_task(ScheduledTask(
            name="check_calendar",
            handler=self._check_calendar,
            interval_seconds=check_interval_minutes * 60 * 3,  # 3x email interval
        ))
        self.register_task(ScheduledTask(
            name="detect_patterns",
            handler=self._detect_patterns,
            interval_seconds=3600,  # hourly
        ))

        # Daily tasks
        self.register_task(ScheduledTask(
            name="morning_briefing",
            handler=self._morning_briefing,
            run_at_time=briefing_time,
        ))
        self.register_task(ScheduledTask(
            name="evening_summary",
            handler=self._evening_summary,
            run_at_time=evening_time,
        ))

        # Weekly tasks
        self.register_task(ScheduledTask(
            name="weekly_review",
            handler=self._weekly_review,
            run_at_time=weekly_time,
            run_on_day=weekly_day,
        ))

    async def run(self) -> None:
        """Main loop — check tasks and execute when due."""
        self._running = True
        logger.info(f"Proactive engine started with {len(self._tasks)} tasks")

        while self._running:
            try:
                await self._tick()
                await asyncio.sleep(self._tick_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Proactive engine tick error: {e}")
                await asyncio.sleep(self._tick_interval)

        logger.info("Proactive engine stopped")

    async def stop(self) -> None:
        """Stop the engine."""
        self._running = False

    async def _tick(self) -> None:
        """Single tick — check all tasks and run due ones."""
        now = datetime.now()
        for task in self._tasks:
            if task.should_run(now):
                await self._execute_task(task)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a single task with error handling."""
        try:
            logger.info(f"Running proactive task: {task.name}")
            await task.handler()
            task.last_run = datetime.now()
            task.run_count += 1
            logger.info(f"Task {task.name} completed (#{task.run_count})")
        except Exception as e:
            task.error_count += 1
            task.last_error = str(e)
            logger.error(f"Task {task.name} failed: {e}")

    async def run_task_by_name(self, name: str) -> bool:
        """Run a specific task by name (for testing/manual triggers).

        Returns True if task was found and executed.
        """
        for task in self._tasks:
            if task.name == name:
                await self._execute_task(task)
                return True
        return False

    def get_status(self) -> dict[str, Any]:
        """Get engine status for monitoring."""
        return {
            "running": self._running,
            "task_count": len(self._tasks),
            "tasks": [t.to_dict() for t in self._tasks],
        }

    # ── Default Task Handlers ──

    async def _check_emails(self) -> None:
        """Check for new emails and classify urgent ones."""
        try:
            events = self._db.get_events(source="gmail", unprocessed_only=True, limit=20)
            urgent_count = 0

            for event in events:
                self._db.mark_event_processed(event["id"])

                try:
                    import json
                    metadata = json.loads(event.get("metadata", "{}"))
                    if metadata.get("urgency") in ("critical", "high"):
                        urgent_count += 1
                except (ValueError, TypeError):
                    pass

            if urgent_count > 0:
                self._notify(
                    NotificationLevel.IMPORTANT,
                    "Urgent Emails",
                    f"{urgent_count} urgent email(s) need your attention",
                )

        except Exception as e:
            logger.error(f"check_emails failed: {e}")

    async def _check_calendar(self) -> None:
        """Check upcoming meetings and propose briefs for important ones."""
        try:
            events = self._db.get_events(source="calendar", limit=20)

            import json
            now = datetime.now()
            upcoming_soon = []

            for event in events:
                try:
                    metadata = json.loads(event.get("metadata", "{}"))
                    start_str = metadata.get("start_time", "")
                    if start_str:
                        start = datetime.fromisoformat(start_str)
                        if now < start < now + timedelta(hours=2):
                            attendees = json.loads(metadata.get("attendees", "[]"))
                            if len(attendees) >= 3 or event.get("priority", 0) >= 3:
                                upcoming_soon.append(event.get("title", ""))
                except (ValueError, TypeError):
                    pass

            if upcoming_soon:
                self._notify(
                    NotificationLevel.IMPORTANT,
                    "Upcoming Meeting",
                    f"Upcoming: {', '.join(upcoming_soon[:3])}",
                )

        except Exception as e:
            logger.error(f"check_calendar failed: {e}")

    async def _morning_briefing(self) -> None:
        """Generate and store morning briefing."""
        if not self._briefing_gen:
            logger.warning("No BriefingGenerator configured — skipping morning briefing")
            return

        try:
            # Prefer LLM narrative when router is available
            if hasattr(self._briefing_gen, 'generate_and_store_narrative'):
                try:
                    data, text, briefing_id = await self._briefing_gen.generate_and_store_narrative("morning")
                    logger.info(
                        f"Morning briefing (narrative) generated: id={briefing_id}, "
                        f"{data.events_processed} events, {data.actions_proposed} actions"
                    )
                    self._notify(
                        NotificationLevel.IMPORTANT,
                        "Morning Briefing",
                        text[:500],
                    )
                    return
                except Exception as e:
                    logger.warning(f"Narrative briefing failed, falling back: {e}")

            data, text, briefing_id = self._briefing_gen.generate_and_store("morning")
            logger.info(
                f"Morning briefing generated: id={briefing_id}, "
                f"{data.events_processed} events, {data.actions_proposed} actions"
            )
            self._notify(
                NotificationLevel.IMPORTANT,
                "Morning Briefing",
                text[:500],
            )
        except Exception as e:
            logger.error(f"morning_briefing failed: {e}")

    async def _evening_summary(self) -> None:
        """Generate and store evening summary."""
        if not self._briefing_gen:
            return

        try:
            # Use ReviewEngine for rich evening summaries when available
            if self._review_engine:
                try:
                    summary = self._review_engine.generate_evening()
                    text = summary.format_text()
                    # Store via briefing generator's DB
                    from omnibrain.models import Briefing
                    briefing = Briefing(
                        type="evening",
                        date=summary.date,
                        content=text,
                        events_processed=summary.stats.total_events if summary.stats else 0,
                        actions_proposed=summary.stats.proposals_actioned if summary.stats else 0,
                    )
                    self._briefing_gen._db.insert_briefing(briefing)
                    logger.info("Evening summary generated via ReviewEngine")
                    self._notify(NotificationLevel.FYI, "Evening Summary", text[:500])
                    return
                except Exception as e:
                    logger.warning("ReviewEngine evening failed, falling back: %s", e)

            data, text, briefing_id = self._briefing_gen.generate_and_store("evening")
            logger.info(f"Evening summary generated: id={briefing_id}")
            self._notify(NotificationLevel.FYI, "Evening Summary", text[:500])
        except Exception as e:
            logger.error(f"evening_summary failed: {e}")

    async def _detect_patterns(self) -> None:
        """Analyze observations for recurring patterns."""
        try:
            # Use PatternDetector when available for proper clustering
            if self._pattern_detector:
                try:
                    patterns = self._pattern_detector.detect()
                    strong = self._pattern_detector.get_strong_patterns()
                    if strong:
                        for p in strong[:3]:
                            self._notify(
                                NotificationLevel.FYI,
                                "Pattern Detected",
                                f"'{p.pattern_type}': {p.description} "
                                f"(seen {p.occurrence_count}x, strength: {p.strength})",
                            )
                    if patterns:
                        logger.info(
                            f"PatternDetector: {len(patterns)} patterns, {len(strong)} strong"
                        )
                    return
                except Exception as e:
                    logger.warning("PatternDetector failed, falling back: %s", e)

            # Fallback: simple observation grouping
            observations = self._db.get_observations(days=30)

            by_type: dict[str, list[dict[str, Any]]] = {}
            for obs in observations:
                ptype = obs.get("pattern_type", "unknown")
                if ptype not in by_type:
                    by_type[ptype] = []
                by_type[ptype].append(obs)

            promotable = []
            for ptype, obs_list in by_type.items():
                if len(obs_list) >= 3:
                    avg_conf = sum(o.get("confidence", 0) for o in obs_list) / len(obs_list)
                    if avg_conf >= 0.7:
                        promotable.append({
                            "type": ptype,
                            "count": len(obs_list),
                            "avg_confidence": round(avg_conf, 2),
                        })

            if promotable:
                for p in promotable:
                    self._notify(
                        NotificationLevel.FYI,
                        "Pattern Detected",
                        f"Pattern '{p['type']}' seen {p['count']}x "
                        f"(confidence: {p['avg_confidence']})",
                    )
                logger.info(f"Detected {len(promotable)} promotable patterns")

        except Exception as e:
            logger.error(f"detect_patterns failed: {e}")

    async def _weekly_review(self) -> None:
        """Generate weekly review."""
        if not self._briefing_gen:
            return

        try:
            # Use ReviewEngine for rich weekly reviews when available
            if self._review_engine:
                try:
                    review = self._review_engine.generate_weekly()
                    text = review.format_text()
                    from omnibrain.models import Briefing
                    briefing = Briefing(
                        type="weekly",
                        date=review.end_date,
                        content=text,
                        events_processed=review.stats.total_events if review.stats else 0,
                    )
                    self._briefing_gen._db.insert_briefing(briefing)
                    logger.info("Weekly review generated via ReviewEngine")
                    self._notify(NotificationLevel.IMPORTANT, "Weekly Review", text[:500])
                    return
                except Exception as e:
                    logger.warning("ReviewEngine weekly failed, falling back: %s", e)

            data, text, briefing_id = self._briefing_gen.generate_and_store("weekly")
            logger.info(f"Weekly review generated: id={briefing_id}")
            self._notify(NotificationLevel.IMPORTANT, "Weekly Review", text[:500])
        except Exception as e:
            logger.error(f"weekly_review failed: {e}")

    # ── Notification Helper ──

    def _notify(self, level: str, title: str, message: str) -> None:
        """Send a notification if callback is set."""
        logger.info(f"Notification [{level}]: {title}")
        if self._notify_callback:
            try:
                self._notify_callback(level, title, message)
            except Exception as e:
                logger.warning(f"Notification callback failed: {e}")

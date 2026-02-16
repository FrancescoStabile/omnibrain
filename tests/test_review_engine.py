"""
Tests for OmniBrain Review Engine — Evening Summary + Weekly Review (Day 26-28).

Groups:
    DataClasses        — DayStats, WeekStats, EveningSummary, WeeklyReview
    EveningSummary     — generate_evening, format, stats
    WeeklyReview       — generate_weekly, trends, format
    TimeSaved          — time estimation
    SevenDaySimulation — 7 full days of realistic data
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager
from omnibrain.models import Observation
from omnibrain.review_engine import (
    DayStats,
    EveningSummary,
    ReviewEngine,
    WeekStats,
    WeeklyReview,
    MINUTES_PER_DRAFT,
    MINUTES_PER_CLASSIFICATION,
    MINUTES_PER_PROPOSAL,
)


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
def memory(tmp_dir):
    return MemoryManager(tmp_dir, enable_chroma=False)


@pytest.fixture
def engine(db, memory):
    return ReviewEngine(db, memory)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _seed_day_events(db: OmniBrainDB, date: str, emails: int = 3, meetings: int = 1,
                     drafts: int = 1, classifications: int = 2, executed: int = 1):
    """Insert events for a single day with controlled timestamps."""
    ts = f"{date}T10:00:00"

    for i in range(emails):
        eid = db.insert_event(
            source="gmail",
            event_type="email_received",
            title=f"Email {i+1} on {date}",
            metadata={"sender_email": f"person{i}@test.com"},
        )
        # Fix timestamp
        with db._connect() as conn:
            conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (ts, eid))

    for i in range(meetings):
        eid = db.insert_event(
            source="calendar",
            event_type="calendar_event",
            title=f"Meeting {i+1} on {date}",
            metadata={"start_time": f"{date}T14:00:00", "attendees": json.dumps(["cto@acme.com"])},
        )
        with db._connect() as conn:
            conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (ts, eid))

    for i in range(drafts):
        eid = db.insert_event(
            source="gmail",
            event_type="email_draft_generated",
            title=f"Draft {i+1} on {date}",
        )
        with db._connect() as conn:
            conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (ts, eid))

    for i in range(classifications):
        eid = db.insert_event(
            source="gmail",
            event_type="email_classified",
            title=f"Classified {i+1} on {date}",
        )
        with db._connect() as conn:
            conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (ts, eid))

    for i in range(executed):
        eid = db.insert_event(
            source="system",
            event_type="proposal_executed",
            title=f"Executed proposal {i+1} on {date}",
        )
        with db._connect() as conn:
            conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (ts, eid))


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


class TestDayStats:
    def test_defaults(self):
        s = DayStats()
        assert s.actions_taken == 0
        assert s.total_events_processed == 0

    def test_computed_properties(self):
        s = DayStats(emails_received=5, calendar_events=2, proposals_executed=3, drafts_generated=2)
        assert s.total_events_processed == 7
        assert s.actions_taken == 5

    def test_to_dict(self):
        s = DayStats(date="2025-01-15", emails_received=10)
        d = s.to_dict()
        assert d["date"] == "2025-01-15"
        assert d["emails_received"] == 10
        assert "actions_taken" in d


class TestWeekStats:
    def test_empty(self):
        w = WeekStats()
        assert w.total_emails == 0
        assert w.busiest_day == ""

    def test_with_data(self):
        days = [
            DayStats(date="2025-01-13", emails_received=3, calendar_events=1),
            DayStats(date="2025-01-14", emails_received=10, calendar_events=4),
            DayStats(date="2025-01-15", emails_received=1, calendar_events=0),
        ]
        w = WeekStats(start_date="2025-01-13", end_date="2025-01-15", daily_stats=days)
        assert w.total_emails == 14
        assert w.total_meetings == 5
        assert w.busiest_day == "2025-01-14"
        assert w.quietest_day == "2025-01-15"

    def test_to_dict(self):
        w = WeekStats(start_date="2025-01-13", end_date="2025-01-19")
        d = w.to_dict()
        assert d["start_date"] == "2025-01-13"


class TestEveningSummaryDC:
    def test_to_dict(self):
        e = EveningSummary(date="2025-01-15", time_saved_minutes=30)
        d = e.to_dict()
        assert d["date"] == "2025-01-15"
        assert d["time_saved_minutes"] == 30


class TestWeeklyReviewDC:
    def test_to_dict(self):
        r = WeeklyReview(week_start="2025-01-13", week_end="2025-01-19")
        d = r.to_dict()
        assert d["week_start"] == "2025-01-13"


# ═══════════════════════════════════════════════════════════════════════════
# Evening Summary
# ═══════════════════════════════════════════════════════════════════════════


class TestEveningSummary:
    def test_empty_day(self, engine):
        summary = engine.generate_evening(_today())
        assert summary.date == _today()
        assert summary.stats.emails_received == 0

    def test_with_emails(self, db, memory):
        engine = ReviewEngine(db, memory)
        today = _today()
        _seed_day_events(db, today, emails=5, meetings=2, drafts=2, classifications=3)

        summary = engine.generate_evening(today)
        assert summary.stats.emails_received == 5
        assert summary.stats.calendar_events == 2
        assert summary.stats.drafts_generated == 2

    def test_top_contacts(self, db, memory):
        engine = ReviewEngine(db, memory)
        today = _today()
        _seed_day_events(db, today, emails=5)

        summary = engine.generate_evening(today)
        assert len(summary.top_contacts) > 0

    def test_tomorrow_preview_no_events(self, db, memory):
        engine = ReviewEngine(db, memory)
        summary = engine.generate_evening(_today())
        assert "No meetings" in summary.tomorrow_preview or "deep work" in summary.tomorrow_preview

    def test_tomorrow_preview_with_events(self, db, memory):
        engine = ReviewEngine(db, memory)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        _seed_day_events(db, tomorrow, emails=0, meetings=3, drafts=0, classifications=0, executed=0)

        summary = engine.generate_evening(_today())
        assert "3 meeting" in summary.tomorrow_preview

    def test_key_decisions(self, db, memory):
        engine = ReviewEngine(db, memory)
        today = _today()
        _seed_day_events(db, today, emails=0, meetings=0, drafts=0, classifications=0, executed=3)

        summary = engine.generate_evening(today)
        assert len(summary.key_decisions) == 3

    def test_patterns_detected(self, db, memory):
        engine = ReviewEngine(db, memory)
        today = _today()

        # Insert observation
        db.insert_observation(Observation(
            type="recurring_search",
            detail="User checks tickets every morning",
            evidence="3 occurrences in last week",
            confidence=0.8,
        ))

        summary = engine.generate_evening(today)
        assert len(summary.patterns_detected) >= 1


class TestEveningFormat:
    def test_format_basic(self):
        summary = EveningSummary(
            date="2025-01-15",
            stats=DayStats(date="2025-01-15", emails_received=10, calendar_events=3,
                           drafts_generated=2, proposals_executed=1),
            time_saved_minutes=25,
        )
        text = summary.format_text()
        assert "Evening Summary" in text
        assert "2025-01-15" in text
        assert "10 emails" in text
        assert "25 min" in text

    def test_format_with_contacts(self):
        summary = EveningSummary(
            date="2025-01-15",
            top_contacts=["marco@test.com (5)", "anna@test.com (3)"],
        )
        text = summary.format_text()
        assert "marco@test.com" in text

    def test_format_with_tomorrow(self):
        summary = EveningSummary(
            date="2025-01-15",
            tomorrow_events=[{"title": "Sprint Review", "time": "14:00"}],
            tomorrow_preview="1 meeting: Sprint Review",
        )
        text = summary.format_text()
        assert "Sprint Review" in text
        assert "Tomorrow" in text

    def test_format_with_patterns(self):
        summary = EveningSummary(
            date="2025-01-15",
            patterns_detected=["recurring_search: Checks tickets daily"],
        )
        text = summary.format_text()
        assert "Patterns" in text
        assert "tickets" in text


# ═══════════════════════════════════════════════════════════════════════════
# Weekly Review
# ═══════════════════════════════════════════════════════════════════════════


class TestWeeklyReview:
    def test_empty_week(self, engine):
        review = engine.generate_weekly(_today(), days=7)
        assert review.week_end == _today()
        assert review.stats.total_emails == 0

    def test_with_data(self, db, memory):
        engine = ReviewEngine(db, memory)
        # Seed 3 days of data
        for i in range(3):
            d = _date_ago(i)
            _seed_day_events(db, d, emails=5 + i, meetings=1 + i, drafts=1, classifications=2, executed=1)

        review = engine.generate_weekly(_today(), days=7)
        assert review.stats.total_emails >= 15  # 5+6+7
        assert review.stats.total_meetings >= 3

    def test_busiest_day(self, db, memory):
        engine = ReviewEngine(db, memory)
        # Day 0 = 2 emails, Day 1 = 10 emails
        _seed_day_events(db, _date_ago(1), emails=10, meetings=5)
        _seed_day_events(db, _date_ago(0), emails=2, meetings=1)

        review = engine.generate_weekly(_today(), days=7)
        assert review.stats.busiest_day == _date_ago(1)

    def test_top_contacts_weekly(self, db, memory):
        engine = ReviewEngine(db, memory)
        for i in range(3):
            _seed_day_events(db, _date_ago(i), emails=3)

        review = engine.generate_weekly(_today(), days=7)
        assert len(review.top_contacts) > 0

    def test_active_projects(self, db, memory):
        engine = ReviewEngine(db, memory)
        # Insert project activity
        db.insert_event(
            source="project:omnibrain",
            event_type="project_activity",
            title="file_edit: main.py",
            metadata={"project": "omnibrain", "action": "file_edit"},
        )

        review = engine.generate_weekly(_today(), days=7)
        assert "omnibrain" in review.projects_active

    def test_observations_summary(self, db, memory):
        engine = ReviewEngine(db, memory)
        db.insert_observation(Observation(
            type="time_pattern",
            detail="Peak productivity 9-11am",
            confidence=0.85,
        ))

        review = engine.generate_weekly(_today(), days=7)
        assert len(review.observations_summary) >= 1
        assert "Peak productivity" in review.observations_summary[0]


class TestWeeklyFormat:
    def test_format_basic(self):
        review = WeeklyReview(
            week_start="2025-01-13",
            week_end="2025-01-19",
            stats=WeekStats(
                start_date="2025-01-13",
                end_date="2025-01-19",
                daily_stats=[
                    DayStats(date="2025-01-13", emails_received=5, calendar_events=2),
                    DayStats(date="2025-01-14", emails_received=8, calendar_events=3),
                ],
            ),
            total_time_saved_minutes=120,
        )
        text = review.format_text()
        assert "Weekly Review" in text
        assert "2025-01-13" in text
        assert "13 emails" in text  # 5+8
        assert "2.0h" in text  # 120 min

    def test_format_with_trends(self):
        review = WeeklyReview(
            week_start="2025-01-13",
            week_end="2025-01-19",
            trends=["📈 Email volume increasing (3 → 8/day)"],
        )
        text = review.format_text()
        assert "Trends" in text
        assert "increasing" in text

    def test_format_with_distribution(self):
        review = WeeklyReview(
            week_start="2025-01-13",
            week_end="2025-01-19",
            stats=WeekStats(
                start_date="2025-01-13",
                end_date="2025-01-19",
                daily_stats=[
                    DayStats(date="2025-01-13", emails_received=3),
                    DayStats(date="2025-01-14", emails_received=10),
                ],
            ),
        )
        text = review.format_text()
        assert "Distribution" in text
        assert "█" in text  # bar chart


# ═══════════════════════════════════════════════════════════════════════════
# Trends
# ═══════════════════════════════════════════════════════════════════════════


class TestTrends:
    def test_increasing_email_volume(self, engine):
        daily = [
            DayStats(date=f"2025-01-{13+i:02d}", emails_received=v)
            for i, v in enumerate([2, 2, 3, 5, 8, 10, 12])
        ]
        trends = engine._detect_trends(daily)
        assert any("increasing" in t.lower() for t in trends)

    def test_decreasing_email_volume(self, engine):
        daily = [
            DayStats(date=f"2025-01-{13+i:02d}", emails_received=v)
            for i, v in enumerate([12, 10, 8, 5, 3, 2, 1])
        ]
        trends = engine._detect_trends(daily)
        assert any("decreasing" in t.lower() for t in trends)

    def test_stable_volume(self, engine):
        daily = [
            DayStats(date=f"2025-01-{13+i:02d}", emails_received=5)
            for i in range(7)
        ]
        trends = engine._detect_trends(daily)
        assert any("stable" in t.lower() for t in trends)

    def test_meeting_heavy_week(self, engine):
        daily = [
            DayStats(date=f"2025-01-{13+i:02d}", calendar_events=v)
            for i, v in enumerate([4, 3, 5, 3, 4, 1, 0])
        ]
        trends = engine._detect_trends(daily)
        assert any("meeting" in t.lower() for t in trends)

    def test_proposal_acceptance_rate(self, engine):
        daily = [
            DayStats(date=f"2025-01-{13+i:02d}", proposals_created=2, proposals_executed=1)
            for i in range(4)
        ]
        trends = engine._detect_trends(daily)
        assert any("acceptance" in t.lower() or "50%" in t for t in trends)


# ═══════════════════════════════════════════════════════════════════════════
# Time Saved Estimation
# ═══════════════════════════════════════════════════════════════════════════


class TestTimeSaved:
    def test_no_actions(self, engine):
        s = DayStats()
        assert engine._estimate_time_saved(s) == 0

    def test_drafts_only(self, engine):
        s = DayStats(drafts_generated=3)
        assert engine._estimate_time_saved(s) == 3 * MINUTES_PER_DRAFT

    def test_classifications_only(self, engine):
        s = DayStats(emails_classified=10)
        assert engine._estimate_time_saved(s) == 10 * MINUTES_PER_CLASSIFICATION

    def test_combined(self, engine):
        s = DayStats(drafts_generated=2, emails_classified=5, proposals_executed=3)
        expected = 2 * MINUTES_PER_DRAFT + 5 * MINUTES_PER_CLASSIFICATION + 3 * MINUTES_PER_PROPOSAL
        assert engine._estimate_time_saved(s) == expected

    def test_evening_includes_time_saved(self, db, memory):
        engine = ReviewEngine(db, memory)
        today = _today()
        _seed_day_events(db, today, drafts=2, classifications=5, executed=1)

        summary = engine.generate_evening(today)
        assert summary.time_saved_minutes > 0


# ═══════════════════════════════════════════════════════════════════════════
# 7-Day Simulation
# ═══════════════════════════════════════════════════════════════════════════


class TestSevenDaySimulation:
    """Simulate a full week of realistic data and generate a weekly review."""

    def test_full_week(self, db, memory):
        """Seed 7 days, generate weekly review, validate all sections."""
        engine = ReviewEngine(db, memory)

        # Seed 7 days with varying data
        patterns = [
            # (emails, meetings, drafts, classifications, executed)
            (8, 2, 2, 6, 1),   # Monday — busy
            (12, 3, 3, 10, 2), # Tuesday — heaviest
            (6, 1, 1, 4, 1),   # Wednesday — light
            (10, 4, 2, 8, 2),  # Thursday — meeting-heavy
            (5, 1, 1, 3, 1),   # Friday — winding down
            (2, 0, 0, 1, 0),   # Saturday — minimal
            (1, 0, 0, 0, 0),   # Sunday — rest
        ]

        for i, (emails, meetings, drafts, classifs, executed) in enumerate(patterns):
            d = _date_ago(6 - i)  # 6 days ago -> today
            _seed_day_events(db, d, emails=emails, meetings=meetings,
                             drafts=drafts, classifications=classifs, executed=executed)

        # Add observations
        db.insert_observation(Observation(
            type="communication_pattern",
            detail="Marco prefers email over Telegram",
            confidence=0.9,
        ))
        db.insert_observation(Observation(
            type="time_pattern",
            detail="Most productive between 9-11am",
            confidence=0.75,
        ))

        # Add project activity
        db.insert_event(
            source="project:omnibrain",
            event_type="project_activity",
            title="file_edit: brain.py",
            metadata={"project": "omnibrain"},
        )

        # Generate weekly review
        review = engine.generate_weekly(_today(), days=7)

        # Validate stats
        assert review.stats.total_emails == sum(p[0] for p in patterns)  # 44
        assert review.stats.total_meetings == sum(p[1] for p in patterns)  # 11
        assert review.stats.total_actions > 0

        # Validate trends
        assert len(review.trends) >= 1

        # Validate observations
        assert len(review.observations_summary) >= 2

        # Validate projects
        assert "omnibrain" in review.projects_active

        # Validate time saved
        assert review.total_time_saved_minutes > 0

        # Format and check output
        text = review.format_text()
        assert "Weekly Review" in text
        assert "44 emails" in text
        assert "11 meetings" in text
        assert "█" in text  # bar chart present
        assert "omnibrain" in text

    def test_evening_after_busy_day(self, db, memory):
        """Generate evening summary after a busy day with all sections filled."""
        engine = ReviewEngine(db, memory)
        today = _today()

        # Seed a busy day
        _seed_day_events(db, today, emails=15, meetings=4, drafts=5,
                         classifications=12, executed=3)

        # Add tomorrow's events
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        _seed_day_events(db, tomorrow, emails=0, meetings=2, drafts=0,
                         classifications=0, executed=0)

        # Add observation
        db.insert_observation(Observation(
            type="recurring_search",
            detail="Checking analytics dashboard at 2pm daily",
            confidence=0.7,
        ))

        summary = engine.generate_evening(today)

        assert summary.stats.emails_received == 15
        assert summary.stats.calendar_events == 4
        assert summary.stats.drafts_generated == 5
        assert summary.stats.actions_taken == 8  # 5 drafts + 3 executed
        assert summary.time_saved_minutes > 0
        assert len(summary.key_decisions) == 3
        assert len(summary.tomorrow_events) == 2
        assert "2 meetings" in summary.tomorrow_preview

        text = summary.format_text()
        assert "Evening Summary" in text
        assert "15 emails" in text
        assert "Tomorrow" in text

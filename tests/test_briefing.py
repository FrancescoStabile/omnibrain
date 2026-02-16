"""
Tests for OmniBrain Morning Briefing (Day 11-12).

Groups:
    EmailSection        — Email data model
    CalendarSection     — Calendar data model
    ProposalSection     — Proposal data model
    BriefingData        — Combined briefing data
    BriefingGenerator   — Collect data + generate briefings
    Formatting          — format_text output
    Priorities          — Priority generation logic
    Helpers             — Conflict detection, metadata helpers
    Integration         — End-to-end briefing flows
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.briefing import (
    BriefingData,
    BriefingGenerator,
    CalendarSection,
    EmailSection,
    PriorityItem,
    ProposalSection,
    _detect_conflicts,
    _meta_flag,
    _meta_int,
    _meta_list,
    _meta_str,
)
from omnibrain.models import Briefing, BriefingType, Observation
from omnibrain.db import OmniBrainDB


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db(tmp_dir):
    """Create a test database."""
    return OmniBrainDB(tmp_dir)


@pytest.fixture
def mock_memory():
    """Create a mock MemoryManager."""
    mm = MagicMock()
    mm.get_recent.return_value = []
    return mm


@pytest.fixture
def generator(db, mock_memory):
    """Create a BriefingGenerator with test DB."""
    return BriefingGenerator(db, mock_memory)


@pytest.fixture
def populated_db(db):
    """DB with some test data."""
    # Add emails
    for i in range(5):
        db.insert_event(
            source="gmail",
            event_type="email",
            title=f"Email {i}: Subject {i}",
            content=f"Body of email {i}",
            metadata={
                "sender_email": f"sender{i}@test.com",
                "is_read": str(i > 2).lower(),
                "urgency": "high" if i == 0 else "medium",
            },
        )

    # Add calendar events
    now = datetime.now()
    for i in range(3):
        start = now + timedelta(hours=i + 1)
        end = start + timedelta(hours=1)
        db.insert_event(
            source="calendar",
            event_type="calendar",
            title=f"Meeting {i}",
            content="",
            metadata={
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "duration_minutes": "60",
                "attendees": json.dumps(["alice@test.com", "bob@test.com"]) if i < 2 else "[]",
            },
        )

    # Add proposals
    db.insert_proposal(
        type="email_draft",
        title="Draft reply to investor",
        description="Draft response to investor email",
        priority=4,
    )
    db.insert_proposal(
        type="meeting_brief",
        title="Sprint planning prep",
        description="Prepare for sprint planning",
        priority=2,
    )

    # Add observation
    db.insert_observation(Observation(
        type="communication",
        detail="User prefers morning responses",
        confidence=0.8,
    ))

    return db


# ═══════════════════════════════════════════════════════════════════════════
# Data Model Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailSection:
    def test_defaults(self):
        s = EmailSection()
        assert s.total == 0
        assert s.unread == 0
        assert s.urgent == 0
        assert s.top_senders == []

    def test_to_dict(self):
        s = EmailSection(total=10, unread=3, urgent=1, drafts_ready=2, top_senders=["a@t.com"])
        d = s.to_dict()
        assert d["total"] == 10
        assert d["unread"] == 3
        assert d["drafts_ready"] == 2
        assert d["top_senders"] == ["a@t.com"]


class TestCalendarSection:
    def test_defaults(self):
        s = CalendarSection()
        assert s.total_events == 0
        assert s.total_hours == 0.0
        assert s.conflicts == []

    def test_to_dict(self):
        s = CalendarSection(total_events=3, total_hours=2.5, next_meeting="Standup")
        d = s.to_dict()
        assert d["total_events"] == 3
        assert d["next_meeting"] == "Standup"


class TestProposalSection:
    def test_defaults(self):
        s = ProposalSection()
        assert s.total_pending == 0
        assert s.by_type == {}

    def test_to_dict(self):
        s = ProposalSection(
            total_pending=2,
            by_type={"email_draft": 1, "task": 1},
            high_priority=[{"type": "email_draft", "title": "Reply"}],
        )
        d = s.to_dict()
        assert d["total_pending"] == 2
        assert d["by_type"]["email_draft"] == 1


class TestPriorityItem:
    def test_creation(self):
        p = PriorityItem(rank=1, title="Reply to boss", reason="Urgent email")
        assert p.rank == 1
        assert p.source == ""

    def test_to_dict(self):
        p = PriorityItem(rank=1, title="Test", reason="Because", source="email")
        d = p.to_dict()
        assert d["rank"] == 1
        assert d["source"] == "email"


class TestBriefingData:
    def test_defaults(self):
        d = BriefingData()
        assert d.briefing_type == "morning"
        assert d.events_processed == 0
        assert d.actions_proposed == 0

    def test_events_processed(self):
        d = BriefingData()
        d.emails = EmailSection(total=5)
        d.calendar = CalendarSection(total_events=3)
        assert d.events_processed == 8

    def test_actions_proposed(self):
        d = BriefingData()
        d.proposals = ProposalSection(total_pending=4)
        assert d.actions_proposed == 4

    def test_to_dict(self):
        d = BriefingData(date="2024-01-15", briefing_type="morning")
        d.priorities = [PriorityItem(rank=1, title="Test", reason="R")]
        result = d.to_dict()
        assert result["date"] == "2024-01-15"
        assert result["briefing_type"] == "morning"
        assert len(result["priorities"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# BriefingGenerator Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefingGenerator:
    def test_creation(self, db):
        gen = BriefingGenerator(db)
        assert gen._db is db
        assert gen._memory is None

    def test_creation_with_memory(self, db, mock_memory):
        gen = BriefingGenerator(db, mock_memory)
        assert gen._memory is mock_memory

    def test_collect_empty_db(self, generator):
        data = generator.collect_data()
        assert data.briefing_type == "morning"
        assert data.emails.total == 0
        assert data.calendar.total_events == 0
        assert data.proposals.total_pending == 0

    def test_collect_with_data(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        assert data.emails.total == 5
        assert data.calendar.total_events == 3
        assert data.proposals.total_pending == 2

    def test_collect_emails(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        assert data.emails.total == 5
        assert data.emails.urgent >= 1  # email 0 is "high"
        assert data.emails.drafts_ready == 1  # 1 email_draft proposal

    def test_collect_calendar(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        assert data.calendar.total_events == 3
        assert data.calendar.total_hours >= 0

    def test_collect_proposals(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        assert data.proposals.total_pending == 2
        assert "email_draft" in data.proposals.by_type
        # Priority 4 proposal should be in high_priority
        assert len(data.proposals.high_priority) >= 1

    def test_collect_observations(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        assert len(data.observations) >= 1

    def test_generate_returns_data_and_text(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data, text = gen.generate()
        assert isinstance(data, BriefingData)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_generate_and_store(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data, text, briefing_id = gen.generate_and_store()
        assert briefing_id > 0

        # Verify stored in DB
        stored = populated_db.get_latest_briefing("morning")
        assert stored is not None
        assert stored["content"] == text

    def test_store(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data = BriefingData(date="2024-01-15")
        bid = gen.store(data, "test content")
        assert bid > 0

    def test_collect_briefing_types(self, generator):
        for btype in ("morning", "evening", "weekly"):
            data = generator.collect_data(btype)
            assert data.briefing_type == btype


# ═══════════════════════════════════════════════════════════════════════════
# Format Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatText:
    def test_empty_briefing(self, generator):
        data = BriefingData(date="2024-01-15")
        text = generator.format_text(data)
        assert "Morning Briefing" in text
        assert "All quiet today" in text

    def test_email_section(self, generator):
        data = BriefingData(date="2024-01-15")
        data.emails = EmailSection(total=10, unread=3, urgent=2)
        text = generator.format_text(data)
        assert "Email Overview" in text
        assert "10 emails" in text
        assert "3 unread" in text
        assert "2 urgent" in text

    def test_calendar_section(self, generator):
        data = BriefingData(date="2024-01-15")
        data.calendar = CalendarSection(
            total_events=3,
            total_hours=2.5,
            next_meeting="Standup",
            next_meeting_time="10:00",
        )
        text = generator.format_text(data)
        assert "Calendar" in text
        assert "3 events" in text
        assert "Standup" in text

    def test_proposals_section(self, generator):
        data = BriefingData(date="2024-01-15")
        data.proposals = ProposalSection(
            total_pending=2,
            high_priority=[{"type": "email_draft", "title": "Reply to boss"}],
        )
        text = generator.format_text(data)
        assert "Pending Actions" in text
        assert "2 actions" in text
        assert "Reply to boss" in text

    def test_priorities_section(self, generator):
        data = BriefingData(date="2024-01-15")
        data.priorities = [
            PriorityItem(rank=1, title="Do the thing", reason="Because it's important"),
        ]
        text = generator.format_text(data)
        assert "Top Priorities" in text
        assert "Do the thing" in text

    def test_observations_section(self, generator):
        data = BriefingData(date="2024-01-15")
        data.observations = ["User prefers morning meetings"]
        text = generator.format_text(data)
        assert "Patterns Detected" in text
        assert "morning meetings" in text

    def test_evening_briefing_title(self, generator):
        data = BriefingData(date="2024-01-15", briefing_type="evening")
        text = generator.format_text(data)
        assert "Evening Summary" in text

    def test_weekly_briefing_title(self, generator):
        data = BriefingData(date="2024-01-15", briefing_type="weekly")
        text = generator.format_text(data)
        assert "Weekly Review" in text

    def test_full_briefing_format(self, populated_db, mock_memory):
        gen = BriefingGenerator(populated_db, mock_memory)
        data, text = gen.generate()
        # Should have multiple sections
        assert "Email" in text
        assert "Calendar" in text
        assert "Priorities" in text or "All quiet" in text


# ═══════════════════════════════════════════════════════════════════════════
# Priority Generation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPriorityGeneration:
    def test_urgent_emails_first(self, generator):
        data = BriefingData()
        data.emails = EmailSection(urgent=3)
        priorities = generator._generate_priorities(data)
        assert len(priorities) >= 1
        assert "urgent" in priorities[0].title.lower()
        assert priorities[0].source == "email"

    def test_next_meeting_priority(self, generator):
        data = BriefingData()
        data.calendar = CalendarSection(next_meeting="Sprint Planning", next_meeting_time="10:00")
        priorities = generator._generate_priorities(data)
        assert len(priorities) >= 1
        assert "Sprint Planning" in priorities[0].title

    def test_draft_emails_priority(self, generator):
        data = BriefingData()
        data.emails = EmailSection(drafts_ready=2)
        priorities = generator._generate_priorities(data)
        assert len(priorities) >= 1
        assert "draft" in priorities[0].title.lower()

    def test_max_5_priorities(self, generator):
        data = BriefingData()
        data.emails = EmailSection(urgent=3, drafts_ready=2)
        data.calendar = CalendarSection(next_meeting="Meeting")
        data.proposals = ProposalSection(
            high_priority=[
                {"title": "P1"}, {"title": "P2"}, {"title": "P3"},
            ]
        )
        priorities = generator._generate_priorities(data)
        assert len(priorities) <= 5

    def test_empty_data_no_priorities(self, generator):
        data = BriefingData()
        priorities = generator._generate_priorities(data)
        assert len(priorities) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Helper Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:
    def test_meta_str(self):
        event = {"metadata": json.dumps({"key": "value"})}
        assert _meta_str(event, "key") == "value"
        assert _meta_str(event, "missing") == ""

    def test_meta_str_already_dict(self):
        event = {"metadata": {"key": "123"}}
        assert _meta_str(event, "key") == "123"

    def test_meta_int(self):
        event = {"metadata": json.dumps({"count": "42"})}
        assert _meta_int(event, "count") == 42
        assert _meta_int(event, "missing") == 0

    def test_meta_flag(self):
        event = {"metadata": json.dumps({"is_read": "true"})}
        assert _meta_flag(event, "is_read") is True
        event2 = {"metadata": json.dumps({"is_read": "false"})}
        assert _meta_flag(event2, "is_read") is False

    def test_meta_list(self):
        event = {"metadata": json.dumps({"attendees": '["a@t.com","b@t.com"]'})}
        result = _meta_list(event, "attendees")
        assert result == ["a@t.com", "b@t.com"]

    def test_meta_list_empty(self):
        event = {"metadata": json.dumps({})}
        assert _meta_list(event, "attendees") == []

    def test_detect_conflicts(self):
        now = datetime.now()
        events = [
            {"title": "Meeting A", "metadata": json.dumps({
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            })},
            {"title": "Meeting B", "metadata": json.dumps({
                "start_time": (now + timedelta(minutes=30)).isoformat(),
                "end_time": (now + timedelta(hours=1, minutes=30)).isoformat(),
            })},
        ]
        conflicts = _detect_conflicts(events)
        assert len(conflicts) == 1
        assert "Meeting A" in conflicts[0]
        assert "Meeting B" in conflicts[0]

    def test_detect_no_conflicts(self):
        now = datetime.now()
        events = [
            {"title": "Meeting A", "metadata": json.dumps({
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            })},
            {"title": "Meeting B", "metadata": json.dumps({
                "start_time": (now + timedelta(hours=2)).isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
            })},
        ]
        conflicts = _detect_conflicts(events)
        assert len(conflicts) == 0

    def test_detect_conflicts_empty(self):
        assert _detect_conflicts([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# Memory Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryIntegration:
    def test_no_memory_manager(self, db):
        gen = BriefingGenerator(db, memory_manager=None)
        data = gen.collect_data()
        assert data.memory_highlights == []

    def test_with_memory_highlights(self, db):
        mm = MagicMock()
        doc = MagicMock()
        doc.text = "User prefers morning emails"
        mm.get_recent.return_value = [doc]

        gen = BriefingGenerator(db, mm)
        data = gen.collect_data()
        assert len(data.memory_highlights) == 1
        assert "morning" in data.memory_highlights[0]

    def test_memory_error_handled(self, db):
        mm = MagicMock()
        mm.get_recent.side_effect = Exception("Memory unavailable")

        gen = BriefingGenerator(db, mm)
        data = gen.collect_data()
        assert data.memory_highlights == []  # Graceful fallback


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_end_to_end_empty(self, generator):
        """Generate briefing with empty DB."""
        data, text, bid = generator.generate_and_store()
        assert bid > 0
        assert "All quiet today" in text

    def test_end_to_end_with_data(self, populated_db, mock_memory):
        """Generate briefing with populated DB."""
        gen = BriefingGenerator(populated_db, mock_memory)
        data, text, bid = gen.generate_and_store()
        assert bid > 0
        assert data.emails.total > 0
        assert data.calendar.total_events > 0
        assert len(text) > 100

        # Verify stored in DB
        stored = populated_db.get_latest_briefing("morning")
        assert stored is not None
        assert stored["events_processed"] > 0

    def test_multiple_briefing_types(self, populated_db, mock_memory):
        """Generate morning, evening, weekly briefings."""
        gen = BriefingGenerator(populated_db, mock_memory)

        for btype in ("morning", "evening", "weekly"):
            _, text, bid = gen.generate_and_store(btype)
            assert bid > 0
            stored = populated_db.get_latest_briefing(btype)
            assert stored is not None

    def test_idempotent_briefing(self, populated_db, mock_memory):
        """Generating twice doesn't corrupt data."""
        gen = BriefingGenerator(populated_db, mock_memory)
        _, text1, _ = gen.generate_and_store()
        _, text2, _ = gen.generate_and_store()
        assert text1 == text2  # Same data, same output

    def test_briefing_data_serializable(self, populated_db, mock_memory):
        """BriefingData.to_dict() produces valid JSON-serializable output."""
        gen = BriefingGenerator(populated_db, mock_memory)
        data = gen.collect_data()
        d = data.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert json_str
        parsed = json.loads(json_str)
        assert parsed["briefing_type"] == "morning"

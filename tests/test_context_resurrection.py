"""
Tests for OmniBrain Context Resurrection (Day 24-25).

Groups:
    DataClasses          — ProjectActivity, ProjectSnapshot, ResurrectionSummary
    Recording            — record_activity, record_blocker, record_note, record_branch
    ProjectContext       — get_project_context, get_all_projects, get_dormant_projects
    Resurrection         — detect_return, generate_resurrection
    SimulateReturn       — simulate 20+ day absence and return
    FormatText           — ResurrectionSummary formatting
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from omnibrain.context_resurrection import (
    ContextTracker,
    ProjectActivity,
    ProjectSnapshot,
    ResurrectionSummary,
)
from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager


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
def tracker(db, memory):
    return ContextTracker(db, memory, dormant_days=3)


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Test data class basics."""

    def test_project_activity_to_dict(self):
        a = ProjectActivity(project="omnibrain", action="file_edit", detail="main.py")
        d = a.to_dict()
        assert d["project"] == "omnibrain"
        assert d["action"] == "file_edit"
        assert d["detail"] == "main.py"
        assert d["timestamp"]  # auto-filled

    def test_project_snapshot_to_dict(self):
        s = ProjectSnapshot(
            project="omnibrain",
            branch="feature/api",
            last_files=["main.py", "config.py"],
            days_inactive=15,
        )
        d = s.to_dict()
        assert d["project"] == "omnibrain"
        assert d["branch"] == "feature/api"
        assert d["days_inactive"] == 15

    def test_resurrection_summary_to_dict(self):
        r = ResurrectionSummary(
            project="omnibrain",
            days_since_last=20,
            last_branch="feature/api",
            last_files=["main.py"],
            blockers=["ChromaDB incompatible"],
            what_changed=["New PR merged"],
            related_conversations=["Marco discussed this"],
            suggested_next_steps=["Fix ChromaDB"],
        )
        d = r.to_dict()
        assert d["days_since_last"] == 20
        assert "ChromaDB" in d["blockers"][0]


# ═══════════════════════════════════════════════════════════════════════════
# Recording
# ═══════════════════════════════════════════════════════════════════════════


class TestRecording:
    """Test activity recording."""

    def test_record_activity(self, tracker):
        eid = tracker.record_activity("omnibrain", "file_edit", "src/main.py")
        assert eid > 0

    def test_record_blocker(self, tracker):
        eid = tracker.record_blocker("omnibrain", "ChromaDB incompatible with 3.14")
        assert eid > 0

    def test_record_note(self, tracker):
        eid = tracker.record_note("omnibrain", "Need to refactor router module")
        assert eid > 0

    def test_record_branch(self, tracker):
        eid = tracker.record_branch("omnibrain", "feature/context-resurrection")
        assert eid > 0

    def test_multiple_projects(self, tracker):
        tracker.record_activity("omnibrain", "file_edit", "main.py")
        tracker.record_activity("landing", "file_edit", "index.html")
        projects = tracker.get_all_projects()
        assert "omnibrain" in projects
        assert "landing" in projects


# ═══════════════════════════════════════════════════════════════════════════
# Project Context
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectContext:
    """Test project context retrieval."""

    def test_empty_project(self, tracker):
        ctx = tracker.get_project_context("nonexistent")
        assert ctx.project == "nonexistent"
        assert ctx.activity_count == 0

    def test_context_with_activities(self, tracker):
        tracker.record_activity("omnibrain", "file_edit", "main.py")
        tracker.record_activity("omnibrain", "file_edit", "config.py")
        tracker.record_branch("omnibrain", "feature/api")
        tracker.record_blocker("omnibrain", "API rate limiting")

        ctx = tracker.get_project_context("omnibrain")
        assert ctx.project == "omnibrain"
        assert ctx.activity_count == 4
        assert ctx.branch == "feature/api"
        assert "main.py" in ctx.last_files
        assert "config.py" in ctx.last_files
        assert "API rate limiting" in ctx.blockers

    def test_context_with_notes(self, tracker):
        tracker.record_note("omnibrain", "Consider FTS5 for search")
        ctx = tracker.get_project_context("omnibrain")
        assert "Consider FTS5 for search" in ctx.notes

    def test_get_all_projects(self, tracker):
        tracker.record_activity("proj-a", "file_edit", "a.py")
        tracker.record_activity("proj-b", "file_edit", "b.py")
        projects = tracker.get_all_projects()
        assert len(projects) == 2

    def test_get_dormant_projects(self, db, memory):
        """Projects with old timestamps are dormant."""
        tracker = ContextTracker(db, memory, dormant_days=3)

        # Insert old event manually to simulate dormancy
        old_ts = (datetime.now() - timedelta(days=10)).isoformat()
        db.insert_event(
            source="project:old-proj",
            event_type="project_activity",
            title="file_edit: old.py",
            metadata={"project": "old-proj", "action": "file_edit", "detail": "old.py"},
        )

        # Make the event look old by updating timestamp directly
        import sqlite3
        with db._connect() as conn:
            conn.execute(
                "UPDATE events SET timestamp = ? WHERE source = ?",
                (old_ts, "project:old-proj"),
            )

        dormant = tracker.get_dormant_projects()
        assert len(dormant) >= 1
        assert dormant[0].project == "old-proj"
        assert dormant[0].days_inactive >= 10


# ═══════════════════════════════════════════════════════════════════════════
# Resurrection
# ═══════════════════════════════════════════════════════════════════════════


class TestResurrection:
    """Test context resurrection."""

    def test_no_resurrection_for_active(self, tracker):
        tracker.record_activity("omnibrain", "file_edit", "main.py")
        result = tracker.detect_return("omnibrain")
        assert result is None  # Recently active, no resurrection

    def test_resurrection_for_dormant(self, db, memory):
        tracker = ContextTracker(db, memory, dormant_days=3)

        # Insert old activities
        old_ts = (datetime.now() - timedelta(days=20)).isoformat()
        for f in ["Hero.tsx", "package.json"]:
            db.insert_event(
                source="project:landing",
                event_type="project_activity",
                title=f"file_edit: {f}",
                metadata={"project": "landing", "action": "file_edit", "detail": f},
            )
        db.insert_event(
            source="project:landing",
            event_type="project_activity",
            title="branch_switch: feature/landing-v2",
            metadata={"project": "landing", "action": "branch_switch", "detail": "feature/landing-v2"},
        )
        db.insert_event(
            source="project:landing",
            event_type="project_activity",
            title="blocker_noted: Framer Motion perf on mobile",
            metadata={"project": "landing", "action": "blocker_noted", "detail": "Framer Motion perf on mobile", "is_blocker": True},
        )

        # Make events old
        import sqlite3
        with db._connect() as conn:
            conn.execute(
                "UPDATE events SET timestamp = ? WHERE source = ?",
                (old_ts, "project:landing"),
            )

        result = tracker.detect_return("landing")
        assert result is not None
        assert result.project == "landing"
        assert result.days_since_last >= 20
        assert result.last_branch == "feature/landing-v2"
        assert "Framer Motion" in result.blockers[0]
        assert "Hero.tsx" in result.last_files or "package.json" in result.last_files

    def test_generate_resurrection_directly(self, tracker):
        tracker.record_activity("omnibrain", "file_edit", "main.py")
        tracker.record_branch("omnibrain", "feature/api")
        tracker.record_blocker("omnibrain", "Rate limiting issue")

        summary = tracker.generate_resurrection("omnibrain")
        assert summary.project == "omnibrain"
        assert summary.last_branch == "feature/api"
        assert "Rate limiting" in summary.blockers[0]

    def test_suggestions_include_blocker(self, tracker):
        tracker.record_blocker("omnibrain", "FTS5 not working")
        summary = tracker.generate_resurrection("omnibrain")
        assert any("FTS5" in s for s in summary.suggested_next_steps)

    def test_suggestions_include_files(self, tracker):
        tracker.record_activity("omnibrain", "file_edit", "router.py")
        summary = tracker.generate_resurrection("omnibrain")
        assert any("router.py" in s for s in summary.suggested_next_steps)

    def test_suggestions_include_branch(self, tracker):
        tracker.record_branch("omnibrain", "feature/patterns")
        summary = tracker.generate_resurrection("omnibrain")
        assert any("feature/patterns" in s for s in summary.suggested_next_steps)


# ═══════════════════════════════════════════════════════════════════════════
# Format Text
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatText:
    """Test resurrection summary formatting."""

    def test_format_basic(self):
        r = ResurrectionSummary(
            project="omnibrain",
            days_since_last=15,
            last_branch="main",
            last_files=["main.py"],
            blockers=[],
            what_changed=[],
            related_conversations=[],
            suggested_next_steps=["Continue coding"],
        )
        text = r.format_text()
        assert "omnibrain" in text
        assert "15 day" in text

    def test_format_with_blockers(self):
        r = ResurrectionSummary(
            project="landing",
            days_since_last=23,
            last_branch="feature/v2",
            last_files=["Hero.tsx"],
            blockers=["Framer Motion perf on mobile"],
            what_changed=["React Spring is 3x faster"],
            related_conversations=["Discussed with Marco"],
            suggested_next_steps=["Try React Spring"],
        )
        text = r.format_text()
        assert "Framer Motion" in text
        assert "React Spring" in text
        assert "Marco" in text
        assert "23 day" in text

    def test_format_contains_sections(self):
        r = ResurrectionSummary(
            project="test",
            days_since_last=5,
            last_branch="dev",
            last_files=["a.py"],
            blockers=["Bug X"],
            what_changed=["Fixed Y"],
            related_conversations=["Chat with Z"],
            suggested_next_steps=["Deploy"],
        )
        text = r.format_text()
        assert "Blockers" in text
        assert "What changed" in text
        assert "Related conversations" in text
        assert "Suggested next steps" in text


# ═══════════════════════════════════════════════════════════════════════════
# Simulate 20+ Day Return
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulateReturn:
    """Simulate 20+ day project absence and return."""

    def test_full_scenario(self, db, memory):
        """Simulate: work on landing page → 23 days away → return."""
        tracker = ContextTracker(db, memory, dormant_days=3)

        # Phase 1: Active work 23 days ago
        old_ts = (datetime.now() - timedelta(days=23)).isoformat()

        for action, detail in [
            ("file_edit", "components/Hero.tsx"),
            ("file_edit", "package.json"),
            ("branch_switch", "feature/landing-v2"),
            ("blocker_noted", "Framer Motion performance on mobile"),
            ("note", "Consider React Spring as alternative"),
        ]:
            db.insert_event(
                source="project:landing",
                event_type="project_activity",
                title=f"{action}: {detail}",
                metadata={"project": "landing", "action": action, "detail": detail,
                          "is_blocker": action == "blocker_noted", "is_note": action == "note"},
            )

        # Make events old
        with db._connect() as conn:
            conn.execute(
                "UPDATE events SET timestamp = ? WHERE source = ?",
                (old_ts, "project:landing"),
            )

        # Phase 2: Memory has relevant update
        memory.store(
            text="Found that React Spring is 3x faster than Framer Motion for mobile animations",
            source="newsletter",
            source_type="email",
        )
        memory.store(
            text="Discussed landing page with Marco on Feb 2",
            source="marco@test.com",
            source_type="email",
            contacts=["marco@test.com"],
        )

        # Phase 3: User returns
        resurrection = tracker.detect_return("landing")
        assert resurrection is not None
        assert resurrection.project == "landing"
        assert resurrection.days_since_last >= 23
        assert resurrection.last_branch == "feature/landing-v2"
        assert "Framer Motion" in resurrection.blockers[0]
        assert "components/Hero.tsx" in resurrection.last_files

        # Format and verify readable output
        text = resurrection.format_text()
        assert "landing" in text
        assert "23" in text or "day" in text

    def test_multiple_projects_one_dormant(self, db, memory):
        """One project active, one dormant."""
        tracker = ContextTracker(db, memory, dormant_days=3)

        # Active project
        tracker.record_activity("omnibrain", "file_edit", "main.py")

        # Dormant project
        old_ts = (datetime.now() - timedelta(days=30)).isoformat()
        db.insert_event(
            source="project:old-demo",
            event_type="project_activity",
            title="file_edit: demo.py",
            metadata={"project": "old-demo", "action": "file_edit", "detail": "demo.py"},
        )
        with db._connect() as conn:
            conn.execute(
                "UPDATE events SET timestamp = ? WHERE source = ?",
                (old_ts, "project:old-demo"),
            )

        # Active project should NOT trigger resurrection
        assert tracker.detect_return("omnibrain") is None

        # Dormant project SHOULD trigger
        result = tracker.detect_return("old-demo")
        assert result is not None
        assert result.days_since_last >= 30

    def test_dormant_projects_list(self, db, memory):
        """List all dormant projects."""
        tracker = ContextTracker(db, memory, dormant_days=3)

        # Create some dormant projects
        for proj in ["old-a", "old-b"]:
            old_ts = (datetime.now() - timedelta(days=15)).isoformat()
            db.insert_event(
                source=f"project:{proj}",
                event_type="project_activity",
                title="file_edit: x.py",
                metadata={"project": proj, "action": "file_edit", "detail": "x.py"},
            )
            with db._connect() as conn:
                conn.execute(
                    "UPDATE events SET timestamp = ? WHERE source = ?",
                    (old_ts, f"project:{proj}"),
                )

        dormant = tracker.get_dormant_projects()
        assert len(dormant) == 2

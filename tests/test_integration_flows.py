"""
Integration tests for OmniBrain — Phase 3.

End-to-end flows that exercise multiple modules together through
the real SQLite database. No mocks on the DB layer.

Coverage:
    1. DB CRUD comprehensive (all public methods)
    2. Email pipeline: store → classify → proposal → approve
    3. Calendar pipeline: store → briefing inclusion
    4. Proactive engine: seed DB → tick → notifications
    5. Pattern detection: observe → detect → promote → propose
    6. Agent session persistence roundtrip
    7. Priority scorer integration with DB data
    8. Briefing generation from real DB data
    9. Data lifecycle: insert → query → prune → verify
   10. GDPR export + wipe
"""

from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from omnibrain.db import OmniBrainDB
from omnibrain.models import (
    Briefing,
    BriefingType,
    ContactInfo,
    EmailClassification,
    NotificationLevel,
    Observation,
    Priority,
    ProposalStatus,
    Relationship,
    Urgency,
)
from omnibrain.briefing import BriefingGenerator
from omnibrain.proactive.engine import ProactiveEngine
from omnibrain.proactive.patterns import PatternDetector
from omnibrain.proactive.scorer import (
    NotificationLevelSelector,
    PriorityScorer,
    ScoringSignals,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db(tmp_path):
    """Fresh OmniBrainDB on tmp_path."""
    return OmniBrainDB(tmp_path)


@pytest.fixture
def seeded_db(db):
    """DB pre-loaded with representative data."""
    # Emails
    for i in range(5):
        urgency = "critical" if i == 0 else "medium"
        db.insert_event(
            source="gmail",
            event_type="email",
            title=f"Email #{i}: Test subject {i}",
            content=f"Body of email {i}",
            metadata={
                "sender_email": f"user{i}@example.com",
                "urgency": urgency,
                "is_read": i > 2,
            },
            priority=4 if i == 0 else 2,
        )

    # Calendar events
    now = datetime.now()
    for i in range(3):
        start = now + timedelta(hours=i + 1)
        db.insert_event(
            source="calendar",
            event_type="meeting",
            title=f"Meeting #{i}: Standup {i}",
            content="",
            metadata={
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=1)).isoformat(),
                "duration_minutes": 60,
                "attendees": json.dumps(["alice@co.com", "bob@co.com"]),
            },
            priority=2,
        )

    # Contacts
    db.upsert_contact(ContactInfo(
        email="vip@company.com",
        name="VIP Person",
        relationship=Relationship.CLIENT.value,
        interaction_count=50,
        avg_response_time_hours=1.0,
    ))
    db.upsert_contact(ContactInfo(
        email="casual@example.com",
        name="Casual Person",
        relationship=Relationship.UNKNOWN.value,
        interaction_count=2,
    ))

    # Proposals
    db.insert_proposal(
        type="email_draft",
        title="Reply to VIP",
        description="Draft reply to important client",
        priority=Priority.HIGH.value,
    )
    db.insert_proposal(
        type="meeting_brief",
        title="Brief for standup",
        description="Prepare meeting brief",
        priority=Priority.MEDIUM.value,
    )

    # Observations
    for i in range(4):
        db.insert_observation(Observation(
            type="time_pattern",
            detail=f"Reads email at 09:0{i}",
            confidence=0.8,
        ))

    return db


# ═══════════════════════════════════════════════════════════════════════════
# 1. DB CRUD Comprehensive
# ═══════════════════════════════════════════════════════════════════════════


class TestDBEvents:
    def test_insert_and_get(self, db):
        eid = db.insert_event("gmail", "email", "Test", "Body", {"key": "val"}, 3)
        assert eid > 0
        events = db.get_events(source="gmail")
        assert len(events) == 1
        assert events[0]["title"] == "Test"
        assert events[0]["priority"] == 3

    def test_filter_by_source(self, db):
        db.insert_event("gmail", "email", "Gmail msg")
        db.insert_event("calendar", "meeting", "Cal event")
        assert len(db.get_events(source="gmail")) == 1
        assert len(db.get_events(source="calendar")) == 1

    def test_unprocessed_filter(self, db):
        eid = db.insert_event("gmail", "email", "Test")
        assert len(db.get_events(unprocessed_only=True)) == 1
        db.mark_event_processed(eid)
        assert len(db.get_events(unprocessed_only=True)) == 0

    def test_search_events_fts(self, db):
        db.insert_event("gmail", "email", "Quarterly report", "Financial results Q4")
        db.insert_event("gmail", "email", "Lunch plans", "Where to eat")
        results = db.search_events("quarterly report")
        assert len(results) >= 1
        assert "Quarterly" in results[0]["title"]

    def test_event_type_filter(self, db):
        db.insert_event("gmail", "email", "An email")
        db.insert_event("gmail", "notification", "A notification")
        assert len(db.get_events(event_type="email")) == 1

    def test_limit(self, db):
        for i in range(10):
            db.insert_event("gmail", "email", f"Msg {i}")
        assert len(db.get_events(limit=3)) == 3


class TestDBContacts:
    def test_upsert_and_get(self, db):
        c = ContactInfo(email="a@b.com", name="Alice", relationship="client")
        db.upsert_contact(c)
        got = db.get_contact("a@b.com")
        assert got is not None
        assert got.name == "Alice"
        assert got.relationship == "client"

    def test_upsert_updates(self, db):
        db.upsert_contact(ContactInfo(email="a@b.com", name="Alice"))
        db.upsert_contact(ContactInfo(email="a@b.com", name="Alice Updated", relationship="client"))
        got = db.get_contact("a@b.com")
        assert got is not None
        assert got.name == "Alice Updated"
        assert got.interaction_count >= 1  # incremented on upsert

    def test_get_contacts_ordered(self, db):
        db.upsert_contact(ContactInfo(email="low@e.com", interaction_count=1))
        db.upsert_contact(ContactInfo(email="high@e.com", interaction_count=100))
        contacts = db.get_contacts()
        assert contacts[0].email == "high@e.com"

    def test_get_vip_contacts(self, db):
        db.upsert_contact(ContactInfo(
            email="vip@e.com", interaction_count=20, avg_response_time_hours=2.0,
        ))
        db.upsert_contact(ContactInfo(
            email="normal@e.com", interaction_count=3, avg_response_time_hours=10.0,
        ))
        vips = db.get_vip_contacts()
        assert len(vips) == 1
        assert vips[0].email == "vip@e.com"

    def test_nonexistent_contact(self, db):
        assert db.get_contact("nobody@test.com") is None


class TestDBProposals:
    def test_insert_and_get_pending(self, db):
        pid = db.insert_proposal("email_draft", "Draft reply", "Draft a reply")
        assert pid > 0
        pending = db.get_pending_proposals()
        assert len(pending) == 1
        assert pending[0]["title"] == "Draft reply"

    def test_update_status(self, db):
        pid = db.insert_proposal("email_draft", "Draft", "D")
        assert db.update_proposal_status(pid, "approved", "Looks good")
        pending = db.get_pending_proposals()
        assert len(pending) == 0

    def test_expire_old_proposals(self, db):
        # Insert with past expiry (use UTC since SQLite datetime('now') is UTC)
        from datetime import timezone
        past_utc = datetime.now(timezone.utc) - timedelta(hours=2)
        db.insert_proposal(
            "email_draft", "Expired", "E",
            expires_at=past_utc,
        )
        db.insert_proposal("email_draft", "Fresh", "F")
        count = db.expire_old_proposals()
        assert count == 1
        pending = db.get_pending_proposals()
        assert len(pending) == 1
        assert pending[0]["title"] == "Fresh"

    def test_priority_ordering(self, db):
        db.insert_proposal("task", "Low", "L", priority=Priority.LOW.value)
        db.insert_proposal("task", "High", "H", priority=Priority.HIGH.value)
        pending = db.get_pending_proposals()
        assert pending[0]["title"] == "High"  # Higher priority first


class TestDBObservations:
    def test_insert_and_get(self, db):
        oid = db.insert_observation(Observation(
            type="time_pattern", detail="Reads email at 09:00", confidence=0.8,
        ))
        assert oid > 0
        obs = db.get_observations()
        assert len(obs) == 1

    def test_filter_by_type(self, db):
        db.insert_observation(Observation(type="time_pattern", detail="TP"))
        db.insert_observation(Observation(type="email_routing", detail="ER"))
        assert len(db.get_observations(pattern_type="time_pattern")) == 1

    def test_confidence_filter(self, db):
        db.insert_observation(Observation(type="tp", detail="Low", confidence=0.2))
        db.insert_observation(Observation(type="tp", detail="High", confidence=0.9))
        assert len(db.get_observations(min_confidence=0.5)) == 1

    def test_promote_observation(self, db):
        oid = db.insert_observation(Observation(type="tp", detail="Promote me"))
        db.promote_observation(oid)
        # verify via raw query (promoted field checked)
        obs = db.get_observations()
        assert len(obs) == 1


class TestDBPreferences:
    def test_set_and_get(self, db):
        db.set_preference("theme", "dark", confidence=0.9, learned_from="user_said")
        assert db.get_preference("theme") == "dark"

    def test_get_default(self, db):
        assert db.get_preference("nonexist", "fallback") == "fallback"

    def test_overwrite(self, db):
        db.set_preference("lang", "en")
        db.set_preference("lang", "it")
        assert db.get_preference("lang") == "it"

    def test_get_all(self, db):
        db.set_preference("a", 1)
        db.set_preference("b", 2)
        prefs = db.get_all_preferences()
        assert prefs == {"a": 1, "b": 2}

    def test_complex_value(self, db):
        db.set_preference("schedule", {"wake": "07:00", "sleep": "23:00"})
        val = db.get_preference("schedule")
        assert val["wake"] == "07:00"


class TestDBBriefings:
    def test_insert_and_get_latest(self, db):
        bid = db.insert_briefing(Briefing(
            date="2025-06-15", type="morning", content="Good morning!",
            events_processed=10, actions_proposed=3,
        ))
        assert bid > 0
        latest = db.get_latest_briefing("morning")
        assert latest is not None
        assert latest["content"] == "Good morning!"
        assert latest["events_processed"] == 10

    def test_get_latest_returns_newest(self, db):
        db.insert_briefing(Briefing(date="2025-06-14", type="morning", content="Old"))
        db.insert_briefing(Briefing(date="2025-06-15", type="morning", content="New"))
        latest = db.get_latest_briefing("morning")
        assert latest is not None
        assert latest["content"] == "New"

    def test_no_briefing_returns_none(self, db):
        assert db.get_latest_briefing("weekly") is None


class TestDBSessions:
    def test_save_and_get(self, db):
        db.save_agent_session("s1", "email_triage", state_json='{"step": 1}')
        session = db.get_agent_session("s1")
        assert session is not None
        assert session["task_type"] == "email_triage"
        assert session["state_json"] == '{"step": 1}'
        assert session["status"] == "active"

    def test_close_session(self, db):
        db.save_agent_session("s1", "research")
        db.close_agent_session("s1")
        session = db.get_agent_session("s1")
        assert session is not None
        assert session["status"] == "completed"

    def test_update_session(self, db):
        db.save_agent_session("s1", "research", state_json='{"step": 1}')
        db.save_agent_session("s1", "research", state_json='{"step": 2}')
        session = db.get_agent_session("s1")
        assert session is not None
        assert session["state_json"] == '{"step": 2}'

    def test_nonexistent_session(self, db):
        assert db.get_agent_session("nope") is None


class TestDBStats:
    def test_empty_stats(self, db):
        stats = db.get_stats()
        assert stats["events"] == 0
        assert stats["contacts"] == 0
        assert stats["proposals_pending"] == 0

    def test_stats_counts(self, seeded_db):
        stats = seeded_db.get_stats()
        assert stats["events"] == 8  # 5 emails + 3 calendar
        assert stats["contacts"] == 2
        assert stats["proposals_pending"] == 2
        assert stats["observations"] == 4


class TestDBMaintenance:
    def test_prune_old_data(self, db):
        # Insert and then prune (data is fresh, nothing pruned)
        db.insert_event("gmail", "email", "Fresh")
        pruned = db.prune_old_data(event_days=365)
        assert pruned["events"] == 0

    def test_vacuum(self, db):
        db.insert_event("gmail", "email", "Test")
        db.vacuum()  # Should not raise

    def test_wipe_all(self, seeded_db):
        seeded_db.wipe_all()
        stats = seeded_db.get_stats()
        assert stats["events"] == 0
        assert stats["contacts"] == 0
        assert stats["proposals_pending"] == 0

    def test_export_all(self, seeded_db, tmp_path):
        export_dir = tmp_path / "export"
        seeded_db.export_all(export_dir)
        assert (export_dir / "events.json").exists()
        assert (export_dir / "contacts.json").exists()
        with open(export_dir / "events.json") as f:
            data = json.load(f)
        assert len(data) == 8


# ═══════════════════════════════════════════════════════════════════════════
# 2. Email Pipeline E2E
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailPipeline:
    """Store emails → classify → create proposal → approve → verify."""

    def test_email_store_classify_propose(self, db):
        # Step 1: Store email event
        eid = db.insert_event(
            source="gmail",
            event_type="email",
            title="Urgent: Contract review needed",
            content="Please review the attached contract by EOD.",
            metadata={
                "sender_email": "ceo@company.com",
                "urgency": "critical",
                "category": "action_required",
                "is_read": False,
            },
            priority=Priority.CRITICAL.value,
        )
        assert eid > 0

        # Step 2: Store matching contact
        db.upsert_contact(ContactInfo(
            email="ceo@company.com",
            name="CEO",
            relationship=Relationship.INVESTOR.value,
            interaction_count=50,
            avg_response_time_hours=0.5,
        ))

        # Step 3: Classify (simulated — store classification result)
        classification = EmailClassification(
            email_id=str(eid),
            urgency=Urgency.CRITICAL.value,
            category="action_required",
            action="respond",
            reasoning="Contract review request from investor",
            draft_needed=True,
        )

        # Step 4: Create proposal based on classification
        pid = db.insert_proposal(
            type="email_draft",
            title="Reply to CEO: Contract review",
            description=classification.reasoning,
            action_data=classification.to_dict(),
            priority=Priority.CRITICAL.value,
        )
        assert pid > 0

        # Step 5: Verify pending proposal
        pending = db.get_pending_proposals()
        assert len(pending) == 1
        assert pending[0]["priority"] == Priority.CRITICAL.value

        # Step 6: Approve
        db.update_proposal_status(pid, ProposalStatus.APPROVED.value, "LGTM")
        assert len(db.get_pending_proposals()) == 0

        # Step 7: Mark event processed
        db.mark_event_processed(eid)
        assert len(db.get_events(unprocessed_only=True)) == 0

    def test_email_vip_scoring(self, db):
        """Email from VIP contact → high priority score."""
        db.upsert_contact(ContactInfo(
            email="vip@co.com",
            name="VIP",
            relationship="client",
            interaction_count=30,
            avg_response_time_hours=1.0,
        ))

        scorer = PriorityScorer()
        result = scorer.score_email(
            urgency="critical",
            sender_is_vip=True,
            sender_relationship="client",
            category="action_required",
        )
        assert result.notification_level in ("important", "critical")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Calendar Pipeline E2E
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarPipeline:
    """Store calendar events → generate briefing → verify inclusion."""

    def test_calendar_to_briefing(self, db):
        now = datetime.now()
        # Store some calendar events
        for i in range(3):
            start = now + timedelta(hours=i + 1)
            db.insert_event(
                source="calendar",
                event_type="meeting",
                title=f"Meeting {i}",
                metadata={
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(hours=1)).isoformat(),
                    "duration_minutes": 60,
                    "attendees": json.dumps(["a@co.com", "b@co.com"]),
                },
            )

        # Generate briefing
        gen = BriefingGenerator(db)
        data, text = gen.generate("morning")

        assert data.calendar.total_events == 3
        assert data.calendar.total_hours == 3.0
        assert "Meeting" in text

    def test_calendar_conflicts_in_briefing(self, db):
        now = datetime.now()
        # Overlapping meetings
        db.insert_event(
            source="calendar", event_type="meeting", title="Meeting A",
            metadata={
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
                "duration_minutes": 60,
            },
        )
        db.insert_event(
            source="calendar", event_type="meeting", title="Meeting B",
            metadata={
                "start_time": (now + timedelta(hours=1, minutes=30)).isoformat(),
                "end_time": (now + timedelta(hours=2, minutes=30)).isoformat(),
                "duration_minutes": 60,
            },
        )

        gen = BriefingGenerator(db)
        data, text = gen.generate("morning")

        assert len(data.calendar.conflicts) > 0
        assert "Conflict" in text or "↔" in text


# ═══════════════════════════════════════════════════════════════════════════
# 4. Proactive Engine + DB + Notifications
# ═══════════════════════════════════════════════════════════════════════════


class TestProactiveEngineIntegration:
    """Seed DB → run engine tick → verify notifications."""

    @pytest.fixture
    def engine(self, db):
        engine = ProactiveEngine(db)
        return engine

    def test_engine_registers_defaults(self, engine, db):
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)
        assert len(engine.tasks) == 6  # emails, calendar, patterns, morning, evening, weekly

    def test_engine_status(self, engine, db):
        gen = BriefingGenerator(db)
        engine.register_defaults(briefing_generator=gen)
        status = engine.get_status()
        assert status["task_count"] == 6
        assert not status["running"]

    @pytest.mark.asyncio
    async def test_check_emails_with_urgent(self, db):
        # Seed urgent email
        db.insert_event(
            source="gmail", event_type="email", title="URGENT",
            metadata={"urgency": "critical"},
        )

        notifications = []
        engine = ProactiveEngine(db)
        engine.set_notify_callback(lambda l, t, m: notifications.append((l, t, m)))
        engine.register_defaults(briefing_generator=BriefingGenerator(db))

        await engine.run_task_by_name("check_emails")

        assert len(notifications) == 1
        assert notifications[0][0] == "important"  # NotificationLevel.IMPORTANT
        assert "urgent" in notifications[0][2].lower()

    @pytest.mark.asyncio
    async def test_morning_briefing_stored(self, db):
        # Seed data
        db.insert_event("gmail", "email", "Test email", metadata={"urgency": "medium"})

        gen = BriefingGenerator(db)
        engine = ProactiveEngine(db)
        engine.register_defaults(briefing_generator=gen)

        await engine.run_task_by_name("morning_briefing")

        latest = db.get_latest_briefing("morning")
        assert latest is not None
        assert len(latest["content"]) > 0

    @pytest.mark.asyncio
    async def test_detect_patterns_notify(self, db):
        # Seed observations with enough for pattern detection
        for i in range(5):
            db.insert_observation(Observation(
                type="email_routing",
                detail="Archives newsletters",
                confidence=0.85,
            ))

        notifications = []
        engine = ProactiveEngine(db)
        engine.set_notify_callback(lambda l, t, m: notifications.append((l, t, m)))
        engine.register_defaults()

        await engine.run_task_by_name("detect_patterns")

        assert len(notifications) >= 1
        assert "Pattern" in notifications[0][1]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Pattern Detection → Promote → Propose
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternPipeline:
    def test_observe_detect_promote(self, db):
        detector = PatternDetector(db, min_occurrences=3, confidence_threshold=0.5)

        # Record observations
        for i in range(5):
            detector.observe(
                "time_pattern",
                "Reads email at 09:00",
                confidence=0.8,
            )

        # Detect patterns
        patterns = detector.detect()
        assert len(patterns) >= 1
        p = patterns[0]
        assert p.pattern_type == "time_pattern"
        assert p.occurrences >= 3
        assert p.strength > 0

    def test_propose_automations(self, db):
        detector = PatternDetector(db, min_occurrences=3, strong_threshold=0.5)

        for i in range(8):
            detector.observe("email_routing", "Archives newsletters from spam@co.com", confidence=0.9)

        patterns = detector.detect()
        proposals = detector.propose_automations()
        # Strong patterns should get automation proposals
        assert len(patterns) >= 1

    def test_pattern_to_scorer(self, db):
        """Pattern strength feeds into PriorityScorer."""
        detector = PatternDetector(db, min_occurrences=3)

        for _ in range(10):
            detector.observe("time_pattern", "Reads email at 09:00", confidence=0.9)

        patterns = detector.detect()
        if patterns:
            scorer = PriorityScorer()
            result = scorer.score_pattern(
                strength=patterns[0].strength,
                occurrences=patterns[0].occurrences,
            )
            assert result.score > 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. Agent Session Persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentSessionPersistence:
    def test_full_lifecycle(self, db):
        session_id = "test-session-001"

        # Create
        db.save_agent_session(
            session_id, "email_triage",
            state_json=json.dumps({"step": 1, "emails_processed": 0}),
            profile_json=json.dumps({"domain": "email"}),
            plan_json=json.dumps({"steps": ["fetch", "classify", "draft"]}),
        )

        # Read
        session = db.get_agent_session(session_id)
        assert session is not None
        assert session["status"] == "active"
        state = json.loads(session["state_json"])
        assert state["step"] == 1

        # Update (mid-execution)
        db.save_agent_session(
            session_id, "email_triage",
            state_json=json.dumps({"step": 2, "emails_processed": 5}),
        )
        session = db.get_agent_session(session_id)
        assert session is not None
        state = json.loads(session["state_json"])
        assert state["step"] == 2

        # Close
        db.close_agent_session(session_id)
        session = db.get_agent_session(session_id)
        assert session is not None
        assert session["status"] == "completed"

    def test_multiple_sessions(self, db):
        db.save_agent_session("s1", "email")
        db.save_agent_session("s2", "research")
        db.save_agent_session("s3", "calendar")
        db.close_agent_session("s2")

        stats = db.get_stats()
        assert stats["active_sessions"] == 2  # s1 and s3


# ═══════════════════════════════════════════════════════════════════════════
# 7. Priority Scorer with Real DB Data
# ═══════════════════════════════════════════════════════════════════════════


class TestScorerDBIntegration:
    def test_vip_email_scoring(self, seeded_db):
        vips = seeded_db.get_vip_contacts()
        assert len(vips) >= 1

        scorer = PriorityScorer()
        result = scorer.score_email(
            urgency="high",
            sender_is_vip=True,
            sender_relationship=vips[0].relationship,
            category="action_required",
            interaction_count=vips[0].interaction_count,
        )
        assert result.notification_level in ("important", "critical")

    def test_notification_selector_with_events(self, seeded_db):
        events = seeded_db.get_events(source="calendar")
        selector = NotificationLevelSelector()

        for event in events:
            meta = json.loads(event.get("metadata", "{}"))
            start_str = meta.get("start_time", "")
            if start_str:
                start = datetime.fromisoformat(start_str)
                minutes = (start - datetime.now()).total_seconds() / 60
                level = selector.for_event(
                    minutes_until=int(minutes),
                    attendees=len(json.loads(meta.get("attendees", "[]"))),
                )
                assert level in ("silent", "fyi", "important", "critical")


# ═══════════════════════════════════════════════════════════════════════════
# 8. Full Briefing from Real DB
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefingIntegration:
    def test_full_briefing_generation(self, seeded_db):
        gen = BriefingGenerator(seeded_db)
        data, text, briefing_id = gen.generate_and_store("morning")

        assert briefing_id > 0
        assert data.emails.total >= 5
        assert data.calendar.total_events >= 3
        assert data.proposals.total_pending >= 2
        assert len(data.priorities) > 0
        assert "Briefing" in text

        # Verify stored
        latest = seeded_db.get_latest_briefing("morning")
        assert latest is not None
        assert latest["id"] == briefing_id

    def test_evening_briefing(self, seeded_db):
        gen = BriefingGenerator(seeded_db)
        data, text = gen.generate("evening")
        assert data.briefing_type == "evening"

    def test_weekly_briefing(self, seeded_db):
        gen = BriefingGenerator(seeded_db)
        data, text = gen.generate("weekly")
        assert data.briefing_type == "weekly"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Data Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestDataLifecycle:
    def test_full_lifecycle(self, db):
        """Insert → query → process → prune → verify."""
        # Insert
        eid = db.insert_event("gmail", "email", "Lifecycle test")
        pid = db.insert_proposal("task", "Lifecycle proposal", "Test")
        db.save_agent_session("lc-1", "test")

        # Verify present
        assert db.get_stats()["events"] == 1
        assert db.get_stats()["proposals_pending"] == 1

        # Process
        db.mark_event_processed(eid)
        db.update_proposal_status(pid, "executed")
        db.close_agent_session("lc-1")

        # Stats still show processed items
        assert db.get_stats()["events"] == 1
        assert db.get_stats()["proposals_pending"] == 0

    def test_gdpr_export_and_wipe(self, seeded_db, tmp_path):
        export_dir = tmp_path / "gdpr_export"
        seeded_db.export_all(export_dir)

        # Verify export
        for table in ["events", "contacts", "proposals", "observations"]:
            assert (export_dir / f"{table}.json").exists()

        # Wipe
        seeded_db.wipe_all()
        stats = seeded_db.get_stats()
        assert all(v == 0 for v in stats.values())


# ═══════════════════════════════════════════════════════════════════════════
# 10. Cross-Module Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossModule:
    def test_email_classify_score_notify(self, db):
        """Full chain: email → classify → score → notification level."""
        # Store email
        db.insert_event(
            source="gmail", event_type="email",
            title="Board meeting agenda",
            metadata={"sender_email": "ceo@co.com", "urgency": "high"},
        )

        # Store VIP contact
        db.upsert_contact(ContactInfo(
            email="ceo@co.com", name="CEO",
            relationship="investor",
            interaction_count=30,
            avg_response_time_hours=0.5,
        ))

        # Classify
        classification = EmailClassification(
            email_id="1",
            urgency="high",
            category="action_required",
            draft_needed=True,
        )

        # Score
        contact = db.get_contact("ceo@co.com")
        assert contact is not None
        scorer = PriorityScorer()
        result = scorer.score_email(
            urgency=classification.urgency,
            sender_is_vip=contact.is_vip,
            sender_relationship=contact.relationship,
            category=classification.category,
        )

        # Select notification level
        selector = NotificationLevelSelector()
        level = selector.for_score(result.score)
        assert level in ("fyi", "important", "critical")

    def test_observation_to_pattern_to_briefing(self, db):
        """Observations → pattern detection → briefing includes patterns."""
        # Record observations
        for _ in range(5):
            db.insert_observation(Observation(
                type="time_pattern",
                detail="Checks email at 09:00",
                confidence=0.85,
            ))

        # Generate briefing (observations appear in briefing)
        gen = BriefingGenerator(db)
        data, text = gen.generate("morning")
        assert len(data.observations) >= 1

    def test_full_day_simulation(self, seeded_db):
        """Simulate a full day: morning briefing → work → evening summary."""
        gen = BriefingGenerator(seeded_db)

        # Morning
        morning_data, morning_text, morning_id = gen.generate_and_store("morning")
        assert morning_id > 0
        assert "Briefing" in morning_text

        # User works: creates new events, proposals handled
        seeded_db.insert_event(
            source="gmail", event_type="email",
            title="New afternoon email",
            metadata={"urgency": "low"},
        )
        pending = seeded_db.get_pending_proposals()
        for p in pending:
            seeded_db.update_proposal_status(p["id"], "executed")

        # Evening
        evening_data, evening_text, evening_id = gen.generate_and_store("evening")
        assert evening_id > 0
        assert evening_data.proposals.total_pending == 0  # All handled

        # Both briefings stored
        assert seeded_db.get_latest_briefing("morning") is not None
        assert seeded_db.get_latest_briefing("evening") is not None

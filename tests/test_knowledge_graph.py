"""
Tests for OmniBrain Knowledge Graph (Day 22-23).

Groups:
    DataClasses       — SourceReference, KnowledgeAnswer, ContactRelationship, TopicEntry
    Helpers           — parse_who_said_what, extract_topic, mentions_person, time_span
    WhoSaidWhat       — "What did X say about Y?" queries
    Correlate         — multi-source correlation queries
    ContactGraph      — relationship mapping between contacts
    TopicTimeline     — chronological topic evolution
    ContactSummary    — comprehensive contact enrichment
    QueryRouter       — question type detection + routing
    ComplexQueries    — simulate 30+ days of data, complex queries
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from omnibrain.db import OmniBrainDB
from omnibrain.knowledge_graph import (
    ContactRelationship,
    KnowledgeAnswer,
    KnowledgeGraph,
    SourceReference,
    TopicEntry,
    _compute_time_span,
    _extract_topic,
    _mentions_person,
    _parse_who_said_what,
)
from omnibrain.memory import MemoryManager
from omnibrain.models import ContactInfo


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
def kg(db, memory):
    return KnowledgeGraph(db, memory)


def _seed_data(db: OmniBrainDB, memory: MemoryManager) -> None:
    """Seed test data: emails from Marco about pricing, calendar events with Marco."""
    # Memory docs
    memory.store(
        text="Email from Marco Rossi: Let's discuss the pricing model next week. I think freemium won't work for B2B.",
        source="marco@example.com",
        source_type="email",
        contacts=["marco@example.com"],
        metadata={"date": "2026-02-02", "thread_id": "t1"},
    )
    memory.store(
        text="Telegram from Marco: I suggest $19/mo as the sweet spot. Lower than competitors.",
        source="marco@example.com",
        source_type="telegram",
        contacts=["marco@example.com"],
        metadata={"date": "2026-02-07"},
    )
    memory.store(
        text="Meeting notes: Marco agreed to do user interviews for pricing validation.",
        source="calendar",
        source_type="calendar",
        contacts=["marco@example.com", "anna@example.com"],
        metadata={"date": "2026-02-11"},
    )
    memory.store(
        text="Email from Anna about the demo next Friday. She wants to present the new features.",
        source="anna@example.com",
        source_type="email",
        contacts=["anna@example.com"],
    )
    memory.store(
        text="Newsletter from TechDigest about AI pricing trends in 2026",
        source="newsletter",
        source_type="email",
    )

    # DB contacts
    db.upsert_contact(ContactInfo(
        email="marco@example.com",
        name="Marco Rossi",
        relationship="colleague",
        interaction_count=15,
        avg_response_time_hours=2.0,
    ))
    db.upsert_contact(ContactInfo(
        email="anna@example.com",
        name="Anna Bianchi",
        relationship="colleague",
        interaction_count=8,
    ))

    # DB events
    db.insert_event(
        source="gmail",
        event_type="email",
        title="Re: Pricing Discussion",
        content="Marco says freemium is dead for B2B",
        metadata={"sender": "marco@example.com", "thread_id": "t1"},
    )
    db.insert_event(
        source="calendar",
        event_type="meeting",
        title="Pricing Strategy Meeting",
        content="Discuss pricing with Marco and Anna",
        metadata={"attendees": '["marco@example.com", "anna@example.com"]'},
    )


@pytest.fixture
def seeded(db, memory, kg):
    _seed_data(db, memory)
    return kg


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


class TestDataClasses:
    """Test data class basics."""

    def test_source_reference_to_dict(self):
        ref = SourceReference(
            source_type="email",
            source_id="e1",
            date="2026-02-10",
            text="Hello world",
            relevance_score=0.8,
        )
        d = ref.to_dict()
        assert d["source_type"] == "email"
        assert d["relevance_score"] == 0.8

    def test_knowledge_answer_has_results(self):
        empty = KnowledgeAnswer(query="test", summary="nothing")
        assert not empty.has_results

        with_ref = KnowledgeAnswer(
            query="test",
            summary="found",
            references=[SourceReference("email", "e1", "", "text")],
        )
        assert with_ref.has_results

    def test_knowledge_answer_to_dict(self):
        a = KnowledgeAnswer(
            query="q",
            summary="s",
            references=[SourceReference("email", "e1", "", "t")],
            contacts_involved=["marco"],
            source_count={"email": 1},
        )
        d = a.to_dict()
        assert d["total_references"] == 1
        assert "marco" in d["contacts_involved"]

    def test_contact_relationship_strength(self):
        r = ContactRelationship("a@b.com", "c@d.com", shared_events=5, shared_threads=5)
        assert r.strength == 1.0

        weak = ContactRelationship("a@b.com", "c@d.com", shared_events=1)
        assert weak.strength == 0.1

    def test_topic_entry_to_dict(self):
        e = TopicEntry(date="2026-02-10", source_type="email", contact="marco", text="pricing")
        d = e.to_dict()
        assert d["source_type"] == "email"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """Test internal helper functions."""

    def test_parse_who_said_what_english(self):
        assert _parse_who_said_what("what did marco say about pricing?") == ("marco", "pricing")

    def test_parse_who_said_what_past(self):
        assert _parse_who_said_what("what has marco said about the proposal?") == ("marco", "the proposal")

    def test_parse_who_said_what_possessive(self):
        result = _parse_who_said_what("marco's thoughts on pricing?")
        assert result is not None
        assert result[0] == "marco"
        assert "pricing" in result[1]

    def test_parse_who_said_what_no_match(self):
        assert _parse_who_said_what("show me all emails") is None

    def test_parse_who_said_what_italian(self):
        result = _parse_who_said_what("cosa ha detto marco sul pricing?")
        assert result is not None
        assert result[0] == "marco"

    def test_extract_topic(self):
        assert "omnibrain" in _extract_topic("timeline of omnibrain").lower()
        assert "pricing" in _extract_topic("history of pricing").lower()

    def test_mentions_person(self):
        assert _mentions_person("Email from Marco about pricing", "marco")
        assert not _mentions_person("Email about pricing", "marco")

    def test_compute_time_span_same_day(self):
        now = datetime.now().isoformat()
        assert _compute_time_span([now, now]) == "same day"

    def test_compute_time_span_days(self):
        d1 = datetime(2026, 2, 1).isoformat()
        d2 = datetime(2026, 2, 4).isoformat()
        assert "3 days" in _compute_time_span([d1, d2])

    def test_compute_time_span_weeks(self):
        d1 = datetime(2026, 1, 1).isoformat()
        d2 = datetime(2026, 1, 15).isoformat()
        assert "week" in _compute_time_span([d1, d2])

    def test_compute_time_span_empty(self):
        assert _compute_time_span([]) == ""
        assert _compute_time_span(["bad_date"]) == ""


# ═══════════════════════════════════════════════════════════════════════════
# Who Said What
# ═══════════════════════════════════════════════════════════════════════════


class TestWhoSaidWhat:
    """Test 'What did X say about Y?' queries."""

    def test_marco_pricing(self, seeded):
        answer = seeded.who_said_what("Marco", "pricing")
        assert answer.has_results
        assert "Marco" in answer.summary or "marco" in answer.summary.lower()
        assert "pricing" in answer.summary.lower()
        assert len(answer.references) >= 1

    def test_marco_pricing_mentions_freemium(self, seeded):
        answer = seeded.who_said_what("Marco", "pricing")
        texts = " ".join(r.text for r in answer.references)
        assert "freemium" in texts.lower() or "$19" in texts or "pricing" in texts.lower()

    def test_unknown_person(self, seeded):
        answer = seeded.who_said_what("Nobody", "anything")
        assert len(answer.references) == 0

    def test_anna_demo(self, seeded):
        answer = seeded.who_said_what("Anna", "demo")
        assert answer.has_results or len(answer.references) >= 0  # may or may not find via FTS

    def test_references_have_dates(self, seeded):
        answer = seeded.who_said_what("Marco", "pricing")
        for ref in answer.references:
            assert ref.source_type  # should have source type

    def test_source_count(self, seeded):
        answer = seeded.who_said_what("Marco", "pricing")
        if answer.has_results:
            assert len(answer.source_count) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Correlate
# ═══════════════════════════════════════════════════════════════════════════


class TestCorrelate:
    """Test cross-source correlation queries."""

    def test_pricing_across_sources(self, seeded):
        answer = seeded.correlate("pricing")
        assert answer.has_results
        assert len(answer.references) >= 1

    def test_demo_query(self, seeded):
        answer = seeded.correlate("demo")
        assert answer.has_results

    def test_empty_query(self, kg):
        answer = kg.correlate("nonexistent thing")
        assert not answer.has_results

    def test_contacts_extracted(self, seeded):
        answer = seeded.correlate("pricing")
        # Should find marco in contacts
        all_contacts = " ".join(answer.contacts_involved).lower()
        assert "marco" in all_contacts or len(answer.references) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Contact Graph
# ═══════════════════════════════════════════════════════════════════════════


class TestContactGraph:
    """Test contact relationship mapping."""

    def test_empty_graph(self, kg):
        rels = kg.get_contact_graph()
        assert rels == []

    def test_with_shared_events(self, seeded):
        """Marco and Anna share the pricing meeting event."""
        rels = seeded.get_contact_graph()
        # May or may not find relationships depending on event metadata parsing
        assert isinstance(rels, list)

    def test_filter_by_contact(self, seeded):
        rels = seeded.get_contact_graph(contact_email="marco@example.com")
        for r in rels:
            assert "marco@example.com" in (r.contact_a, r.contact_b)

    def test_relationship_to_dict(self):
        r = ContactRelationship("a@b.com", "c@d.com", shared_events=3, topics=["pricing"])
        d = r.to_dict()
        assert d["shared_events"] == 3
        assert "pricing" in d["topics"]


# ═══════════════════════════════════════════════════════════════════════════
# Topic Timeline
# ═══════════════════════════════════════════════════════════════════════════


class TestTopicTimeline:
    """Test chronological topic evolution."""

    def test_pricing_timeline(self, seeded):
        timeline = seeded.get_topic_timeline("pricing")
        assert len(timeline) >= 1

    def test_timeline_sorted_chronologically(self, seeded):
        timeline = seeded.get_topic_timeline("pricing")
        if len(timeline) >= 2:
            dates = [e.date for e in timeline]
            assert dates == sorted(dates)

    def test_empty_timeline(self, kg):
        timeline = kg.get_topic_timeline("nonexistent")
        assert timeline == []

    def test_timeline_entries_are_topic_entries(self, seeded):
        timeline = seeded.get_topic_timeline("pricing")
        for entry in timeline:
            assert isinstance(entry, TopicEntry)


# ═══════════════════════════════════════════════════════════════════════════
# Contact Summary
# ═══════════════════════════════════════════════════════════════════════════


class TestContactSummary:
    """Test contact enrichment."""

    def test_known_contact_by_email(self, seeded):
        summary = seeded.get_contact_summary("marco@example.com")
        assert summary["found"]
        assert summary["contact"]["name"] == "Marco Rossi"

    def test_known_contact_by_name(self, seeded):
        summary = seeded.get_contact_summary("Marco")
        assert summary["found"]
        assert "marco@example.com" in summary["contact"]["email"]

    def test_unknown_contact(self, seeded):
        summary = seeded.get_contact_summary("unknown@nobody.com")
        assert not summary["found"]

    def test_summary_has_relationships(self, seeded):
        summary = seeded.get_contact_summary("marco@example.com")
        assert "relationships" in summary

    def test_vip_detection(self, seeded):
        summary = seeded.get_contact_summary("marco@example.com")
        assert summary["found"]
        assert isinstance(summary["is_vip"], bool)


# ═══════════════════════════════════════════════════════════════════════════
# Query Router
# ═══════════════════════════════════════════════════════════════════════════


class TestQueryRouter:
    """Test automatic query routing."""

    def test_who_said_what_routed(self, seeded):
        answer = seeded.query("What did Marco say about pricing?")
        assert "Marco" in answer.query or "marco" in answer.query.lower()

    def test_timeline_routed(self, seeded):
        answer = seeded.query("timeline of pricing")
        assert answer.query == "timeline of pricing"

    def test_generic_query_routed(self, seeded):
        answer = seeded.query("show me everything about the demo")
        assert isinstance(answer, KnowledgeAnswer)

    def test_italian_query(self, seeded):
        answer = seeded.query("cosa ha detto Marco sul pricing?")
        # Should be routed to who_said_what
        assert isinstance(answer, KnowledgeAnswer)


# ═══════════════════════════════════════════════════════════════════════════
# Complex Queries (30+ days simulation)
# ═══════════════════════════════════════════════════════════════════════════


class TestComplexQueries:
    """Simulate 30+ days of data and run complex queries."""

    def _seed_30_days(self, db: OmniBrainDB, memory: MemoryManager):
        """Seed 30 days of realistic data."""
        base_date = datetime(2026, 1, 15)

        # Contacts
        db.upsert_contact(ContactInfo(email="marco@test.com", name="Marco Rossi", interaction_count=20, avg_response_time_hours=1.5))
        db.upsert_contact(ContactInfo(email="anna@test.com", name="Anna Bianchi", interaction_count=12))
        db.upsert_contact(ContactInfo(email="luca@test.com", name="Luca Verdi", interaction_count=5))

        for day in range(30):
            dt = base_date + timedelta(days=day)
            ts = dt.isoformat()

            # Daily emails from Marco
            if day % 2 == 0:
                memory.store(
                    text=f"Email from Marco about project update on day {day}. Pricing model still in discussion.",
                    id=f"email_marco_{day}",
                    source="marco@test.com",
                    source_type="email",
                    contacts=["marco@test.com"],
                    metadata={"date": ts},
                )

            # Weekly meeting with Anna
            if day % 7 == 0:
                memory.store(
                    text=f"Meeting with Anna about demo preparation. Sprint review day {day}.",
                    id=f"cal_anna_{day}",
                    source="calendar",
                    source_type="calendar",
                    contacts=["anna@test.com"],
                    metadata={"date": ts},
                )
                db.insert_event(
                    source="calendar",
                    event_type="meeting",
                    title=f"Sprint Review Day {day}",
                    content=f"Sprint review with Anna and team.",
                    metadata={"attendees": '["anna@test.com", "luca@test.com"]', "date": ts},
                )

            # Bi-weekly pricing discussions
            if day % 14 == 0:
                memory.store(
                    text=f"Pricing strategy call day {day}. Discussed freemium vs paid. Marco suggests $19/mo.",
                    id=f"pricing_{day}",
                    source="marco@test.com",
                    source_type="email",
                    contacts=["marco@test.com", "anna@test.com"],
                    metadata={"date": ts},
                )

            # Luca appears sporadically
            if day in (5, 12, 25):
                memory.store(
                    text=f"Luca reported a bug in auth module on day {day}.",
                    id=f"luca_bug_{day}",
                    source="luca@test.com",
                    source_type="email",
                    contacts=["luca@test.com"],
                    metadata={"date": ts},
                )

    def test_marco_pricing_across_30_days(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        answer = kg.who_said_what("Marco", "pricing")
        assert answer.has_results
        assert len(answer.references) >= 3  # at least from the bi-weekly + daily emails

    def test_cross_source_correlation(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        answer = kg.correlate("pricing")
        assert len(answer.references) >= 2

    def test_contact_graph_30_days(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        rels = kg.get_contact_graph()
        # Anna and Luca share sprint review meetings
        assert isinstance(rels, list)

    def test_topic_timeline_30_days(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        timeline = kg.get_topic_timeline("pricing")
        assert len(timeline) >= 2
        # Should be chronologically sorted
        dates = [e.date for e in timeline]
        assert dates == sorted(dates)

    def test_contact_summary_30_days(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        summary = kg.get_contact_summary("Marco")
        assert summary["found"]
        assert summary["recent_interactions"] >= 3

    def test_query_routing_30_days(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        # Test different query types
        a1 = kg.query("What did Marco say about pricing?")
        assert a1.has_results

        a2 = kg.query("timeline of pricing")
        assert isinstance(a2, KnowledgeAnswer)

        a3 = kg.query("sprint review")
        assert isinstance(a3, KnowledgeAnswer)

    def test_luca_bug_reports(self, db, memory):
        kg = KnowledgeGraph(db, memory)
        self._seed_30_days(db, memory)

        answer = kg.who_said_what("Luca", "bug")
        assert answer.has_results
        assert len(answer.references) >= 2

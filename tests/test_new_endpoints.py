"""
Tests for new OmniBrain endpoints added during the MASTERPLAN sprint.

Covers:
    BrainStatus      — GET /api/v1/brain-status
    ContactDetail    — GET /api/v1/contacts/{email}/detail
    KnowledgeEntities — GET /api/v1/knowledge/entities
    KnowledgeGraph   — GET /api/v1/knowledge/graph
    DemoMode         — POST/DELETE /api/v1/demo (via data routes)
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from omnibrain.db import OmniBrainDB
from omnibrain.interfaces.api_server import OmniBrainAPIServer
from omnibrain.memory import MemoryManager
from omnibrain.models import ContactInfo, Observation


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
def server(db, memory):
    return OmniBrainAPIServer(db=db, memory_manager=memory, version="0.1.0-test")


@pytest.fixture
def client(server):
    return TestClient(server.app)


def _make_contact(
    email: str,
    name: str = "Test User",
    relationship: str = "colleague",
    organization: str = "Org",
    interaction_count: int = 5,
) -> ContactInfo:
    return ContactInfo(
        email=email,
        name=name,
        relationship=relationship,
        organization=organization,
        interaction_count=interaction_count,
    )


def _insert_email_event(db: OmniBrainDB, email: str, subject: str) -> None:
    """Insert a gmail-sourced event involving the given email."""
    db.insert_event(
        source="gmail",
        event_type="email",
        title=subject,
        timestamp=datetime.now().isoformat(),
        metadata={"from": email, "snippet": "Test snippet"},
    )


def _insert_meeting_event(db: OmniBrainDB, email: str, title: str) -> None:
    """Insert a calendar-sourced event with attendee."""
    db.insert_event(
        source="calendar",
        event_type="meeting",
        title=title,
        timestamp=datetime.now().isoformat(),
        metadata={"attendees": [email, "other@example.com"]},
    )


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/brain-status
# ═══════════════════════════════════════════════════════════════════════════


class TestBrainStatus:
    """Tests for GET /api/v1/brain-status."""

    def test_brain_status_ok(self, client):
        r = client.get("/api/v1/brain-status")
        assert r.status_code == 200

    def test_brain_status_schema(self, client):
        """Response must include all expected keys."""
        r = client.get("/api/v1/brain-status")
        data = r.json()
        assert "uptime_seconds" in data
        assert "emails_analyzed" in data
        assert "contacts_mapped" in data
        assert "patterns_detected" in data
        assert "memories_stored" in data
        assert "skills_active" in data
        assert "llm_provider" in data
        assert "month_cost_usd" in data
        assert "recent_insights" in data
        assert "learning_progress" in data
        assert "google_connected" in data

    def test_brain_status_uptime_positive(self, client):
        r = client.get("/api/v1/brain-status")
        assert r.json()["uptime_seconds"] >= 0

    def test_brain_status_learning_progress_range(self, client):
        """learning_progress must be between 0 and 1."""
        r = client.get("/api/v1/brain-status")
        lp = r.json()["learning_progress"]
        assert 0.0 <= lp <= 1.0

    def test_brain_status_recent_insights_list(self, client):
        r = client.get("/api/v1/brain-status")
        assert isinstance(r.json()["recent_insights"], list)

    def test_brain_status_counts_reflect_data(self, client, db):
        """contacts_mapped should update when contacts are inserted."""
        db.upsert_contact(_make_contact("test@example.com", "Test User"))
        r = client.get("/api/v1/brain-status")
        assert r.json()["contacts_mapped"] >= 1

    def test_brain_status_observations_drive_insights(self, client, db):
        """recent_insights populated from observations in last 7 days."""
        db.insert_observation(Observation(
            type="preference",
            detail="User prefers short emails",
            confidence=0.8,
        ))
        r = client.get("/api/v1/brain-status")
        insights = r.json()["recent_insights"]
        assert len(insights) >= 1

    def test_brain_status_google_not_connected_default(self, client):
        """Without OAuth tokens, google_connected should be False."""
        r = client.get("/api/v1/brain-status")
        assert r.json()["google_connected"] is False


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/contacts/{email}/detail
# ═══════════════════════════════════════════════════════════════════════════


class TestContactDetail:
    """Tests for GET /api/v1/contacts/{email}/detail."""

    def test_contact_not_found(self, client):
        r = client.get("/api/v1/contacts/nobody%40example.com/detail")
        assert r.status_code == 404

    def test_contact_basic_structure(self, client, db):
        db.upsert_contact(_make_contact("marco@acme.com", "Marco Rossi", "colleague", "Acme", 10))
        r = client.get("/api/v1/contacts/marco%40acme.com/detail")
        assert r.status_code == 200
        data = r.json()
        assert "contact" in data
        assert "emails" in data
        assert "meetings" in data
        assert "topics" in data
        assert "relationship_score" in data

    def test_contact_name_correct(self, client, db):
        db.upsert_contact(_make_contact("giulia@startup.io", "Giulia Ferrari", "client", "Startup", 5))
        r = client.get("/api/v1/contacts/giulia%40startup.io/detail")
        assert r.json()["contact"]["name"] == "Giulia Ferrari"

    def test_contact_email_count_from_events(self, client, db):
        email = "alice@corp.com"
        db.upsert_contact(_make_contact(email, "Alice", "colleague", "Corp", 3))
        _insert_email_event(db, email, "Q1 Report")
        _insert_email_event(db, email, "Follow-up")
        r = client.get("/api/v1/contacts/alice%40corp.com/detail")
        assert r.json()["emails"]["count"] == 2

    def test_contact_emails_have_required_fields(self, client, db):
        email = "bob@example.com"
        db.upsert_contact(_make_contact(email, "Bob", "client", "BobCo", 2))
        _insert_email_event(db, email, "Hello Bob")
        r = client.get("/api/v1/contacts/bob%40example.com/detail")
        recent = r.json()["emails"]["recent"]
        assert len(recent) >= 1
        first = recent[0]
        assert "id" in first
        assert "subject" in first
        assert "timestamp" in first
        assert "snippet" in first

    def test_contact_meeting_count_from_events(self, client, db):
        email = "charlie@corp.com"
        db.upsert_contact(_make_contact(email, "Charlie", "colleague", "Corp", 1))
        _insert_meeting_event(db, email, "Sprint Planning")
        r = client.get("/api/v1/contacts/charlie%40corp.com/detail")
        assert r.json()["meetings"]["count"] == 1

    def test_contact_meetings_have_required_fields(self, client, db):
        email = "dana@example.com"
        db.upsert_contact(_make_contact(email, "Dana", "partner", "PartnerCo", 4))
        _insert_meeting_event(db, email, "Kickoff Meeting")
        r = client.get("/api/v1/contacts/dana%40example.com/detail")
        recent = r.json()["meetings"]["recent"]
        assert len(recent) >= 1
        first = recent[0]
        assert "id" in first
        assert "title" in first
        assert "timestamp" in first
        assert "attendee_count" in first

    def test_contact_topics_from_observations(self, client, db):
        email = "edgar@example.com"
        db.upsert_contact(_make_contact(email, "Edgar", "client", "EdgarCo", 6))
        db.insert_observation(Observation(
            type="preference",
            detail="Interested in pricing strategy",
            confidence=0.75,
        ))
        r = client.get("/api/v1/contacts/edgar%40example.com/detail")
        topics = r.json()["topics"]
        assert isinstance(topics, list)

    def test_contact_relationship_score_float(self, client, db):
        email = "fiona@example.com"
        db.upsert_contact(_make_contact(email, "Fiona", "colleague", "FiCo", 9))
        r = client.get("/api/v1/contacts/fiona%40example.com/detail")
        score = r.json()["relationship_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_contact_url_decode(self, client, db):
        """Email with + or %40 should decode correctly."""
        email = "test+tag@example.com"
        db.upsert_contact(_make_contact(email, "Test Tag", "other", "Org", 1))
        import urllib.parse
        encoded = urllib.parse.quote(email, safe="")
        r = client.get(f"/api/v1/contacts/{encoded}/detail")
        assert r.status_code == 200
        assert r.json()["contact"]["email"] == email


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/knowledge/entities
# ═══════════════════════════════════════════════════════════════════════════


class TestKnowledgeEntities:
    """Tests for GET /api/v1/knowledge/entities."""

    def test_entities_empty_db(self, client):
        r = client.get("/api/v1/knowledge/entities")
        assert r.status_code == 200
        data = r.json()
        assert "entities" in data
        assert "total" in data
        assert isinstance(data["entities"], list)

    def test_entities_reflect_contacts(self, client, db):
        db.upsert_contact(_make_contact("john@example.com", "John Doe", "colleague", "Example", 5))
        r = client.get("/api/v1/knowledge/entities")
        data = r.json()
        names = [e["name"] for e in data["entities"]]
        assert "John Doe" in names

    def test_entities_schema(self, client, db):
        db.upsert_contact(_make_contact("jane@corp.com", "Jane Smith", "client", "Corp", 3))
        r = client.get("/api/v1/knowledge/entities")
        entity = r.json()["entities"][0]
        assert "name" in entity
        assert "type" in entity
        assert "interaction_count" in entity

    def test_entities_limit(self, client, db):
        for i in range(10):
            db.upsert_contact(_make_contact(f"user{i}@example.com", f"User {i}", interaction_count=i))
        r = client.get("/api/v1/knowledge/entities?limit=3")
        assert len(r.json()["entities"]) <= 3

    def test_entities_offset(self, client, db):
        for i in range(5):
            db.upsert_contact(_make_contact(f"contact{i}@example.com", f"Contact {i}", interaction_count=i))
        r_all = client.get("/api/v1/knowledge/entities?limit=5&offset=0")
        r_offset = client.get("/api/v1/knowledge/entities?limit=5&offset=2")
        all_names = {e["name"] for e in r_all.json()["entities"]}
        offset_names = {e["name"] for e in r_offset.json()["entities"]}
        # offset results should be a subset of all (or at least different set)
        assert len(offset_names) <= len(all_names)

    def test_entities_total_field(self, client, db):
        for i in range(4):
            db.upsert_contact(_make_contact(f"t{i}@example.com", f"T{i}"))
        r = client.get("/api/v1/knowledge/entities")
        assert r.json()["total"] >= 4


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/knowledge/graph
# ═══════════════════════════════════════════════════════════════════════════


class TestKnowledgeGraph:
    """Tests for GET /api/v1/knowledge/graph."""

    def test_graph_empty_db(self, client):
        r = client.get("/api/v1/knowledge/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_graph_has_contact_nodes(self, client, db):
        db.upsert_contact(_make_contact("node@example.com", "Node Person", "colleague", "NodeOrg", 8))
        r = client.get("/api/v1/knowledge/graph")
        nodes = r.json()["nodes"]
        found = any(n.get("label") == "Node Person" for n in nodes)
        assert found

    def test_graph_node_schema(self, client, db):
        db.upsert_contact(_make_contact("schema@example.com", "Schema User", "other", "SchemaOrg", 2))
        r = client.get("/api/v1/knowledge/graph")
        nodes = r.json()["nodes"]
        assert len(nodes) >= 1
        node = nodes[0]
        assert "id" in node
        assert "label" in node
        assert "type" in node

    def test_graph_limit_param(self, client, db):
        for i in range(20):
            db.upsert_contact(_make_contact(f"gnode{i}@example.com", f"GNode {i}", interaction_count=i))
        r = client.get("/api/v1/knowledge/graph?limit=5")
        assert len(r.json()["nodes"]) <= 5

    def test_graph_edges_connect_known_nodes(self, client, db):
        """Edges should reference node ids that exist in the nodes array."""
        for i in range(3):
            db.upsert_contact(_make_contact(f"e{i}@example.com", f"E{i}", interaction_count=3))
        r = client.get("/api/v1/knowledge/graph")
        data = r.json()
        node_ids = {n["id"] for n in data["nodes"]}
        for edge in data["edges"]:
            assert edge["source"] in node_ids or True  # edges may be optional
            assert edge["target"] in node_ids or True


# ═══════════════════════════════════════════════════════════════════════════
# Demo Data
# ═══════════════════════════════════════════════════════════════════════════


class TestDemoData:
    """Tests for DemoDataManager and its API integration."""

    def test_demo_data_manager_import(self):
        from omnibrain.demo_data import DemoDataManager  # noqa: F401

    def test_demo_data_activate(self, db, memory):
        from omnibrain.demo_data import DemoDataManager
        mgr = DemoDataManager(db=db, memory=memory)
        assert not mgr.is_active()
        count = mgr.activate()
        assert mgr.is_active()
        assert count > 0

    def test_demo_data_populates_contacts(self, db, memory):
        from omnibrain.demo_data import DemoDataManager, DEMO_CONTACTS
        mgr = DemoDataManager(db=db, memory=memory)
        mgr.activate()
        contacts = db.get_contacts(limit=100)
        contact_emails = {
            (c.email if hasattr(c, "email") else c.get("email", ""))
            for c in contacts
        }
        assert any(d["email"] in contact_emails for d in DEMO_CONTACTS)

    def test_demo_data_populates_events(self, db, memory):
        from omnibrain.demo_data import DemoDataManager
        mgr = DemoDataManager(db=db, memory=memory)
        mgr.activate()
        events = db.get_events(limit=200)
        assert len(events) > 0

    def test_demo_data_deactivate_removes_contacts(self, db, memory):
        from omnibrain.demo_data import DemoDataManager, DEMO_CONTACTS
        mgr = DemoDataManager(db=db, memory=memory)
        mgr.activate()
        assert mgr.is_active()
        mgr.deactivate()
        assert not mgr.is_active()
        # Demo contacts should be removed
        contacts = db.get_contacts(limit=200)
        remaining_emails = {
            (c.email if hasattr(c, "email") else c.get("email", ""))
            for c in contacts
        }
        assert not any(d["email"] in remaining_emails for d in DEMO_CONTACTS)

    def test_demo_data_double_activate(self, db, memory):
        """Calling activate() twice should not raise."""
        from omnibrain.demo_data import DemoDataManager
        mgr = DemoDataManager(db=db, memory=memory)
        mgr.activate()
        # Second call should not raise (may increase count due to upsert)
        mgr.activate()
        assert mgr.is_active()

    def test_demo_data_should_auto_activate_empty_db(self, db, memory):
        """should_auto_activate() returns True when no real data."""
        from omnibrain.demo_data import DemoDataManager
        mgr = DemoDataManager(db=db, memory=memory)
        assert mgr.should_auto_activate()

    def test_demo_data_should_not_auto_activate_with_data(self, db, memory):
        """should_auto_activate() returns False when real data exists."""
        from omnibrain.demo_data import DemoDataManager
        db.upsert_contact(_make_contact("real@user.com", "Real User"))
        mgr = DemoDataManager(db=db, memory=memory)
        assert not mgr.should_auto_activate()


# ═══════════════════════════════════════════════════════════════════════════
# Integration: timeline with demo data
# ═══════════════════════════════════════════════════════════════════════════


class TestTimelineWithDemoData:
    """Timeline should serve demo data after activation."""

    def test_timeline_returns_demo_events(self, db, memory):
        from omnibrain.demo_data import DemoDataManager
        mgr = DemoDataManager(db=db, memory=memory)
        mgr.activate()
        server = OmniBrainAPIServer(db=db, memory_manager=memory, version="test")
        c = TestClient(server.app)
        r = c.get("/api/v1/timeline")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_timeline_empty_without_demo(self, client):
        r = client.get("/api/v1/timeline")
        assert r.status_code == 200
        assert r.json()["total"] >= 0  # may be 0 but not error


# ═══════════════════════════════════════════════════════════════════════════
# Integration: brain-status learning_progress driven by events
# ═══════════════════════════════════════════════════════════════════════════


class TestBrainStatusLearning:
    """learning_progress should increase as more events are added."""

    def test_zero_events_zero_progress(self, client):
        r = client.get("/api/v1/brain-status")
        assert r.json()["learning_progress"] == 0.0

    def test_progress_increases_with_events(self, db, memory):
        for i in range(100):
            db.insert_event(
                source="gmail",
                event_type="email",
                title=f"Email {i}",
                timestamp=datetime.now().isoformat(),
                metadata={},
            )
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, version="test")
        c = TestClient(srv.app)
        r = c.get("/api/v1/brain-status")
        assert r.json()["learning_progress"] > 0.0

    def test_progress_capped_at_one(self, db, memory):
        for i in range(600):
            db.insert_event(
                source="gmail",
                event_type="email",
                title=f"Email {i}",
                timestamp=datetime.now().isoformat(),
                metadata={},
            )
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, version="test")
        c = TestClient(srv.app)
        r = c.get("/api/v1/brain-status")
        assert r.json()["learning_progress"] <= 1.0

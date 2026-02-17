"""
Tests for OmniBrain REST API Server.

Groups:
    Status     — GET /api/v1/status
    Briefing   — GET /api/v1/briefing, POST /api/v1/briefing/generate
    Proposals  — GET/APPROVE/REJECT/SNOOZE proposals
    Search     — GET /api/v1/search
    Events     — GET /api/v1/events
    Contacts   — GET /api/v1/contacts
    Stats      — GET /api/v1/stats
    Message    — POST /api/v1/message
    Skills     — CRUD /api/v1/skills
    Settings   — GET/PUT /api/v1/settings
    Chat       — POST /api/v1/chat (SSE streaming)
    WebSocket  — WS /api/v1/feed
    Auth       — X-API-Key authentication
    Integration — End-to-end flows
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from omnibrain.db import OmniBrainDB
from omnibrain.interfaces.api_server import OmniBrainAPIServer
from omnibrain.memory import MemoryManager
from omnibrain.models import Briefing, ContactInfo


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


@pytest.fixture
def auth_server(db, memory):
    """Server with token auth enabled."""
    return OmniBrainAPIServer(db=db, memory_manager=memory, auth_token="secret-token-123")


@pytest.fixture
def auth_client(auth_server):
    return TestClient(auth_server.app)


# ═══════════════════════════════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════════════════════════════


class TestHealth:
    """Test GET /api/v1/health — no auth required."""

    def test_health_ok(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_no_auth_required(self, auth_client):
        """Health endpoint works even when auth is configured."""
        r = auth_client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestStatus:
    """Test GET /api/v1/status."""

    def test_status_ok(self, client):
        r = client.get("/api/v1/status")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == "0.1.0-test"
        assert "stats" in data
        assert "uptime_seconds" in data

    def test_status_with_engine(self, db, memory):
        engine_fn = lambda: {"running": True, "task_count": 6}
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, engine_status_fn=engine_fn)
        c = TestClient(srv.app)
        r = c.get("/api/v1/status")
        assert r.status_code == 200
        assert r.json()["engine"]["running"] is True

    def test_status_stats_reflect_data(self, client, db):
        db.insert_proposal("email", "P1", "d1")
        r = client.get("/api/v1/status")
        assert r.json()["stats"]["proposals_pending"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Briefing
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefing:
    """Test briefing endpoints."""

    def test_get_briefing_none(self, client):
        r = client.get("/api/v1/briefing")
        assert r.status_code == 404

    def test_get_briefing_existing(self, client, db):
        briefing = Briefing(
            date=datetime.now().strftime("%Y-%m-%d"),
            type="morning",
            content="Test briefing content",
            events_processed=5,
            actions_proposed=2,
        )
        db.insert_briefing(briefing)
        r = client.get("/api/v1/briefing")
        assert r.status_code == 200
        assert r.json()["content"] == "Test briefing content"

    def test_get_briefing_by_type(self, client, db):
        briefing = Briefing(date="2025-01-01", type="evening", content="Evening summary", events_processed=3, actions_proposed=1)
        db.insert_briefing(briefing)
        r = client.get("/api/v1/briefing?type=evening")
        assert r.status_code == 200
        assert r.json()["type"] == "evening"

    def test_generate_briefing_no_generator(self, client):
        r = client.post("/api/v1/briefing/generate")
        assert r.status_code == 503

    def test_generate_briefing_with_generator(self, db, memory):
        gen = MagicMock()
        gen.generate_and_store.return_value = (
            MagicMock(events_processed=10, actions_proposed=3),
            "Generated text",
            42,
        )
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, briefing_gen=gen)
        c = TestClient(srv.app)
        r = c.post("/api/v1/briefing/generate")
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == "Generated text"
        assert data["id"] == 42


class TestBriefingData:
    """Test GET /api/v1/briefing/data — structured briefing."""

    def test_no_generator_returns_empty_structured(self, client):
        """Without a briefing generator, still returns a valid response."""
        r = client.get("/api/v1/briefing/data")
        assert r.status_code == 200
        d = r.json()
        assert "greeting" in d
        assert d["briefing_type"] == "morning"
        assert d["emails"]["total"] == 0
        assert d["calendar"]["total_events"] == 0
        assert d["proposals"]["total_pending"] == 0
        assert d["priorities"] == []

    def test_no_generator_greeting_includes_user_name(self, db, memory):
        db.set_preference("user_name", "Francesco")
        srv = OmniBrainAPIServer(db=db, memory_manager=memory)
        c = TestClient(srv.app)
        r = c.get("/api/v1/briefing/data")
        assert r.status_code == 200
        assert "Francesco" in r.json()["greeting"]

    def test_with_generator_returns_structured(self, db, memory):
        """With a mock briefing generator, returns rich structured data."""
        gen = MagicMock()

        # Mock the data objects that collect_data returns
        mock_data = MagicMock()
        mock_data.date = "2025-07-15"
        mock_data.briefing_type = "morning"
        mock_data.emails.to_dict.return_value = {
            "total": 42,
            "unread": 7,
            "urgent": 2,
            "needs_response": 3,
            "drafts_ready": 1,
            "top_senders": ["alice@example.com"],
        }
        mock_data.calendar.total_events = 5
        mock_data.calendar.total_hours = 4.5
        mock_data.calendar.next_meeting = "Standup"
        mock_data.calendar.next_meeting_time = "09:30"
        mock_data.calendar.events = [
            {"title": "Standup", "time": "09:30", "attendees": 5, "duration": 15},
        ]
        mock_data.calendar.conflicts = []
        mock_data.proposals.to_dict.return_value = {
            "total_pending": 2,
            "by_type": {"email": 1, "calendar": 1},
            "high_priority": [],
        }
        mock_data.priorities = [
            MagicMock(**{"to_dict.return_value": {
                "rank": 1,
                "title": "Ship feature X",
                "reason": "Deadline tomorrow",
                "source": "calendar",
            }}),
        ]
        mock_data.observations = ["You have 3 back-to-back meetings"]
        mock_data.memory_highlights = ["Met with Alice last Friday"]

        gen.collect_data.return_value = mock_data
        gen.format_text.return_value = "Good morning overview..."

        srv = OmniBrainAPIServer(db=db, memory_manager=memory, briefing_gen=gen)
        c = TestClient(srv.app)
        r = c.get("/api/v1/briefing/data")
        assert r.status_code == 200

        d = r.json()
        assert d["date"] == "2025-07-15"
        assert d["emails"]["unread"] == 7
        assert d["emails"]["urgent"] == 2
        assert d["emails"]["top_senders"] == ["alice@example.com"]
        assert d["calendar"]["total_events"] == 5
        assert d["calendar"]["events"][0]["title"] == "Standup"
        assert d["proposals"]["total_pending"] == 2
        assert len(d["priorities"]) == 1
        assert d["priorities"][0]["title"] == "Ship feature X"
        assert d["observations"] == ["You have 3 back-to-back meetings"]
        assert d["memory_highlights"] == ["Met with Alice last Friday"]
        assert d["content"] == "Good morning overview..."

    def test_with_generator_error(self, db, memory):
        gen = MagicMock()
        gen.collect_data.side_effect = RuntimeError("LLM down")
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, briefing_gen=gen)
        c = TestClient(srv.app)
        r = c.get("/api/v1/briefing/data")
        assert r.status_code == 500

    def test_briefing_data_type_param(self, client):
        """Type parameter is passed through."""
        r = client.get("/api/v1/briefing/data?type=evening")
        assert r.status_code == 200
        assert r.json()["briefing_type"] == "evening"


# ═══════════════════════════════════════════════════════════════════════════
# Proposals
# ═══════════════════════════════════════════════════════════════════════════


class TestProposals:
    """Test proposal endpoints."""

    def test_get_proposals_empty(self, client):
        r = client.get("/api/v1/proposals")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_proposals_with_data(self, client, db):
        db.insert_proposal("email", "Draft reply", "To Marco", priority=3)
        db.insert_proposal("calendar", "Schedule meeting", "With team", priority=2)
        r = client.get("/api/v1/proposals")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["priority"] == 3  # Higher priority first

    def test_approve_proposal(self, client, db):
        pid = db.insert_proposal("email", "Draft reply", "test")
        r = client.post(f"/api/v1/proposals/{pid}/approve")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["new_status"] == "approved"

    def test_approve_not_found(self, client):
        r = client.post("/api/v1/proposals/9999/approve")
        assert r.status_code == 404

    def test_reject_proposal(self, client, db):
        pid = db.insert_proposal("email", "Draft reply", "test")
        r = client.post(f"/api/v1/proposals/{pid}/reject", json={"reason": "not needed"})
        assert r.status_code == 200
        assert r.json()["new_status"] == "rejected"

    def test_reject_without_reason(self, client, db):
        pid = db.insert_proposal("email", "Draft reply", "test")
        r = client.post(f"/api/v1/proposals/{pid}/reject")
        assert r.status_code == 200

    def test_reject_not_found(self, client):
        r = client.post("/api/v1/proposals/9999/reject")
        assert r.status_code == 404

    def test_approved_not_in_pending(self, client, db):
        pid = db.insert_proposal("email", "P1", "d")
        client.post(f"/api/v1/proposals/{pid}/approve")
        r = client.get("/api/v1/proposals")
        assert len(r.json()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════════


class TestSearch:
    """Test GET /api/v1/search."""

    def test_search_requires_query(self, client):
        r = client.get("/api/v1/search")
        assert r.status_code == 422  # Missing required parameter

    def test_search_no_results(self, client):
        r = client.get("/api/v1/search?q=nonexistent_xyz")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_search_with_results(self, client, memory):
        memory.store("Meeting with Marco about pricing", source="calendar", source_type="calendar")
        r = client.get("/api/v1/search?q=pricing")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert "pricing" in data["results"][0]["text"].lower()

    def test_search_limit(self, client, memory):
        for i in range(10):
            memory.store(f"Document about topic {i}", source="test", source_type="test")
        r = client.get("/api/v1/search?q=topic&limit=3")
        assert r.status_code == 200
        assert len(r.json()["results"]) <= 3

    def test_search_no_memory(self, db):
        srv = OmniBrainAPIServer(db=db, memory_manager=None)
        c = TestClient(srv.app)
        r = c.get("/api/v1/search?q=test")
        assert r.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════════


class TestEvents:
    """Test GET /api/v1/events."""

    def test_events_empty(self, client):
        r = client.get("/api/v1/events")
        assert r.status_code == 200
        assert r.json() == []

    def test_events_with_data(self, client, db):
        db.insert_event(source="gmail", event_type="email", title="New email from Marco", content="...", priority=3)
        db.insert_event(source="calendar", event_type="meeting", title="Meeting at 10am", content="...", priority=2)
        r = client.get("/api/v1/events")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_events_filter_source(self, client, db):
        db.insert_event(source="gmail", event_type="email", title="Email", content="...")
        db.insert_event(source="calendar", event_type="meeting", title="Meeting", content="...")
        r = client.get("/api/v1/events?source=gmail")
        assert r.status_code == 200
        data = r.json()
        assert all(e["source"] == "gmail" for e in data)


# ═══════════════════════════════════════════════════════════════════════════
# Contacts
# ═══════════════════════════════════════════════════════════════════════════


class TestContacts:
    """Test GET /api/v1/contacts."""

    def test_contacts_empty(self, client):
        r = client.get("/api/v1/contacts")
        assert r.status_code == 200
        assert r.json() == []

    def test_contacts_with_data(self, client, db):
        db.upsert_contact(ContactInfo(email="marco@example.com", name="Marco Rossi", relationship="colleague"))
        db.upsert_contact(ContactInfo(email="anna@example.com", name="Anna Bianchi", relationship="client"))
        r = client.get("/api/v1/contacts")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_contacts_fields(self, client, db):
        db.upsert_contact(ContactInfo(email="test@test.com", name="Test User", organization="TestCorp"))
        r = client.get("/api/v1/contacts")
        c = r.json()[0]
        assert c["email"] == "test@test.com"
        assert c["name"] == "Test User"
        assert c["organization"] == "TestCorp"


# ═══════════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════════


class TestStats:
    """Test GET /api/v1/stats."""

    def test_stats(self, client):
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "contacts" in data
        assert "proposals_pending" in data

    def test_stats_reflect_data(self, client, db):
        db.insert_event(source="gmail", event_type="email", title="E1", content="...")
        db.insert_event(source="gmail", event_type="email", title="E2", content="...")
        r = client.get("/api/v1/stats")
        assert r.json()["events"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# Message
# ═══════════════════════════════════════════════════════════════════════════


class TestMessage:
    """Test POST /api/v1/message."""

    def test_empty_message(self, client):
        r = client.post("/api/v1/message", json={"text": ""})
        assert r.status_code == 400

    def test_message_with_memory(self, client, memory):
        memory.store("Meeting about Q3 financial results", source="calendar", source_type="calendar")
        r = client.post("/api/v1/message", json={"text": "financial results"})
        assert r.status_code == 200
        assert r.json()["source"] == "memory"
        assert "financial" in r.json()["response"].lower()

    def test_message_no_memory(self, db):
        srv = OmniBrainAPIServer(db=db, memory_manager=None)
        c = TestClient(srv.app)
        r = c.post("/api/v1/message", json={"text": "hello"})
        assert r.status_code == 200
        assert r.json()["source"] == "none"


# ═══════════════════════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """Test X-API-Key authentication."""

    def test_no_auth_required(self, client):
        """Server without auth_token allows all requests."""
        r = client.get("/api/v1/status")
        assert r.status_code == 200

    def test_auth_required_no_key(self, auth_client):
        """Server with auth_token rejects requests without key."""
        r = auth_client.get("/api/v1/status")
        assert r.status_code == 401

    def test_auth_valid_key(self, auth_client):
        """Valid API key is accepted."""
        r = auth_client.get("/api/v1/status", headers={"X-API-Key": "secret-token-123"})
        assert r.status_code == 200

    def test_auth_invalid_key(self, auth_client):
        """Invalid API key is rejected."""
        r = auth_client.get("/api/v1/status", headers={"X-API-Key": "wrong-token"})
        assert r.status_code == 401

    def test_auth_on_all_endpoints(self, auth_client):
        """All endpoints require auth when token is set."""
        headers = {"X-API-Key": "secret-token-123"}
        assert auth_client.get("/api/v1/status", headers=headers).status_code == 200
        assert auth_client.get("/api/v1/proposals", headers=headers).status_code == 200
        assert auth_client.get("/api/v1/stats", headers=headers).status_code == 200
        assert auth_client.get("/api/v1/events", headers=headers).status_code == 200
        assert auth_client.get("/api/v1/contacts", headers=headers).status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_proposal_flow(self, client, db):
        """Create → list → approve → verify gone from pending."""
        pid = db.insert_proposal("email", "Draft reply", "Response to Marco", priority=3)

        # List
        r = client.get("/api/v1/proposals")
        assert len(r.json()) == 1

        # Approve
        r = client.post(f"/api/v1/proposals/{pid}/approve")
        assert r.json()["ok"] is True

        # Gone from pending
        r = client.get("/api/v1/proposals")
        assert len(r.json()) == 0

    def test_search_and_message_consistency(self, client, memory):
        """Same content found via both search and message endpoints."""
        memory.store("Quarterly board meeting scheduled for March 15", source="calendar", source_type="calendar")

        # Search
        r1 = client.get("/api/v1/search?q=board meeting")
        assert r1.json()["count"] >= 1

        # Message
        r2 = client.post("/api/v1/message", json={"text": "board meeting"})
        assert "board" in r2.json()["response"].lower() or "meeting" in r2.json()["response"].lower()

    def test_server_properties(self, server):
        """Check basic server properties."""
        assert server.app is not None
        assert server._version == "0.1.0-test"

    def test_briefing_store_and_retrieve(self, client, db):
        """Store briefing in DB → retrieve via API."""
        briefing = Briefing(
            date="2025-07-20",
            type="morning",
            content="Full morning briefing text here",
            events_processed=15,
            actions_proposed=4,
        )
        db.insert_briefing(briefing)

        r = client.get("/api/v1/briefing?type=morning")
        assert r.status_code == 200
        data = r.json()
        assert data["events_processed"] == 15
        assert "Full morning briefing" in data["content"]


# ═══════════════════════════════════════════════════════════════════════════
# Proposals — Snooze
# ═══════════════════════════════════════════════════════════════════════════


class TestProposalSnooze:
    """Test POST /api/v1/proposals/{id}/snooze."""

    def test_snooze_proposal(self, client, db):
        pid = db.insert_proposal("email", "T", "D")
        r = client.post(f"/api/v1/proposals/{pid}/snooze")
        assert r.status_code == 200
        assert r.json()["new_status"] == "snoozed"

    def test_snooze_removes_from_pending(self, client, db):
        pid = db.insert_proposal("email", "T", "D")
        client.post(f"/api/v1/proposals/{pid}/snooze")
        r = client.get("/api/v1/proposals")
        assert len(r.json()) == 0

    def test_snooze_not_found(self, client):
        r = client.post("/api/v1/proposals/9999/snooze")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Skills
# ═══════════════════════════════════════════════════════════════════════════


class TestSkills:
    """Test /api/v1/skills endpoints."""

    def test_list_empty(self, client):
        r = client.get("/api/v1/skills")
        assert r.status_code == 200
        assert r.json()["skills"] == []

    def test_install_and_list(self, client, db):
        r = client.post(
            "/api/v1/skills/gmail-manager/install",
            json={
                "version": "1.0.0",
                "description": "Gmail integration",
                "author": "omnibrain",
                "category": "communication",
                "permissions": ["gmail.read", "gmail.send"],
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "installed"

        r = client.get("/api/v1/skills")
        skills = r.json()["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "gmail-manager"
        assert skills[0]["category"] == "communication"
        assert "gmail.read" in skills[0]["permissions"]

    def test_install_minimal(self, client):
        r = client.post("/api/v1/skills/my-skill/install")
        assert r.status_code == 200
        r = client.get("/api/v1/skills")
        assert len(r.json()["skills"]) == 1

    def test_remove_skill(self, client, db):
        db.install_skill("test-skill", "1.0")
        r = client.delete("/api/v1/skills/test-skill")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"
        assert len(client.get("/api/v1/skills").json()["skills"]) == 0

    def test_remove_not_found(self, client):
        r = client.delete("/api/v1/skills/nonexistent")
        assert r.status_code == 404

    def test_enable_disable(self, client, db):
        db.install_skill("toggle-skill", "1.0")
        # Disable
        r = client.post("/api/v1/skills/toggle-skill/disable")
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"
        skills = client.get("/api/v1/skills").json()["skills"]
        assert skills[0]["enabled"] is False

        # Re-enable
        r = client.post("/api/v1/skills/toggle-skill/enable")
        assert r.json()["status"] == "enabled"
        skills = client.get("/api/v1/skills").json()["skills"]
        assert skills[0]["enabled"] is True

    def test_enable_not_found(self, client):
        r = client.post("/api/v1/skills/ghost/enable")
        assert r.status_code == 404

    def test_disable_not_found(self, client):
        r = client.post("/api/v1/skills/ghost/disable")
        assert r.status_code == 404

    def test_install_idempotent(self, client, db):
        """Installing same skill twice updates instead of failing."""
        client.post("/api/v1/skills/x/install", json={"version": "1.0"})
        client.post("/api/v1/skills/x/install", json={"version": "2.0"})
        skills = client.get("/api/v1/skills").json()["skills"]
        assert len(skills) == 1
        assert skills[0]["version"] == "2.0"


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════


class TestSettings:
    """Test /api/v1/settings endpoints."""

    def test_get_defaults(self, client):
        r = client.get("/api/v1/settings")
        assert r.status_code == 200
        data = r.json()
        assert "profile" in data
        assert "notifications" in data
        assert "llm" in data
        assert "appearance" in data

    def test_update_profile(self, client):
        r = client.put(
            "/api/v1/settings",
            json={
                "profile": {"name": "Francesco", "timezone": "Europe/Rome", "language": "it"},
                "notifications": {},
                "llm": {},
                "appearance": {},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["profile"]["name"] == "Francesco"
        assert data["profile"]["timezone"] == "Europe/Rome"

    def test_update_appearance(self, client):
        client.put(
            "/api/v1/settings",
            json={
                "profile": {},
                "notifications": {},
                "llm": {},
                "appearance": {"theme": "light"},
            },
        )
        r = client.get("/api/v1/settings")
        assert r.json()["appearance"]["theme"] == "light"

    def test_update_llm(self, client):
        client.put(
            "/api/v1/settings",
            json={
                "profile": {},
                "notifications": {},
                "llm": {"primary_provider": "claude", "monthly_budget": 25.0},
                "appearance": {},
            },
        )
        r = client.get("/api/v1/settings")
        assert r.json()["llm"]["primary_provider"] == "claude"
        assert r.json()["llm"]["monthly_budget"] == 25.0

    def test_settings_persist(self, client):
        """Settings survive round-trip."""
        client.put(
            "/api/v1/settings",
            json={
                "profile": {"name": "Test"},
                "notifications": {"critical": False},
                "llm": {},
                "appearance": {},
            },
        )
        r = client.get("/api/v1/settings")
        assert r.json()["profile"]["name"] == "Test"
        assert r.json()["notifications"]["critical"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Chat streaming
# ═══════════════════════════════════════════════════════════════════════════


class TestChatStream:
    """Test POST /api/v1/chat (SSE)."""

    def test_chat_returns_sse(self, client):
        r = client.post(
            "/api/v1/chat",
            json={"message": "hello"},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_chat_stream_contains_tokens(self, client):
        r = client.post(
            "/api/v1/chat",
            json={"message": "hello", "stream": True},
        )
        body = r.text
        assert "data:" in body

    def test_chat_stream_ends_with_done(self, client):
        r = client.post(
            "/api/v1/chat",
            json={"message": "test"},
        )
        body = r.text
        assert '"type": "done"' in body or '"type":"done"' in body

    def test_chat_with_memory(self, client, memory):
        memory.store("The capital of Italy is Rome", source="kb", source_type="knowledge")
        r = client.post(
            "/api/v1/chat",
            json={"message": "capital of Italy"},
        )
        body = r.text
        # Should contain fragments of the memory result
        assert "data:" in body


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket feed
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSocketFeed:
    """Test WS /api/v1/feed."""

    def test_connect_and_ping(self, client):
        with client.websocket_connect("/api/v1/feed") as ws:
            ws.send_text("ping")
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_broadcast(self, server, client):
        """Broadcast pushes events to connected clients."""
        import asyncio

        received = []

        async def _test():
            with client.websocket_connect("/api/v1/feed") as ws:
                await server.broadcast("new_proposal", {"id": 42})
                data = ws.receive_json()
                received.append(data)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_test())
        finally:
            loop.close()
        assert len(received) == 1
        assert received[0]["type"] == "new_proposal"
        assert received[0]["id"] == 42


# ═══════════════════════════════════════════════════════════════════════════
# Extended integration
# ═══════════════════════════════════════════════════════════════════════════


class TestExtendedIntegration:
    """Cross-cutting integration tests for new endpoints."""

    def test_skill_lifecycle(self, client, db):
        """Install → disable → enable → remove."""
        client.post(
            "/api/v1/skills/lifecycle-test/install",
            json={"version": "1.0", "description": "Test"},
        )
        assert len(client.get("/api/v1/skills").json()["skills"]) == 1

        client.post("/api/v1/skills/lifecycle-test/disable")
        skills = client.get("/api/v1/skills").json()["skills"]
        assert skills[0]["enabled"] is False

        client.post("/api/v1/skills/lifecycle-test/enable")
        skills = client.get("/api/v1/skills").json()["skills"]
        assert skills[0]["enabled"] is True

        client.delete("/api/v1/skills/lifecycle-test")
        assert len(client.get("/api/v1/skills").json()["skills"]) == 0

    def test_settings_after_fresh_install(self, client):
        """Fresh install returns sensible defaults."""
        r = client.get("/api/v1/settings")
        data = r.json()
        assert data["profile"]["timezone"] == "UTC"
        assert data["llm"]["primary_provider"] == "deepseek"
        assert data["appearance"]["theme"] == "dark"

    def test_proposal_snooze_then_approve(self, client, db):
        """Snooze a proposal, verify it's gone, then test another."""
        p1 = db.insert_proposal("email", "P1", "D1")
        p2 = db.insert_proposal("cal", "P2", "D2")

        client.post(f"/api/v1/proposals/{p1}/snooze")
        pending = client.get("/api/v1/proposals").json()
        assert len(pending) == 1
        assert pending[0]["id"] == p2

        client.post(f"/api/v1/proposals/{p2}/approve")
        assert len(client.get("/api/v1/proposals").json()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# OAuth endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestOAuth:
    """Tests for /api/v1/oauth/* endpoints."""

    @pytest.fixture
    def oauth_server(self, tmp_dir, db, memory):
        """Server with data_dir pointing to a writeable temp dir."""
        import json

        # Plant a google_credentials.json
        creds = {
            "installed": {
                "client_id": "test-id.apps.googleusercontent.com",
                "client_secret": "test-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        (tmp_dir / "google_credentials.json").write_text(json.dumps(creds))
        return OmniBrainAPIServer(db=db, memory_manager=memory, data_dir=tmp_dir)

    @pytest.fixture
    def oauth_client(self, oauth_server):
        return TestClient(oauth_server.app)

    def test_oauth_status_not_connected(self, oauth_client):
        r = oauth_client.get("/api/v1/oauth/status")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is False
        assert data["has_client_credentials"] is True

    def test_oauth_status_no_credentials(self, db, memory, tmp_path):
        """No google_credentials.json → has_client_credentials=False."""
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, data_dir=tmp_path)
        c = TestClient(srv.app)
        r = c.get("/api/v1/oauth/status")
        assert r.status_code == 200
        assert r.json()["has_client_credentials"] is False

    def test_oauth_google_returns_url(self, oauth_client):
        r = oauth_client.get("/api/v1/oauth/google")
        assert r.status_code == 200
        data = r.json()
        assert "auth_url" in data
        assert "accounts.google.com" in data["auth_url"]
        assert "client_id=test-id" in data["auth_url"]

    def test_oauth_google_no_credentials(self, db, memory, tmp_path):
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, data_dir=tmp_path)
        c = TestClient(srv.app)
        r = c.get("/api/v1/oauth/google")
        assert r.status_code == 503

    def test_oauth_callback_success(self, oauth_client, oauth_server, monkeypatch, tmp_dir):
        """Mock token exchange and verify callback saves tokens + redirects."""
        import json
        import urllib.request

        token_resp = json.dumps({
            "access_token": "ya29.test",
            "refresh_token": "1//refresh",
            "token_type": "Bearer",
            "scope": "openid email",
            "expires_in": 3600,
        }).encode()

        class FakeResp:
            def read(self):
                return token_resp
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        r = oauth_client.get(
            "/api/v1/oauth/google/callback",
            params={"code": "auth-code-123", "state": ""},
            follow_redirects=False,
        )
        # Should redirect
        assert r.status_code in (302, 307)
        assert "oauth=success" in r.headers.get("location", "")
        # Token should be saved
        assert (tmp_dir / "google_token.json").exists()

    def test_oauth_disconnect(self, oauth_client, tmp_dir):
        """Disconnect when no token → disconnected=False."""
        r = oauth_client.post("/api/v1/oauth/disconnect")
        assert r.status_code == 200
        assert r.json()["disconnected"] is False

    def test_oauth_disconnect_with_token(self, oauth_client, tmp_dir):
        """Disconnect when token exists → disconnected=True."""
        import json
        (tmp_dir / "google_token.json").write_text(json.dumps({"token": "t"}))
        r = oauth_client.post("/api/v1/oauth/disconnect")
        assert r.status_code == 200
        assert r.json()["disconnected"] is True
        assert not (tmp_dir / "google_token.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Onboarding endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestOnboarding:
    """Tests for POST /api/v1/onboarding/analyze."""

    def test_analyze_requires_google(self, client):
        """Without Google connected, should return 400."""
        r = client.post("/api/v1/onboarding/analyze")
        assert r.status_code == 400

    def test_analyze_with_mocked_google(self, tmp_dir, db, memory, monkeypatch):
        """Full onboarding analysis with mocked Gmail + Calendar."""
        import json
        import types
        from unittest.mock import patch

        # Setup: plant token file
        (tmp_dir / "google_token.json").write_text(json.dumps({"token": "ya29"}))
        (tmp_dir / "google_credentials.json").write_text(json.dumps({
            "installed": {"client_id": "id", "client_secret": "s"},
        }))

        srv = OmniBrainAPIServer(db=db, memory_manager=memory, data_dir=tmp_dir)

        # Mock the OnboardingAnalyzer
        from omnibrain.auth.onboarding import InsightCard, OnboardingResult

        fake_result = OnboardingResult(
            greeting="Good morning, Test.",
            stats={"emails": 50, "contacts": 8, "events": 3},
            insights=[
                InsightCard(icon="mail", title="Top sender", body="alice@x.com sent 12 emails", priority=3),
                InsightCard(icon="calendar", title="2 meetings today", body="Next: standup", priority=5),
            ],
            user_email="test@example.com",
            user_name="Test",
            completed_at="2025-01-15T10:00:00Z",
            duration_ms=1500,
        )

        with patch("omnibrain.auth.onboarding.OnboardingAnalyzer") as mock_cls:
            mock_cls.return_value.analyze.return_value = fake_result
            c = TestClient(srv.app)
            r = c.post("/api/v1/onboarding/analyze")

        assert r.status_code == 200
        data = r.json()
        assert data["greeting"] == "Good morning, Test."
        assert data["stats"]["emails"] == 50
        assert data["stats"]["contacts"] == 8
        assert len(data["insights"]) == 2
        assert data["user_email"] == "test@example.com"
        assert data["duration_ms"] == 1500


"""
Tests for GDPR Data Export / Wipe routes and Transparency API routes.

Groups:
    DataExport      — POST /api/v1/data/export
    DataWipe        — POST + DELETE /api/v1/data/wipe (double-delete pattern)
    TransparencyAPI — GET /api/v1/transparency/calls, /stats, /daily
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Helper for TestClient DELETE with JSON body (httpx API)
def _delete_json(client, url: str, body: dict):
    return client.request(
        "DELETE", url,
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )

import pytest
from fastapi.testclient import TestClient

from omnibrain.db import OmniBrainDB
from omnibrain.interfaces.api_server import OmniBrainAPIServer
from omnibrain.memory import MemoryManager
from omnibrain.transparency import TransparencyLogger


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
    return TestClient(server.app, raise_server_exceptions=False)


@pytest.fixture
def tlogger(tmp_dir):
    return TransparencyLogger(tmp_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Data Export
# ═══════════════════════════════════════════════════════════════════════════


class TestDataExport:
    def test_export_returns_json(self, client):
        r = client.post("/api/v1/data/export")
        assert r.status_code == 200
        # Response should be valid JSON (may stream but TestClient assembles it)
        data = r.json()
        assert isinstance(data, dict)

    def test_export_contains_expected_sections(self, client):
        r = client.post("/api/v1/data/export")
        data = r.json()
        # All data sections must be present (metadata key is _metadata)
        for key in ("events", "contacts", "proposals", "observations",
                    "briefings", "preferences", "_metadata"):
            assert key in data, f"Missing section: {key}"

    def test_export_events_populated(self, client, db):
        db.insert_event(
            source="gmail",
            event_type="email",
            title="Test email",
            content="Hello",
        )
        r = client.post("/api/v1/data/export")
        data = r.json()
        assert len(data["events"]) >= 1

    def test_export_contacts_populated(self, client, db):
        from omnibrain.models import ContactInfo
        db.upsert_contact(ContactInfo(email="test@example.com", name="Test User"))
        r = client.post("/api/v1/data/export")
        data = r.json()
        assert len(data["contacts"]) >= 1

    def test_export_metadata_present(self, client):
        r = client.post("/api/v1/data/export")
        # Metadata is stored under "_metadata" key
        meta = r.json().get("_metadata", {})
        assert "exported_at" in meta
        assert "version" in meta

    def test_export_empty_db_returns_empty_lists(self, client):
        r = client.post("/api/v1/data/export")
        data = r.json()
        assert data["events"] == []
        assert data["contacts"] == []
        assert data["proposals"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Data Wipe — Double-delete pattern
# ═══════════════════════════════════════════════════════════════════════════


class TestDataWipe:
    def test_post_wipe_returns_token(self, client):
        r = client.post("/api/v1/data/wipe")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending_confirmation"
        assert "confirmation_token" in data
        assert len(data["confirmation_token"]) > 10

    def test_post_wipe_returns_expires_in(self, client):
        r = client.post("/api/v1/data/wipe")
        data = r.json()
        assert data["expires_in"] == 60

    def test_delete_without_token_returns_400(self, client):
        r = _delete_json(client, "/api/v1/data/wipe", {})
        assert r.status_code == 400

    def test_delete_with_invalid_token_returns_400(self, client):
        r = _delete_json(client, "/api/v1/data/wipe", {"confirmation_token": "invalid-token-xyz"})
        assert r.status_code == 400

    def test_full_wipe_flow(self, client, db):
        # Insert some data first
        db.insert_event(source="gmail", event_type="email", title="test", content="x")

        # Step 1: request wipe
        r1 = client.post("/api/v1/data/wipe")
        assert r1.status_code == 200
        token = r1.json()["confirmation_token"]

        # Step 2: confirm with token
        r2 = _delete_json(client, "/api/v1/data/wipe", {"confirmation_token": token})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "wiped"

    def test_token_single_use(self, client):
        """Same token cannot be used twice."""
        r1 = client.post("/api/v1/data/wipe")
        token = r1.json()["confirmation_token"]

        # First confirm — should succeed
        r2 = _delete_json(client, "/api/v1/data/wipe", {"confirmation_token": token})
        assert r2.status_code == 200

        # Second confirm with same token — should fail
        r3 = _delete_json(client, "/api/v1/data/wipe", {"confirmation_token": token})
        assert r3.status_code == 400

    def test_wipe_clears_events(self, client, db):
        db.insert_event(source="gmail", event_type="email", title="to-delete", content="x")

        r1 = client.post("/api/v1/data/wipe")
        token = r1.json()["confirmation_token"]

        r2 = _delete_json(client, "/api/v1/data/wipe", {"confirmation_token": token})
        assert r2.status_code == 200

        # DB should now be empty
        events = db.get_events(limit=100)
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════
# Transparency API — /api/v1/transparency/*
# ═══════════════════════════════════════════════════════════════════════════


class TestTransparencyAPI:
    """Test transparency routes via TestClient.

    We wire a real TransparencyLogger to the server and insert test data.
    """

    @pytest.fixture
    def server_with_tlog(self, db, memory, tmp_dir):
        srv = OmniBrainAPIServer(db=db, memory_manager=memory, version="0.1.0-test")
        tlog = TransparencyLogger(tmp_dir)
        srv._transparency_logger = tlog
        srv._data_dir = tmp_dir
        return srv, tlog

    @pytest.fixture
    def tlog_client(self, server_with_tlog):
        srv, tlog = server_with_tlog
        return TestClient(srv.app, raise_server_exceptions=False), tlog

    def _insert(self, tlog: TransparencyLogger, **kwargs):
        defaults = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_estimate": 0.001,
            "source": "chat",
        }
        defaults.update(kwargs)
        tlog.log_call(**defaults)

    def test_calls_endpoint_empty(self, tlog_client):
        client, _ = tlog_client
        r = client.get("/api/v1/transparency/calls")
        assert r.status_code == 200
        data = r.json()
        assert data["calls"] == []
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_calls_endpoint_with_data(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, provider="deepseek", source="chat")
        self._insert(tlog, provider="claude", source="briefing")
        r = client.get("/api/v1/transparency/calls")
        assert r.status_code == 200
        assert len(r.json()["calls"]) == 2

    def test_calls_filter_by_provider(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, provider="deepseek")
        self._insert(tlog, provider="claude")
        r = client.get("/api/v1/transparency/calls?provider=claude")
        assert r.status_code == 200
        calls = r.json()["calls"]
        assert len(calls) == 1
        assert calls[0]["provider"] == "claude"

    def test_calls_filter_by_source(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, source="briefing")
        self._insert(tlog, source="chat")
        r = client.get("/api/v1/transparency/calls?source=briefing")
        assert r.status_code == 200
        calls = r.json()["calls"]
        assert len(calls) == 1
        assert calls[0]["source"] == "briefing"

    def test_calls_pagination(self, tlog_client):
        client, tlog = tlog_client
        for _ in range(5):
            self._insert(tlog)
        r = client.get("/api/v1/transparency/calls?limit=2&offset=2")
        assert r.status_code == 200
        data = r.json()
        assert len(data["calls"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 2

    def test_stats_endpoint_empty(self, tlog_client):
        client, _ = tlog_client
        r = client.get("/api/v1/transparency/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_calls"] == 0

    def test_stats_endpoint_with_data(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, provider="deepseek", input_tokens=100, cost_estimate=0.005)
        self._insert(tlog, provider="claude", input_tokens=200, cost_estimate=0.01)
        r = client.get("/api/v1/transparency/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_calls"] == 2
        assert data["total_input_tokens"] == 300
        assert abs(data["total_cost"] - 0.015) < 1e-6

    def test_stats_provider_breakdown(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, provider="deepseek")
        self._insert(tlog, provider="deepseek")
        self._insert(tlog, provider="claude")
        r = client.get("/api/v1/transparency/stats")
        data = r.json()
        assert data["calls_by_provider"]["deepseek"] == 2
        assert data["calls_by_provider"]["claude"] == 1

    def test_daily_endpoint_empty(self, tlog_client):
        client, _ = tlog_client
        r = client.get("/api/v1/transparency/daily")
        assert r.status_code == 200
        data = r.json()
        # Key is "data" not "daily"
        assert data["data"] == []

    def test_daily_endpoint_with_data(self, tlog_client):
        client, tlog = tlog_client
        self._insert(tlog, provider="deepseek", cost_estimate=0.01)
        r = client.get("/api/v1/transparency/daily?days=7")
        assert r.status_code == 200
        daily = r.json()["data"]
        assert len(daily) >= 1

    def test_calls_invalid_limit(self, tlog_client):
        """limit must be >= 1 and <= 500."""
        client, _ = tlog_client
        r = client.get("/api/v1/transparency/calls?limit=0")
        assert r.status_code == 422  # Validation error

    def test_calls_invalid_offset(self, tlog_client):
        """offset must be >= 0."""
        client, _ = tlog_client
        r = client.get("/api/v1/transparency/calls?offset=-1")
        assert r.status_code == 422

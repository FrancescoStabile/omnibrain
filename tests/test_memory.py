"""
Tests for OmniBrain Memory System (Day 9-10).

Groups:
    MemoryDocument     — Document creation, serialization
    SQLiteMemoryStore  — Store, search, delete, count, edge cases
    MemoryManager      — Facade, dual-backend, convenience methods
    MemoryTools        — search_memory, store_observation tool handlers
    BatchIngestion     — ingest_emails_to_memory, ingest_events_to_memory
    Extractors         — extract_memory_results, extract_observation
    Integration        — End-to-end memory flows
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.memory import (
    ChromaMemoryStore,
    MemoryDocument,
    MemoryManager,
    MemoryStore,
    SQLiteMemoryStore,
    _chromadb_available,
    _generate_id,
    _sanitize_fts_query,
)
from omnibrain.tools.memory_tools import (
    MEMORY_TOOL_SCHEMAS,
    SEARCH_MEMORY_SCHEMA,
    STORE_OBSERVATION_SCHEMA,
    ingest_emails_to_memory,
    ingest_events_to_memory,
    search_memory,
    store_observation,
)
from omnibrain.extractors import extract_memory_results, extract_observation


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test databases."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sqlite_store(tmp_dir):
    """Create a SQLiteMemoryStore for testing."""
    return SQLiteMemoryStore(tmp_dir)


@pytest.fixture
def memory_manager(tmp_dir):
    """Create a MemoryManager with ChromaDB disabled (SQLite only)."""
    return MemoryManager(tmp_dir, enable_chroma=False)


@pytest.fixture
def sample_doc():
    """A sample MemoryDocument."""
    return MemoryDocument(
        id="doc_001",
        text="Meeting with Marco about the Q4 pricing strategy",
        source="marco@example.com",
        source_type="calendar",
        timestamp="2024-01-15T10:00:00",
        contacts=["marco@example.com"],
        metadata={"duration_minutes": 60},
    )


@pytest.fixture
def sample_email():
    """A sample email dict (from email_tools)."""
    return {
        "id": "msg_abc123",
        "thread_id": "thread_abc",
        "subject": "Q4 Budget Review",
        "sender": "Anna Rossi",
        "sender_email": "anna@example.com",
        "body_preview": "Hi, I've attached the updated Q4 budget. Please review before Monday.",
        "date": "2024-01-15T09:30:00",
        "is_read": False,
        "has_attachments": True,
    }


@pytest.fixture
def sample_event():
    """A sample calendar event dict (from calendar_tools)."""
    return {
        "id": "evt_xyz789",
        "title": "Sprint Planning",
        "description": "Plan next sprint tasks and review backlog",
        "start_time": "2024-01-16T10:00:00",
        "end_time": "2024-01-16T11:00:00",
        "duration_minutes": 60,
        "location": "Zoom",
        "attendees": ["alice@example.com", "bob@example.com"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# MemoryDocument Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryDocument:
    def test_creation_with_defaults(self):
        doc = MemoryDocument(id="1", text="hello")
        assert doc.id == "1"
        assert doc.text == "hello"
        assert doc.source == ""
        assert doc.source_type == ""
        assert doc.contacts == []
        assert doc.metadata == {}
        assert doc.score == 0.0
        assert doc.timestamp  # auto-generated

    def test_creation_with_all_fields(self, sample_doc):
        assert sample_doc.id == "doc_001"
        assert "Marco" in sample_doc.text
        assert sample_doc.source_type == "calendar"
        assert sample_doc.contacts == ["marco@example.com"]
        assert sample_doc.metadata == {"duration_minutes": 60}

    def test_to_dict(self, sample_doc):
        d = sample_doc.to_dict()
        assert d["id"] == "doc_001"
        assert d["text"] == sample_doc.text
        assert d["source"] == "marco@example.com"
        assert d["source_type"] == "calendar"
        assert d["contacts"] == ["marco@example.com"]
        assert d["metadata"]["duration_minutes"] == 60
        assert d["score"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# SQLiteMemoryStore Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSQLiteMemoryStore:
    def test_store_and_count(self, sqlite_store, sample_doc):
        assert sqlite_store.count() == 0
        ok = sqlite_store.store(sample_doc)
        assert ok is True
        assert sqlite_store.count() == 1

    def test_store_replaces_on_same_id(self, sqlite_store):
        doc = MemoryDocument(id="dup", text="version 1")
        sqlite_store.store(doc)
        assert sqlite_store.count() == 1

        doc2 = MemoryDocument(id="dup", text="version 2")
        sqlite_store.store(doc2)
        assert sqlite_store.count() == 1

        retrieved = sqlite_store.get_by_id("dup")
        assert retrieved is not None
        assert retrieved.text == "version 2"

    def test_search_basic(self, sqlite_store, sample_doc):
        sqlite_store.store(sample_doc)
        # sample_doc has old timestamp, use large time_range
        results = sqlite_store.search("pricing", time_range_days=3650)
        assert len(results) >= 1
        assert "pricing" in results[0].text.lower()

    def test_search_empty_query(self, sqlite_store, sample_doc):
        sqlite_store.store(sample_doc)
        results = sqlite_store.search("")
        assert results == []

    def test_search_no_match(self, sqlite_store, sample_doc):
        sqlite_store.store(sample_doc)
        results = sqlite_store.search("kubernetes")
        assert results == []

    def test_search_with_source_filter(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="e1", text="Email about sales", source_type="email"))
        sqlite_store.store(MemoryDocument(id="c1", text="Calendar meeting about sales", source_type="calendar"))

        email_results = sqlite_store.search("sales", source_filter="email")
        assert len(email_results) == 1
        assert email_results[0].source_type == "email"

        cal_results = sqlite_store.search("sales", source_filter="calendar")
        assert len(cal_results) == 1
        assert cal_results[0].source_type == "calendar"

    def test_search_all_sources(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="e1", text="revenue forecast", source_type="email"))
        sqlite_store.store(MemoryDocument(id="c1", text="revenue review meeting", source_type="calendar"))

        results = sqlite_store.search("revenue", source_filter="all")
        assert len(results) == 2

    def test_search_max_results(self, sqlite_store):
        for i in range(20):
            sqlite_store.store(MemoryDocument(id=f"d{i}", text=f"document about testing number {i}"))
        results = sqlite_store.search("testing", max_results=5)
        assert len(results) == 5

    def test_search_time_range(self, sqlite_store):
        sqlite_store.store(MemoryDocument(
            id="old", text="old pricing discussion",
            timestamp="2020-01-01T00:00:00",
        ))
        sqlite_store.store(MemoryDocument(
            id="new", text="new pricing discussion",
            timestamp="2099-01-01T00:00:00",
        ))
        results = sqlite_store.search("pricing", time_range_days=30)
        # Only the future-dated one should match (within 30 days from now? No — the cutoff
        # is now - 30 days, so the 2020 one should NOT match and the 2099 one should.)
        ids = [r.id for r in results]
        assert "new" in ids
        assert "old" not in ids

    def test_delete(self, sqlite_store, sample_doc):
        sqlite_store.store(sample_doc)
        assert sqlite_store.count() == 1
        ok = sqlite_store.delete(sample_doc.id)
        assert ok is True
        assert sqlite_store.count() == 0

    def test_delete_nonexistent(self, sqlite_store):
        ok = sqlite_store.delete("nonexistent")
        assert ok is True  # DELETE succeeds even if row doesn't exist

    def test_get_by_id(self, sqlite_store, sample_doc):
        sqlite_store.store(sample_doc)
        doc = sqlite_store.get_by_id("doc_001")
        assert doc is not None
        assert doc.text == sample_doc.text
        assert doc.contacts == ["marco@example.com"]
        assert doc.metadata == {"duration_minutes": 60}

    def test_get_by_id_nonexistent(self, sqlite_store):
        assert sqlite_store.get_by_id("nope") is None

    def test_get_recent(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="a", text="aaa", timestamp="2024-01-01T00:00:00"))
        sqlite_store.store(MemoryDocument(id="b", text="bbb", timestamp="2024-06-01T00:00:00"))
        sqlite_store.store(MemoryDocument(id="c", text="ccc", timestamp="2024-12-01T00:00:00"))

        recent = sqlite_store.get_recent(max_results=2)
        assert len(recent) == 2
        assert recent[0].id == "c"  # Most recent first
        assert recent[1].id == "b"

    def test_get_recent_with_filter(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="e1", text="email one", source_type="email"))
        sqlite_store.store(MemoryDocument(id="c1", text="cal one", source_type="calendar"))
        sqlite_store.store(MemoryDocument(id="e2", text="email two", source_type="email"))

        emails = sqlite_store.get_recent(source_filter="email")
        assert all(d.source_type == "email" for d in emails)
        assert len(emails) == 2

    def test_search_special_characters(self, sqlite_store):
        """FTS5 query with special characters should not crash."""
        sqlite_store.store(MemoryDocument(id="s1", text="user@example.com sent a message"))
        # These would crash FTS5 with raw query
        results = sqlite_store.search("user@example.com")
        assert isinstance(results, list)

    def test_search_returns_score(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="s1", text="project alpha budget meeting"))
        results = sqlite_store.search("budget")
        if results:
            assert results[0].score >= 0  # BM25 score converted to positive

    def test_multiple_words_search(self, sqlite_store):
        sqlite_store.store(MemoryDocument(id="m1", text="meeting about budget and revenue"))
        sqlite_store.store(MemoryDocument(id="m2", text="lunch plans for friday"))

        # Searches for "budget" OR "revenue" — should match m1
        results = sqlite_store.search("budget revenue")
        assert len(results) >= 1
        assert results[0].id == "m1"


# ═══════════════════════════════════════════════════════════════════════════
# MemoryManager Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryManager:
    def test_creation_sqlite_only(self, memory_manager):
        assert memory_manager.has_chroma is False
        assert memory_manager.count() == 0

    def test_store_returns_id(self, memory_manager):
        doc_id = memory_manager.store(text="hello world", source="test", source_type="test")
        assert doc_id  # non-empty string
        assert memory_manager.count() == 1

    def test_store_with_custom_id(self, memory_manager):
        doc_id = memory_manager.store(text="hello", id="custom_id")
        assert doc_id == "custom_id"

    def test_search(self, memory_manager):
        memory_manager.store(text="meeting about pricing strategy", source_type="calendar")
        results = memory_manager.search("pricing")
        assert len(results) >= 1

    def test_get_by_id(self, memory_manager):
        memory_manager.store(text="important note", id="note_1")
        doc = memory_manager.get_by_id("note_1")
        assert doc is not None
        assert doc.text == "important note"

    def test_get_recent(self, memory_manager):
        memory_manager.store(text="first", id="r1", source_type="email")
        memory_manager.store(text="second", id="r2", source_type="email")
        recent = memory_manager.get_recent(max_results=10)
        assert len(recent) == 2

    def test_delete(self, memory_manager):
        memory_manager.store(text="to delete", id="del_1")
        assert memory_manager.count() == 1
        ok = memory_manager.delete("del_1")
        assert ok is True
        assert memory_manager.count() == 0

    def test_store_email(self, memory_manager, sample_email):
        doc_id = memory_manager.store_email(sample_email)
        assert doc_id == "email_msg_abc123"
        doc = memory_manager.get_by_id(doc_id)
        assert doc is not None
        assert "Anna Rossi" in doc.text
        assert "Q4 Budget" in doc.text
        assert doc.source_type == "email"
        assert "anna@example.com" in doc.contacts

    def test_store_calendar_event(self, memory_manager, sample_event):
        doc_id = memory_manager.store_calendar_event(sample_event)
        assert doc_id == "cal_evt_xyz789"
        doc = memory_manager.get_by_id(doc_id)
        assert doc is not None
        assert "Sprint Planning" in doc.text
        assert doc.source_type == "calendar"
        assert "alice@example.com" in doc.contacts

    def test_chroma_disabled_flag(self, tmp_dir):
        mgr = MemoryManager(tmp_dir, enable_chroma=False)
        assert mgr.has_chroma is False

    @patch("omnibrain.memory._chromadb_available", return_value=False)
    def test_chroma_unavailable_fallback(self, mock_avail, tmp_dir):
        mgr = MemoryManager(tmp_dir, enable_chroma=True)
        assert mgr.has_chroma is False
        # Should still work with SQLite
        mgr.store(text="test", id="t1")
        assert mgr.count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# Memory Tools Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSearchMemoryTool:
    def test_search_returns_results(self, memory_manager):
        memory_manager.store(text="budget meeting Q4", id="s1", source_type="email")
        result = search_memory(memory_manager, {"query": "budget"})
        assert result["count"] >= 1
        assert result["backend"] == "keyword"
        assert result["query"] == "budget"

    def test_search_empty_query(self, memory_manager):
        result = search_memory(memory_manager, {"query": ""})
        assert result["count"] == 0
        assert "error" in result

    def test_search_with_filter(self, memory_manager):
        memory_manager.store(text="email about revenue", id="e1", source_type="email")
        memory_manager.store(text="calendar revenue review", id="c1", source_type="calendar")
        result = search_memory(memory_manager, {"query": "revenue", "source_filter": "email"})
        assert result["count"] >= 1
        for r in result["results"]:
            assert r["source_type"] == "email"

    def test_search_respects_max_results(self, memory_manager):
        for i in range(15):
            memory_manager.store(text=f"document about testing {i}", id=f"d{i}")
        result = search_memory(memory_manager, {"query": "testing", "max_results": 3})
        assert result["count"] <= 3

    def test_search_result_structure(self, memory_manager):
        memory_manager.store(
            text="Q4 pricing discussion",
            id="s1",
            source="marco@test.com",
            source_type="email",
            contacts=["marco@test.com"],
        )
        result = search_memory(memory_manager, {"query": "pricing"})
        assert result["count"] >= 1
        item = result["results"][0]
        assert "id" in item
        assert "text" in item
        assert "source" in item
        assert "source_type" in item
        assert "timestamp" in item
        assert "score" in item
        assert "contacts" in item


class TestStoreObservationTool:
    def test_store_observation(self, memory_manager):
        result = store_observation(memory_manager, {
            "pattern_type": "communication",
            "description": "User always replies to boss within 1 hour",
            "confidence": 0.8,
        })
        assert result["stored"] is True
        assert result["pattern_type"] == "communication"
        assert result["confidence"] == 0.8
        assert result["id"]  # non-empty

    def test_store_observation_default_confidence(self, memory_manager):
        result = store_observation(memory_manager, {
            "pattern_type": "scheduling",
            "description": "User prefers morning meetings",
        })
        assert result["stored"] is True
        assert result["confidence"] == 0.5

    def test_store_observation_missing_fields(self, memory_manager):
        result = store_observation(memory_manager, {"pattern_type": ""})
        assert result["stored"] is False
        assert "error" in result

    def test_stored_observation_searchable(self, memory_manager):
        store_observation(memory_manager, {
            "pattern_type": "preference",
            "description": "User prefers brief email responses",
            "confidence": 0.9,
        })
        # Should be findable via search
        results = memory_manager.search("email responses")
        assert len(results) >= 1
        assert results[0].source_type == "observation"

    def test_confidence_clamped(self, memory_manager):
        result = store_observation(memory_manager, {
            "pattern_type": "test",
            "description": "over confidence test",
            "confidence": 5.0,
        })
        assert result["confidence"] == 1.0

        result2 = store_observation(memory_manager, {
            "pattern_type": "test",
            "description": "under confidence test",
            "confidence": -2.0,
        })
        assert result2["confidence"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Batch Ingestion Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBatchIngestion:
    def test_ingest_emails(self, memory_manager):
        emails = [
            {"id": "e1", "subject": "Budget", "sender": "Alice", "sender_email": "alice@test.com", "body_preview": "Review this"},
            {"id": "e2", "subject": "Sprint", "sender": "Bob", "sender_email": "bob@test.com", "body_preview": "Sprint update"},
        ]
        result = ingest_emails_to_memory(memory_manager, emails)
        assert result["stored"] == 2
        assert result["failed"] == 0
        assert result["total"] == 2
        assert memory_manager.count() == 2

    def test_ingest_events(self, memory_manager):
        events = [
            {"id": "ev1", "title": "Standup", "description": "Daily meeting", "attendees": ["a@t.com"]},
            {"id": "ev2", "title": "Review", "description": "Code review", "attendees": []},
        ]
        result = ingest_events_to_memory(memory_manager, events)
        assert result["stored"] == 2
        assert result["failed"] == 0

    def test_ingest_empty(self, memory_manager):
        result = ingest_emails_to_memory(memory_manager, [])
        assert result["stored"] == 0
        assert result["total"] == 0

    def test_ingest_partial_emails(self, memory_manager):
        """Emails with minimal fields should still work."""
        emails = [{"id": "e1", "subject": "test"}]
        result = ingest_emails_to_memory(memory_manager, emails)
        assert result["stored"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Extractor Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryExtractors:
    def test_extract_memory_results_empty(self):
        result = extract_memory_results(None, {"results": [], "count": 0}, {})
        assert result["count"] == 0
        assert result["results"] == []
        assert result["contacts"] == []
        assert result["by_source"] == {}

    def test_extract_memory_results_with_data(self):
        search_result = {
            "results": [
                {"id": "1", "text": "meeting about budget", "source_type": "calendar",
                 "contacts": ["alice@test.com"], "score": 0.9},
                {"id": "2", "text": "email about budget", "source_type": "email",
                 "contacts": ["bob@test.com"], "score": 0.7},
            ],
            "count": 2,
            "query": "budget",
            "backend": "keyword",
        }
        result = extract_memory_results(None, search_result, {"query": "budget"})
        assert result["count"] == 2
        assert "calendar" in result["by_source"]
        assert "email" in result["by_source"]
        assert "alice@test.com" in result["contacts"]
        assert "bob@test.com" in result["contacts"]
        assert result["avg_score"] == 0.8

    def test_extract_observation(self):
        obs_result = {"stored": True, "pattern_type": "scheduling", "confidence": 0.9}
        result = extract_observation(None, obs_result, {})
        assert result["stored"] is True
        assert result["pattern_type"] == "scheduling"
        assert result["confidence"] == 0.9


# ═══════════════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemas:
    def test_search_memory_schema(self):
        assert SEARCH_MEMORY_SCHEMA["name"] == "search_memory"
        params = SEARCH_MEMORY_SCHEMA["parameters"]
        assert "query" in params["properties"]
        assert "query" in params["required"]
        assert "source_filter" in params["properties"]
        assert "max_results" in params["properties"]
        assert "time_range_days" in params["properties"]
        enum = params["properties"]["source_filter"]["enum"]
        assert "all" in enum
        assert "email" in enum
        assert "calendar" in enum

    def test_store_observation_schema(self):
        assert STORE_OBSERVATION_SCHEMA["name"] == "store_observation"
        params = STORE_OBSERVATION_SCHEMA["parameters"]
        assert "pattern_type" in params["properties"]
        assert "description" in params["properties"]
        assert "confidence" in params["properties"]
        assert params["properties"]["confidence"]["minimum"] == 0
        assert params["properties"]["confidence"]["maximum"] == 1

    def test_memory_tool_schemas_list(self):
        assert len(MEMORY_TOOL_SCHEMAS) == 2
        names = [s["name"] for s in MEMORY_TOOL_SCHEMAS]
        assert "search_memory" in names
        assert "store_observation" in names


# ═══════════════════════════════════════════════════════════════════════════
# Helper Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:
    def test_generate_id_deterministic(self):
        id1 = _generate_id("hello", "source1")
        id2 = _generate_id("hello", "source1")
        assert id1 == id2

    def test_generate_id_different_inputs(self):
        id1 = _generate_id("hello", "source1")
        id2 = _generate_id("world", "source2")
        assert id1 != id2

    def test_generate_id_length(self):
        doc_id = _generate_id("some text", "some source")
        assert len(doc_id) == 16

    def test_sanitize_fts_query_basic(self):
        q = _sanitize_fts_query("budget meeting")
        assert '"budget"' in q
        assert '"meeting"' in q
        assert "OR" in q

    def test_sanitize_fts_query_special_chars(self):
        q = _sanitize_fts_query("user@example.com (test)")
        assert q  # should not be empty
        # Special chars should be sanitized
        assert "(" not in q
        assert ")" not in q

    def test_sanitize_fts_query_empty(self):
        assert _sanitize_fts_query("") == ""
        assert _sanitize_fts_query("   ") == ""


# ═══════════════════════════════════════════════════════════════════════════
# ChromaDB Tests (mock-based, since chromadb unavailable on Python 3.14)
# ═══════════════════════════════════════════════════════════════════════════


class TestChromaDBAvailability:
    def test_chromadb_available_check(self):
        """On Python 3.14, chromadb should not be available."""
        # We just check it returns a bool and doesn't crash
        result = _chromadb_available()
        assert isinstance(result, bool)


class TestChromaMemoryStoreMocked:
    """Test ChromaMemoryStore with mocked chromadb."""

    @patch("omnibrain.memory._chromadb_available", return_value=True)
    def test_init_failure_sets_unavailable(self, mock_avail, tmp_dir):
        """If chromadb import fails during init, store is unavailable."""
        with patch.dict("sys.modules", {"chromadb": None}):
            store = ChromaMemoryStore(tmp_dir)
            assert store.is_available is False

    def test_unavailable_store_returns_false(self, tmp_dir):
        store = ChromaMemoryStore.__new__(ChromaMemoryStore)
        store._client = None
        store._collection = None
        doc = MemoryDocument(id="1", text="test")
        assert store.store(doc) is False

    def test_unavailable_search_returns_empty(self, tmp_dir):
        store = ChromaMemoryStore.__new__(ChromaMemoryStore)
        store._client = None
        store._collection = None
        assert store.search("test") == []

    def test_unavailable_delete_returns_false(self, tmp_dir):
        store = ChromaMemoryStore.__new__(ChromaMemoryStore)
        store._client = None
        store._collection = None
        assert store.delete("1") is False

    def test_unavailable_count_returns_zero(self, tmp_dir):
        store = ChromaMemoryStore.__new__(ChromaMemoryStore)
        store._client = None
        store._collection = None
        assert store.count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_full_email_workflow(self, memory_manager, sample_email):
        """Store email → search by content → find it."""
        memory_manager.store_email(sample_email)
        results = memory_manager.search("Q4 Budget")
        assert len(results) >= 1
        assert "Budget" in results[0].text

    def test_full_calendar_workflow(self, memory_manager, sample_event):
        """Store event → search by content → find it."""
        memory_manager.store_calendar_event(sample_event)
        results = memory_manager.search("Sprint Planning")
        assert len(results) >= 1
        assert "Sprint" in results[0].text

    def test_cross_source_search(self, memory_manager, sample_email, sample_event):
        """Store email + event → search across both."""
        memory_manager.store_email(sample_email)
        memory_manager.store_calendar_event(sample_event)
        assert memory_manager.count() == 2

        # Search all sources
        all_results = memory_manager.search("review", source_filter="all")
        # "review" appears in both email body_preview and event description
        assert len(all_results) >= 1

    def test_observation_workflow(self, memory_manager):
        """Store observation → search for it."""
        store_observation(memory_manager, {
            "pattern_type": "communication",
            "description": "User responds faster to marketing emails",
            "confidence": 0.85,
        })
        results = search_memory(memory_manager, {"query": "marketing emails"})
        assert results["count"] >= 1

    def test_memory_with_extractors(self, memory_manager):
        """End-to-end: store + search + extract."""
        memory_manager.store(text="Meeting prep notes for investor call", id="m1", source_type="calendar")
        memory_manager.store(text="Email from investor about next quarter", id="m2", source_type="email")

        tool_result = search_memory(memory_manager, {"query": "investor"})
        extracted = extract_memory_results(None, tool_result, {"query": "investor"})

        assert extracted["count"] >= 1
        assert "by_source" in extracted

    def test_extractor_registered(self):
        """Verify extractors are registered in the global dict."""
        from omnibrain.extractors import EXTRACTORS
        assert "search_memory" in EXTRACTORS
        assert "store_observation" in EXTRACTORS

    def test_tools_exported(self):
        """Verify tools are exported from __init__."""
        from omnibrain.tools import (
            search_memory as sm,
            store_observation as so,
            MEMORY_TOOL_SCHEMAS as schemas,
        )
        assert callable(sm)
        assert callable(so)
        assert len(schemas) == 2

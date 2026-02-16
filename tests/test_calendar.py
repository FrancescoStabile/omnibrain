"""
Tests for OmniBrain Google Calendar integration.

Tests cover:
    - Calendar event parsing (_parse_event, _parse_event_time)
    - CalendarClient authentication flow (mocked)
    - calendar_tools handlers (get_today_events, get_upcoming_events, generate_meeting_brief)
    - Calendar extractors (extract_calendar)
    - store_events_in_db integration with OmniBrainDB
    - CalendarEvent model (duration_minutes, attendees_summary, serialization)
    - Tool schemas validation
    - CLI today/upcoming commands

All Google API calls are mocked — no real authentication needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from omnibrain.models import CalendarEvent, EventSource


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for tests."""
    data_dir = tmp_path / ".omnibrain"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_calendar_event_data() -> dict[str, Any]:
    """A realistic Google Calendar API event response."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    return {
        "id": "evt_001",
        "summary": "Team Standup",
        "description": "Daily standup meeting for the engineering team.",
        "location": "Meeting Room A",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "attendees": [
            {"email": "marco@example.com", "displayName": "Marco Rossi"},
            {"email": "giulia@example.com", "displayName": "Giulia Bianchi"},
            {"email": "francesco@omnibrain.dev", "displayName": "Francesco", "self": True},
        ],
        "recurringEventId": "recurring_weekly_001",
    }


@pytest.fixture
def sample_allday_event_data() -> dict[str, Any]:
    """An all-day calendar event."""
    return {
        "id": "evt_002",
        "summary": "Company Holiday",
        "description": "National holiday — office closed.",
        "start": {"date": "2026-02-15"},
        "end": {"date": "2026-02-16"},
    }


@pytest.fixture
def sample_minimal_event_data() -> dict[str, Any]:
    """A minimal event — no title, no attendees, no location."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=14, minute=30, second=0, microsecond=0)
    end = start + timedelta(minutes=30)

    return {
        "id": "evt_003",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }


@pytest.fixture
def sample_events_list(sample_calendar_event_data, sample_allday_event_data, sample_minimal_event_data):
    """Multiple events for list testing."""
    return [sample_calendar_event_data, sample_allday_event_data, sample_minimal_event_data]


@pytest.fixture
def mock_calendar_service(sample_events_list):
    """A mocked Google Calendar service."""
    service = MagicMock()
    events_resource = MagicMock()
    service.events.return_value = events_resource

    # events().list().execute()
    list_mock = MagicMock()
    list_mock.execute.return_value = {"items": sample_events_list}
    events_resource.list.return_value = list_mock

    # events().get().execute()
    get_mock = MagicMock()
    get_mock.execute.return_value = sample_events_list[0]
    events_resource.get.return_value = get_mock

    return service


# ═══════════════════════════════════════════════════════════════════════════
# CalendarEvent Model Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarEventModel:
    """Tests for CalendarEvent dataclass."""

    def test_duration_minutes(self):
        event = CalendarEvent(
            id="1",
            title="Test",
            start_time=datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 15, 11, 30, tzinfo=timezone.utc),
        )
        assert event.duration_minutes == 90

    def test_duration_zero(self):
        t = datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc)
        event = CalendarEvent(id="1", title="Test", start_time=t, end_time=t)
        assert event.duration_minutes == 0

    def test_attendees_summary_solo(self):
        event = CalendarEvent(
            id="1",
            title="Focus Time",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert event.attendees_summary == "solo"

    def test_attendees_summary_with_people(self):
        event = CalendarEvent(
            id="1",
            title="Meeting",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            attendees=["alice@test.com", "bob@test.com", "charlie@test.com"],
        )
        assert event.attendees_summary == "3 people"

    def test_to_dict_roundtrip(self):
        event = CalendarEvent(
            id="evt_100",
            title="Sprint Review",
            start_time=datetime(2026, 2, 15, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 15, 15, 0, tzinfo=timezone.utc),
            attendees=["alice@test.com", "bob@test.com"],
            location="Zoom",
            description="Sprint 42 review",
            is_recurring=True,
        )
        d = event.to_dict()
        restored = CalendarEvent.from_dict(d)

        assert restored.id == event.id
        assert restored.title == event.title
        assert restored.start_time == event.start_time
        assert restored.end_time == event.end_time
        assert restored.attendees == event.attendees
        assert restored.location == event.location
        assert restored.description == event.description
        assert restored.is_recurring == event.is_recurring

    def test_from_dict_json_attendees(self):
        """from_dict handles JSON-encoded attendees (as stored in DB)."""
        d = {
            "id": "1",
            "title": "Test",
            "start_time": "2026-02-15T10:00:00+00:00",
            "end_time": "2026-02-15T11:00:00+00:00",
            "attendees": '["a@test.com", "b@test.com"]',
        }
        event = CalendarEvent.from_dict(d)
        assert event.attendees == ["a@test.com", "b@test.com"]

    def test_from_dict_defaults(self):
        d = {
            "id": "1",
            "title": "Minimal",
            "start_time": "2026-02-15T10:00:00+00:00",
            "end_time": "2026-02-15T11:00:00+00:00",
        }
        event = CalendarEvent.from_dict(d)
        assert event.location == ""
        assert event.description == ""
        assert event.is_recurring is False
        assert event.attendees == []


# ═══════════════════════════════════════════════════════════════════════════
# Event Parsing Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEventParsing:
    """Tests for calendar event parsing helpers."""

    def test_parse_timed_event(self, sample_calendar_event_data):
        from omnibrain.integrations.calendar import _parse_event

        event = _parse_event(sample_calendar_event_data)
        assert event is not None
        assert event.id == "evt_001"
        assert event.title == "Team Standup"
        assert event.location == "Meeting Room A"
        assert event.description == "Daily standup meeting for the engineering team."
        assert event.is_recurring is True
        assert len(event.attendees) == 3
        assert "marco@example.com" in event.attendees
        assert event.duration_minutes == 60

    def test_parse_allday_event(self, sample_allday_event_data):
        from omnibrain.integrations.calendar import _parse_event

        event = _parse_event(sample_allday_event_data)
        assert event is not None
        assert event.id == "evt_002"
        assert event.title == "Company Holiday"
        assert event.is_recurring is False
        assert event.attendees == []
        # All-day event = 1 day = 1440 minutes
        assert event.duration_minutes == 1440

    def test_parse_minimal_event(self, sample_minimal_event_data):
        from omnibrain.integrations.calendar import _parse_event

        event = _parse_event(sample_minimal_event_data)
        assert event is not None
        assert event.id == "evt_003"
        assert event.title == "(No title)"
        assert event.location == ""
        assert event.attendees == []
        assert event.duration_minutes == 30

    def test_parse_event_no_time_returns_none(self):
        from omnibrain.integrations.calendar import _parse_event

        result = _parse_event({"id": "bad", "start": {}, "end": {}})
        assert result is None

    def test_parse_event_empty_dict_returns_none(self):
        from omnibrain.integrations.calendar import _parse_event

        result = _parse_event({})
        assert result is None

    def test_parse_event_time_datetime(self):
        from omnibrain.integrations.calendar import _parse_event_time

        result = _parse_event_time({"dateTime": "2026-02-15T10:00:00+01:00"})
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 15
        assert result.hour == 10

    def test_parse_event_time_date(self):
        from omnibrain.integrations.calendar import _parse_event_time

        result = _parse_event_time({"date": "2026-02-15"})
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 15

    def test_parse_event_time_empty(self):
        from omnibrain.integrations.calendar import _parse_event_time

        result = _parse_event_time({})
        assert result is None

    def test_parse_event_time_invalid(self):
        from omnibrain.integrations.calendar import _parse_event_time

        result = _parse_event_time({"dateTime": "not-a-date"})
        assert result is None

    def test_is_auth_error(self):
        from omnibrain.integrations.calendar import _is_auth_error

        assert _is_auth_error(Exception("401 Unauthorized")) is True
        assert _is_auth_error(Exception("invalid_grant")) is True
        assert _is_auth_error(Exception("token expired")) is True
        assert _is_auth_error(Exception("Something else")) is False


# ═══════════════════════════════════════════════════════════════════════════
# CalendarClient Tests (mocked)
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarClient:
    """Tests for CalendarClient — all API calls mocked."""

    def test_authenticate_no_token(self, tmp_data_dir):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        assert client.authenticate() is False
        assert client.is_authenticated is False

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_get_today_events(self, mock_auth, tmp_data_dir, mock_calendar_service):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True
        client._service = mock_calendar_service
        client._creds = MagicMock(valid=True)

        events = client.get_today_events()
        # Should parse 3 events (2 timed + 1 all-day)
        assert len(events) >= 2

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_get_upcoming_events(self, mock_auth, tmp_data_dir, mock_calendar_service):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True
        client._service = mock_calendar_service
        client._creds = MagicMock(valid=True)

        events = client.get_upcoming_events(days=7, max_results=20)
        assert len(events) >= 2

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_get_event_by_id(self, mock_auth, tmp_data_dir, mock_calendar_service):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True
        client._service = mock_calendar_service
        client._creds = MagicMock(valid=True)

        event = client.get_event("evt_001")
        assert event is not None
        assert event.id == "evt_001"
        assert event.title == "Team Standup"

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_get_event_not_found(self, mock_auth, tmp_data_dir):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True

        service = MagicMock()
        events_resource = MagicMock()
        service.events.return_value = events_resource
        get_mock = MagicMock()
        get_mock.execute.side_effect = Exception("Not found")
        events_resource.get.return_value = get_mock

        client._service = service
        client._creds = MagicMock(valid=True)

        event = client.get_event("nonexistent")
        assert event is None

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_search_events(self, mock_auth, tmp_data_dir, mock_calendar_service):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True
        client._service = mock_calendar_service
        client._creds = MagicMock(valid=True)

        events = client.search_events("standup")
        assert len(events) >= 2

    def test_unauthenticated_raises(self, tmp_data_dir):
        from omnibrain.integrations.calendar import CalendarClient, CalendarAuthError

        client = CalendarClient(tmp_data_dir)
        with pytest.raises(CalendarAuthError):
            client.get_today_events()
        with pytest.raises(CalendarAuthError):
            client.get_upcoming_events()
        with pytest.raises(CalendarAuthError):
            client.get_event("evt_001")
        with pytest.raises(CalendarAuthError):
            client.search_events("test")

    @patch("omnibrain.integrations.calendar.CalendarClient.authenticate")
    def test_fetch_empty_result(self, mock_auth, tmp_data_dir):
        from omnibrain.integrations.calendar import CalendarClient

        client = CalendarClient(tmp_data_dir)
        mock_auth.return_value = True

        service = MagicMock()
        events_resource = MagicMock()
        service.events.return_value = events_resource
        list_mock = MagicMock()
        list_mock.execute.return_value = {"items": []}
        events_resource.list.return_value = list_mock

        client._service = service
        client._creds = MagicMock(valid=True)

        events = client.get_today_events()
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Tools Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarTools:
    """Tests for calendar_tools handlers."""

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_get_today_events_success(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import get_today_events

        now = datetime.now(timezone.utc)
        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.get_today_events.return_value = [
            CalendarEvent(
                id="evt_1",
                title="Standup",
                start_time=now.replace(hour=9, minute=0),
                end_time=now.replace(hour=9, minute=30),
                attendees=["alice@test.com"],
            ),
            CalendarEvent(
                id="evt_2",
                title="Lunch",
                start_time=now.replace(hour=12, minute=0),
                end_time=now.replace(hour=13, minute=0),
            ),
        ]

        result = get_today_events(tmp_data_dir)
        assert result["count"] == 2
        assert len(result["events"]) == 2
        assert "error" not in result
        assert result["events"][0]["title"] == "Standup"
        assert result["events"][0]["duration_minutes"] == 30

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_get_today_events_not_authenticated(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import get_today_events

        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = False

        result = get_today_events(tmp_data_dir)
        assert "error" in result
        assert result["count"] == 0

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_get_upcoming_events_success(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import get_upcoming_events

        now = datetime.now(timezone.utc)
        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.get_upcoming_events.return_value = [
            CalendarEvent(
                id="evt_1",
                title="Monday Meeting",
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=1, hours=1),
            ),
        ]

        result = get_upcoming_events(tmp_data_dir, days=7, max_results=20)
        assert result["count"] == 1
        assert result["days_ahead"] == 7
        assert "error" not in result

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_generate_meeting_brief_success(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import generate_meeting_brief

        now = datetime.now(timezone.utc)
        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.get_event.return_value = CalendarEvent(
            id="evt_1",
            title="Strategy Meeting",
            start_time=now,
            end_time=now + timedelta(hours=2),
            attendees=["marco@example.com", "giulia@example.com"],
            location="Board Room",
            description="Q2 strategy discussion.",
        )

        # With DB mock that has contact data
        mock_db = MagicMock()
        mock_db.get_contact.side_effect = lambda email: {
            "marco@example.com": {
                "name": "Marco Rossi",
                "relationship": "colleague",
                "organization": "OmniBrain",
                "interaction_count": 42,
                "last_interaction": "2026-02-14",
            },
        }.get(email)

        result = generate_meeting_brief(tmp_data_dir, "evt_1", db=mock_db)
        assert "error" not in result
        assert result["attendee_count"] == 2
        assert result["duration_minutes"] == 120
        assert result["has_description"] is True
        assert len(result["attendee_context"]) == 2

        # Known contact
        marco = [a for a in result["attendee_context"] if a["email"] == "marco@example.com"][0]
        assert marco["name"] == "Marco Rossi"
        assert marco["interaction_count"] == 42

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_generate_meeting_brief_event_not_found(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import generate_meeting_brief

        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.get_event.return_value = None

        result = generate_meeting_brief(tmp_data_dir, "nonexistent")
        assert "error" in result

    @patch("omnibrain.tools.calendar_tools.CalendarClient")
    def test_generate_meeting_brief_no_db(self, MockClient, tmp_data_dir):
        from omnibrain.tools.calendar_tools import generate_meeting_brief

        now = datetime.now(timezone.utc)
        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.get_event.return_value = CalendarEvent(
            id="evt_1",
            title="Quick Call",
            start_time=now,
            end_time=now + timedelta(minutes=15),
        )

        result = generate_meeting_brief(tmp_data_dir, "evt_1", db=None)
        assert "error" not in result
        assert result["attendee_context"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Calendar Extractor Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCalendarExtractors:
    """Tests for calendar extractor functions."""

    def test_extract_calendar_with_events(self):
        from omnibrain.extractors import extract_calendar

        result = {
            "events": [
                {"id": "1", "title": "Standup", "duration_minutes": 30, "attendees": ["a@t.com"], "is_recurring": True},
                {"id": "2", "title": "Review", "duration_minutes": 60, "attendees": ["a@t.com", "b@t.com"], "is_recurring": False},
                {"id": "3", "title": "Focus", "duration_minutes": 120, "attendees": [], "is_recurring": False},
            ],
            "summary": "3 events today",
        }

        extracted = extract_calendar(profile=None, result=result, args={})
        assert extracted["stats"]["total"] == 3
        assert extracted["stats"]["total_minutes"] == 210
        assert extracted["stats"]["total_hours"] == 3.5
        assert extracted["stats"]["with_attendees"] == 2
        assert extracted["stats"]["recurring"] == 1
        assert extracted["stats"]["unique_attendees"] == 2
        assert extracted["summary"] == "3 events today"

    def test_extract_calendar_empty(self):
        from omnibrain.extractors import extract_calendar

        extracted = extract_calendar(profile=None, result={"events": []}, args={})
        assert extracted["stats"]["total"] == 0
        assert extracted["events"] == []

    def test_extract_calendar_registered(self):
        from omnibrain.extractors import EXTRACTORS

        assert "get_today_events" in EXTRACTORS
        assert "get_upcoming_events" in EXTRACTORS
        assert "generate_meeting_brief" in EXTRACTORS

    def test_search_emails_extractor_registered(self):
        from omnibrain.extractors import EXTRACTORS

        assert "search_emails" in EXTRACTORS


# ═══════════════════════════════════════════════════════════════════════════
# Store Events in DB Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreEventsInDB:
    """Tests for store_events_in_db."""

    def test_store_events(self, tmp_data_dir):
        from omnibrain.db import OmniBrainDB
        from omnibrain.tools.calendar_tools import store_events_in_db

        db = OmniBrainDB(tmp_data_dir)
        now = datetime.now(timezone.utc)

        events = [
            CalendarEvent(
                id="evt_1",
                title="Morning Standup",
                start_time=now.replace(hour=9),
                end_time=now.replace(hour=9, minute=30),
                attendees=["alice@test.com"],
                location="Zoom",
            ),
            CalendarEvent(
                id="evt_2",
                title="Sprint Review",
                start_time=now.replace(hour=14),
                end_time=now.replace(hour=15),
                attendees=["bob@test.com", "charlie@test.com"],
                description="Sprint 42 review",
                is_recurring=True,
            ),
        ]

        stored = store_events_in_db(events, db)
        assert stored == 2

        # Verify events are in DB
        stats = db.get_stats()
        assert stats["events"] >= 2

    def test_store_empty_events(self, tmp_data_dir):
        from omnibrain.db import OmniBrainDB
        from omnibrain.tools.calendar_tools import store_events_in_db

        db = OmniBrainDB(tmp_data_dir)
        stored = store_events_in_db([], db)
        assert stored == 0

    def test_store_events_error_handling(self):
        from omnibrain.tools.calendar_tools import store_events_in_db

        mock_db = MagicMock()
        mock_db.insert_event.side_effect = Exception("DB error")

        now = datetime.now(timezone.utc)
        events = [
            CalendarEvent(
                id="evt_1",
                title="Test",
                start_time=now,
                end_time=now + timedelta(hours=1),
            ),
        ]

        # Should not raise, just log warning and return 0
        stored = store_events_in_db(events, mock_db)
        assert stored == 0


# ═══════════════════════════════════════════════════════════════════════════
# Tool Schemas Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestToolSchemas:
    """Tests for calendar tool schema definitions."""

    def test_schemas_list(self):
        from omnibrain.tools.calendar_tools import CALENDAR_TOOL_SCHEMAS
        assert len(CALENDAR_TOOL_SCHEMAS) == 3

    def test_get_today_events_schema(self):
        from omnibrain.tools.calendar_tools import GET_TODAY_EVENTS_SCHEMA

        assert GET_TODAY_EVENTS_SCHEMA["name"] == "get_today_events"
        assert "description" in GET_TODAY_EVENTS_SCHEMA
        assert "parameters" in GET_TODAY_EVENTS_SCHEMA

    def test_get_upcoming_events_schema(self):
        from omnibrain.tools.calendar_tools import GET_UPCOMING_EVENTS_SCHEMA

        assert GET_UPCOMING_EVENTS_SCHEMA["name"] == "get_upcoming_events"
        props = GET_UPCOMING_EVENTS_SCHEMA["parameters"]["properties"]
        assert "days" in props
        assert "max_results" in props

    def test_generate_meeting_brief_schema(self):
        from omnibrain.tools.calendar_tools import GENERATE_MEETING_BRIEF_SCHEMA

        assert GENERATE_MEETING_BRIEF_SCHEMA["name"] == "generate_meeting_brief"
        assert "event_id" in GENERATE_MEETING_BRIEF_SCHEMA["parameters"]["properties"]
        assert "event_id" in GENERATE_MEETING_BRIEF_SCHEMA["parameters"]["required"]

    def test_schemas_importable_from_tools_init(self):
        from omnibrain.tools import (
            CALENDAR_TOOL_SCHEMAS,
            GET_TODAY_EVENTS_SCHEMA,
            GET_UPCOMING_EVENTS_SCHEMA,
            GENERATE_MEETING_BRIEF_SCHEMA,
            get_today_events,
            get_upcoming_events,
            generate_meeting_brief,
            store_events_in_db,
        )
        # Just verify imports work
        assert callable(get_today_events)
        assert callable(get_upcoming_events)
        assert callable(generate_meeting_brief)
        assert callable(store_events_in_db)

    def test_integrations_importable(self):
        from omnibrain.integrations import CalendarClient, CalendarAuthError
        assert CalendarClient is not None
        assert CalendarAuthError is not None


# ═══════════════════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """Tests for calendar tool helper functions."""

    def test_event_to_agent_view(self):
        from omnibrain.tools.calendar_tools import _event_to_agent_view

        now = datetime.now(timezone.utc)
        event = CalendarEvent(
            id="evt_1",
            title="Team Meeting",
            start_time=now,
            end_time=now + timedelta(hours=1),
            attendees=["a@t.com", "b@t.com"],
            location="Room 42",
            description="Important meeting " * 100,  # Long description
            is_recurring=True,
        )

        view = _event_to_agent_view(event)
        assert view["id"] == "evt_1"
        assert view["title"] == "Team Meeting"
        assert view["duration_minutes"] == 60
        assert view["attendees_summary"] == "2 people"
        assert view["location"] == "Room 42"
        assert view["is_recurring"] is True
        # Description truncated to 300 chars
        assert len(view["description"]) <= 300

    def test_make_day_summary_no_events(self):
        from omnibrain.tools.calendar_tools import _make_day_summary

        assert _make_day_summary([]) == "No events today."

    def test_make_day_summary_with_events(self):
        from omnibrain.tools.calendar_tools import _make_day_summary

        now = datetime.now(timezone.utc)
        events = [
            CalendarEvent(
                id="1", title="Standup",
                start_time=now.replace(hour=9, minute=0),
                end_time=now.replace(hour=9, minute=30),
            ),
            CalendarEvent(
                id="2", title="Review",
                start_time=now.replace(hour=14, minute=0),
                end_time=now.replace(hour=15, minute=0),
            ),
        ]
        summary = _make_day_summary(events)
        assert "2 events today" in summary
        assert "Standup" in summary
        assert "Review" in summary
        assert "1h 30m" in summary

    def test_make_week_summary_no_events(self):
        from omnibrain.tools.calendar_tools import _make_week_summary

        assert "No events" in _make_week_summary([], 7)

    def test_make_week_summary_with_events(self):
        from omnibrain.tools.calendar_tools import _make_week_summary

        now = datetime.now(timezone.utc)
        events = [
            CalendarEvent(
                id="1", title="Monday Call",
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=1, hours=1),
            ),
        ]
        summary = _make_week_summary(events, 7)
        assert "1 events" in summary
        assert "Monday Call" in summary

    def test_generate_prep_notes(self):
        from omnibrain.tools.calendar_tools import _generate_prep_notes

        now = datetime.now(timezone.utc)
        event = CalendarEvent(
            id="1", title="Board Meeting",
            start_time=now, end_time=now + timedelta(hours=2),
            location="Board Room",
        )
        attendees = [
            {"email": "a@t.com", "name": "Alice", "relationship": "colleague", "interaction_count": 10},
            {"email": "b@t.com", "name": "", "interaction_count": 0},
        ]

        notes = _generate_prep_notes(event, attendees)
        assert "Board Meeting" in notes
        assert "120 minutes" in notes
        assert "Board Room" in notes
        assert "Alice" in notes
        assert "b@t.com" in notes


# ═══════════════════════════════════════════════════════════════════════════
# ApprovalGate Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalGate:
    """Verify calendar tools are in pre-approved set."""

    def test_calendar_tools_preapproved(self):
        from omnibrain.models import ApprovalGate

        assert ApprovalGate.needs_approval("get_today_events") is False
        assert ApprovalGate.needs_approval("get_upcoming_events") is False
        assert ApprovalGate.needs_approval("generate_meeting_brief") is False

    def test_create_event_needs_approval(self):
        from omnibrain.models import ApprovalGate

        assert ApprovalGate.needs_approval("create_event") is True

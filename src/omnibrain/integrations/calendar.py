"""
OmniBrain — Google Calendar Integration

Async-friendly Google Calendar client built on google-api-python-client.
Handles authentication (shared with Gmail), event fetching, parsing,
and searching. Phase 1 is read-only; Phase 2 adds create/modify.

Architecture:
    CalendarClient (this file)
    └── uses shared OAuth token from setup_google.py
    └── returns CalendarEvent dataclasses
    └── stores events in db.events via tools layer
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from omnibrain.auth.google_oauth import CALENDAR_SCOPES
from omnibrain.integrations import _is_auth_error
from omnibrain.models import CalendarEvent

logger = logging.getLogger("omnibrain.integrations.calendar")


class CalendarAuthError(Exception):
    """Raised when Calendar authentication fails."""


class CalendarClient:
    """Google Calendar API client — fetches and parses events.

    Shares OAuth token with GmailClient (both use setup_google.py).

    Usage:
        client = CalendarClient(data_dir=Path("~/.omnibrain"))
        if client.authenticate():
            events = client.get_today_events()
            for event in events:
                print(event.title, event.start_time, event.duration_minutes)
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._token_path = data_dir / "google_token.json"
        self._service: Any = None
        self._creds: Any = None

    # ── Authentication ──

    def authenticate(self) -> bool:
        """Load and validate credentials. Returns True if authenticated.

        Uses the same token.json as GmailClient.
        """
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            logger.error("google-auth not installed.")
            return False

        if not self._token_path.exists():
            logger.warning(f"No Google token at {self._token_path}. Run 'omnibrain setup-google'.")
            return False

        try:
            self._creds = Credentials.from_authorized_user_file(
                str(self._token_path),
                scopes=CALENDAR_SCOPES,
            )
        except Exception as e:
            logger.error(f"Failed to load token: {e}")
            return False

        if self._creds.expired and self._creds.refresh_token:
            try:
                self._creds.refresh(Request())
                logger.info("Google token refreshed for Calendar")
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")
                return False

        if not self._creds.valid:
            logger.error("Google credentials invalid for Calendar.")
            return False

        try:
            from googleapiclient.discovery import build
            self._service = build("calendar", "v3", credentials=self._creds)
            logger.info("Calendar client authenticated")
            return True
        except Exception as e:
            logger.error(f"Failed to build Calendar service: {e}")
            return False

    @property
    def is_authenticated(self) -> bool:
        return self._service is not None and self._creds is not None and self._creds.valid

    # ── Fetch Events ──

    def get_today_events(self) -> list[CalendarEvent]:
        """Get all events for today.

        Returns events from midnight to midnight in local timezone.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        return self._fetch_events(
            time_min=start_of_day,
            time_max=end_of_day,
        )

    def get_upcoming_events(self, days: int = 7, max_results: int = 50) -> list[CalendarEvent]:
        """Get upcoming events for next N days.

        Args:
            days: Number of days to look ahead.
            max_results: Maximum events to return.

        Returns:
            List of CalendarEvent, sorted by start time.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        now = datetime.now(timezone.utc)
        future = now + timedelta(days=days)

        return self._fetch_events(
            time_min=now,
            time_max=future,
            max_results=max_results,
        )

    def get_event(self, event_id: str) -> CalendarEvent | None:
        """Fetch a single event by ID.

        Args:
            event_id: The Google Calendar event ID.

        Returns:
            CalendarEvent or None if not found.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        try:
            event_data = self._service.events().get(
                calendarId="primary",
                eventId=event_id,
            ).execute()
            return _parse_event(event_data)
        except Exception as e:
            logger.warning(f"Failed to get event {event_id}: {e}")
            return None

    def search_events(
        self,
        query: str,
        days_back: int = 30,
        days_forward: int = 30,
        max_results: int = 20,
    ) -> list[CalendarEvent]:
        """Search calendar events by text query.

        Args:
            query: Free-text search (searches title, description, location).
            days_back: How far back to search.
            days_forward: How far forward to search.
            max_results: Maximum results.

        Returns:
            List of matching CalendarEvent objects.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        now = datetime.now(timezone.utc)
        time_min = now - timedelta(days=days_back)
        time_max = now + timedelta(days=days_forward)

        try:
            result = self._service.events().list(
                calendarId="primary",
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                q=query,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events_data = result.get("items", [])
            events = []
            for ed in events_data:
                event = _parse_event(ed)
                if event:
                    events.append(event)
            return events

        except Exception as e:
            logger.error(f"Calendar search failed for '{query}': {e}")
            raise

    # ── Write Operations ──

    def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime | None = None,
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> CalendarEvent | None:
        """Create a new event on Google Calendar.

        Args:
            title: Event title/summary.
            start_time: When the event starts.
            end_time: When the event ends (defaults to start_time + 1 hour).
            description: Event description.
            location: Event location.
            attendees: List of attendee email addresses.

        Returns:
            The created CalendarEvent, or None on failure.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        if end_time is None:
            end_time = start_time + timedelta(hours=1)

        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]

        try:
            result = self._service.events().insert(
                calendarId="primary", body=body,
            ).execute()
            event = _parse_event(result)
            if event:
                logger.info(f"Created Google Calendar event: {title} ({event.id})")
            return event
        except Exception as e:
            logger.error(f"Failed to create calendar event '{title}': {e}")
            return None

    def delete_event(self, event_id: str) -> bool:
        """Delete an event from Google Calendar.

        Args:
            event_id: The Google Calendar event ID.

        Returns:
            True if deleted, False on failure.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        try:
            self._service.events().delete(
                calendarId="primary", eventId=event_id,
            ).execute()
            logger.info(f"Deleted Google Calendar event: {event_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete calendar event {event_id}: {e}")
            return False

    def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> CalendarEvent | None:
        """Update an existing Google Calendar event.

        Only provided fields are changed; None fields are left as-is.

        Returns:
            The updated CalendarEvent, or None on failure.
        """
        if not self.is_authenticated:
            raise CalendarAuthError("Not authenticated.")

        try:
            # Fetch current event to merge
            current = self._service.events().get(
                calendarId="primary", eventId=event_id,
            ).execute()

            if title is not None:
                current["summary"] = title
            if start_time is not None:
                current["start"] = {"dateTime": start_time.isoformat(), "timeZone": "UTC"}
            if end_time is not None:
                current["end"] = {"dateTime": end_time.isoformat(), "timeZone": "UTC"}
            if description is not None:
                current["description"] = description
            if location is not None:
                current["location"] = location

            result = self._service.events().update(
                calendarId="primary", eventId=event_id, body=current,
            ).execute()
            event = _parse_event(result)
            if event:
                logger.info(f"Updated Google Calendar event: {event_id}")
            return event
        except Exception as e:
            logger.warning(f"Failed to update calendar event {event_id}: {e}")
            return None

    # ── Internal ──

    def _fetch_events(
        self,
        time_min: datetime,
        time_max: datetime,
        max_results: int = 100,
    ) -> list[CalendarEvent]:
        """Fetch events in a time range from primary calendar."""
        try:
            result = self._service.events().list(
                calendarId="primary",
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events_data = result.get("items", [])
            if not events_data:
                logger.info("No calendar events found in range")
                return []

            events = []
            for ed in events_data:
                event = _parse_event(ed)
                if event:
                    events.append(event)

            logger.info(f"Fetched {len(events)} calendar events")
            return events

        except Exception as e:
            if _is_auth_error(e):
                raise CalendarAuthError(f"Auth error: {e}") from e
            logger.error(f"Failed to fetch events: {e}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
# Parsing Helpers (module-level for testability)
# ═══════════════════════════════════════════════════════════════════════════


def _parse_event(event_data: dict[str, Any]) -> CalendarEvent | None:
    """Parse a Google Calendar API event response into a CalendarEvent.

    Handles both dateTime (specific time) and date (all-day) events.
    """
    try:
        event_id = event_data.get("id", "")
        title = event_data.get("summary", "(No title)")
        description = event_data.get("description", "")
        location = event_data.get("location", "")

        # Parse start/end times (handle all-day vs timed events)
        start_data = event_data.get("start", {})
        end_data = event_data.get("end", {})

        start_time = _parse_event_time(start_data)
        end_time = _parse_event_time(end_data)

        if not start_time or not end_time:
            logger.warning(f"Event {event_id} has no start/end time")
            return None

        # Parse attendees
        attendees = []
        for att in event_data.get("attendees", []):
            email = att.get("email", "")
            if email:
                attendees.append(email)

        # Check if recurring
        is_recurring = bool(event_data.get("recurringEventId"))

        return CalendarEvent(
            id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            location=location,
            description=description,
            is_recurring=is_recurring,
        )

    except Exception as e:
        logger.warning(f"Failed to parse event: {e}")
        return None


def _parse_event_time(time_data: dict[str, str]) -> datetime | None:
    """Parse Google Calendar time object to datetime.

    Google Calendar returns either:
    - {"dateTime": "2026-02-15T10:00:00+01:00"} for timed events
    - {"date": "2026-02-15"} for all-day events
    """
    if "dateTime" in time_data:
        try:
            return datetime.fromisoformat(time_data["dateTime"])
        except ValueError:
            return None
    elif "date" in time_data:
        try:
            return datetime.strptime(time_data["date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None
    return None


# _is_auth_error is imported from omnibrain.integrations (shared helper)

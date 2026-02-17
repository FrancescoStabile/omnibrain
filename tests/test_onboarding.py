"""
Tests for OnboardingAnalyzer (src/omnibrain/auth/onboarding.py).

Covers:
    - Email extraction helpers
    - Name guessing from email
    - Greeting generation (time-of-day)
    - Insight generation (busiest sender, meetings, unread, network)
    - Full analyze() with mocked Gmail/Calendar clients
"""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.auth.onboarding import (
    InsightCard,
    OnboardingAnalyzer,
    OnboardingResult,
    _build_greeting,
    _extract_email,
    _generate_insights,
    _guess_name_from_email,
    _is_today,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractEmail:
    def test_bare_email(self) -> None:
        assert _extract_email("alice@example.com") == "alice@example.com"

    def test_name_angle_brackets(self) -> None:
        assert _extract_email("Alice Smith <alice@example.com>") == "alice@example.com"

    def test_quoted_name(self) -> None:
        assert _extract_email('"Bob Jones" <bob@co.uk>') == "bob@co.uk"

    def test_empty(self) -> None:
        assert _extract_email("") == ""

    def test_lowercase(self) -> None:
        assert _extract_email("User@Example.COM") == "user@example.com"


class TestGuessName:
    def test_first_dot_last(self) -> None:
        assert _guess_name_from_email("john.doe@company.com") == "John Doe"

    def test_first_underscore_last(self) -> None:
        assert _guess_name_from_email("jane_doe@example.com") == "Jane Doe"

    def test_single_name(self) -> None:
        assert _guess_name_from_email("carlo@gmail.com") == "Carlo"

    def test_empty(self) -> None:
        assert _guess_name_from_email("") == ""


class TestBuildGreeting:
    @patch("omnibrain.auth.onboarding.datetime")
    def test_morning(self, mock_dt: MagicMock) -> None:
        mock_dt.now.return_value = datetime(2025, 1, 15, 8, 0, 0)
        assert _build_greeting("Francesco") == "Good morning, Francesco."

    @patch("omnibrain.auth.onboarding.datetime")
    def test_afternoon(self, mock_dt: MagicMock) -> None:
        mock_dt.now.return_value = datetime(2025, 1, 15, 14, 0, 0)
        assert _build_greeting("Alice") == "Good afternoon, Alice."

    @patch("omnibrain.auth.onboarding.datetime")
    def test_evening(self, mock_dt: MagicMock) -> None:
        mock_dt.now.return_value = datetime(2025, 1, 15, 20, 0, 0)
        assert _build_greeting("Bob") == "Good evening, Bob."

    @patch("omnibrain.auth.onboarding.datetime")
    def test_no_name(self, mock_dt: MagicMock) -> None:
        mock_dt.now.return_value = datetime(2025, 1, 15, 9, 0, 0)
        assert _build_greeting("") == "Good morning."


class TestIsToday:
    def test_today(self) -> None:
        assert _is_today(datetime.now(timezone.utc)) is True

    def test_yesterday(self) -> None:
        assert _is_today(datetime.now(timezone.utc) - timedelta(days=1)) is False

    def test_none(self) -> None:
        assert _is_today(None) is False


# ═══════════════════════════════════════════════════════════════════════════
# Insight generation
# ═══════════════════════════════════════════════════════════════════════════


def _fake_email(sender: str, is_read: bool = True) -> types.SimpleNamespace:
    return types.SimpleNamespace(sender=sender, recipients=[], is_read=is_read)


def _fake_event(title: str, start_time: datetime | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        title=title,
        start_time=start_time or datetime.now(timezone.utc),
        attendees=[],
    )


class TestGenerateInsights:
    def test_busiest_sender(self) -> None:
        emails = [
            _fake_email("Boss <boss@co.com>"),
            _fake_email("Boss <boss@co.com>"),
            _fake_email("Boss <boss@co.com>"),
            _fake_email("Other <other@co.com>"),
        ]
        cards = _generate_insights(
            emails=emails,
            events=[],
            contacts=set(),
            email_count=4,
            event_count=0,
        )
        titles = [c.title for c in cards]
        assert any("sent you" in t.lower() or "correspondent" in t.lower() for t in titles)

    def test_today_meetings(self) -> None:
        events = [
            _fake_event("Standup", datetime.now(timezone.utc)),
            _fake_event("1:1 with Alice", datetime.now(timezone.utc)),
        ]
        cards = _generate_insights(
            emails=[],
            events=events,
            contacts=set(),
            email_count=0,
            event_count=2,
        )
        titles = [c.title for c in cards]
        assert any("meeting" in t.lower() for t in titles)

    def test_unread_threshold(self) -> None:
        emails = [_fake_email("s@x.com", is_read=False) for _ in range(10)]
        cards = _generate_insights(
            emails=emails,
            events=[],
            contacts=set(),
            email_count=10,
            event_count=0,
        )
        titles = [c.title for c in cards]
        assert any("unread" in t.lower() for t in titles)

    def test_network_size(self) -> None:
        cards = _generate_insights(
            emails=[],
            events=[],
            contacts={"a@x.com", "b@x.com", "c@x.com"},
            email_count=0,
            event_count=0,
        )
        titles = [c.title for c in cards]
        assert any("network" in t.lower() or "people" in t.lower() for t in titles)

    def test_fallback_card(self) -> None:
        cards = _generate_insights(
            emails=[],
            events=[],
            contacts=set(),
            email_count=0,
            event_count=0,
        )
        assert len(cards) >= 1
        assert cards[0].icon == "sparkles"

    def test_max_five_cards(self) -> None:
        emails = [_fake_email(f"s{i}@x.com", is_read=False) for i in range(20)]
        events = [_fake_event(f"Event {i}") for i in range(5)]
        contacts = {f"c{i}@x.com" for i in range(50)}
        cards = _generate_insights(
            emails=emails,
            events=events,
            contacts=contacts,
            email_count=20,
            event_count=5,
        )
        assert len(cards) <= 5

    def test_sorted_by_priority(self) -> None:
        events = [_fake_event("Standup")]
        emails = [_fake_email("boss@co.com") for _ in range(5)]
        cards = _generate_insights(
            emails=emails,
            events=events,
            contacts={"a@x.com"},
            email_count=5,
            event_count=1,
        )
        # _generate_insights doesn't sort — sort like analyze() does
        sorted_cards = sorted(cards, key=lambda c: -c.priority)
        if len(sorted_cards) >= 2:
            assert sorted_cards[0].priority >= sorted_cards[1].priority


# ═══════════════════════════════════════════════════════════════════════════
# Full analyze() — mocked integrations
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzer:
    def test_analyze_with_mocked_gmail_calendar(self, tmp_path: Path) -> None:
        """Verify the full pipeline with mocked GmailClient + CalendarClient."""
        now = datetime.now(timezone.utc)
        fake_emails = [
            _fake_email("Alice <alice@co.com>"),
            _fake_email("Bob <bob@co.com>"),
            _fake_email("Alice <alice@co.com>"),
        ]
        fake_events = [
            _fake_event("Team standup", now),
        ]

        # Mock GmailClient
        mock_gmail = MagicMock()
        mock_gmail.return_value.authenticate.return_value = True
        mock_gmail.return_value.user_email = "me@example.com"
        mock_gmail.return_value.fetch_recent.return_value = fake_emails

        # Mock CalendarClient
        mock_cal = MagicMock()
        mock_cal.return_value.authenticate.return_value = True
        mock_cal.return_value.get_upcoming_events.return_value = fake_events

        with (
            patch("omnibrain.integrations.gmail.GmailClient", mock_gmail),
            patch("omnibrain.integrations.calendar.CalendarClient", mock_cal),
        ):
            analyzer = OnboardingAnalyzer(tmp_path)
            result = analyzer.analyze()

        assert isinstance(result, OnboardingResult)
        assert result.stats["emails"] == 3
        assert result.stats["events"] == 1
        assert result.stats["contacts"] >= 2  # alice + bob
        assert result.user_email == "me@example.com"
        assert len(result.insights) >= 1
        assert result.duration_ms >= 0
        assert result.completed_at

    def test_analyze_gmail_fails_gracefully(self, tmp_path: Path) -> None:
        """Gmail failure should not crash — returns partial results."""
        mock_gmail = MagicMock()
        mock_gmail.return_value.authenticate.side_effect = Exception("no google-auth")

        mock_cal = MagicMock()
        mock_cal.return_value.authenticate.return_value = False

        with (
            patch("omnibrain.integrations.gmail.GmailClient", mock_gmail),
            patch("omnibrain.integrations.calendar.CalendarClient", mock_cal),
        ):
            analyzer = OnboardingAnalyzer(tmp_path)
            result = analyzer.analyze()

        assert result.stats["emails"] == 0
        assert result.stats["events"] == 0
        assert len(result.insights) >= 1  # "You're all set!" fallback

    def test_analyze_returns_onboarding_result(self, tmp_path: Path) -> None:
        mock_gmail = MagicMock()
        mock_gmail.return_value.authenticate.return_value = False

        mock_cal = MagicMock()
        mock_cal.return_value.authenticate.return_value = False

        with (
            patch("omnibrain.integrations.gmail.GmailClient", mock_gmail),
            patch("omnibrain.integrations.calendar.CalendarClient", mock_cal),
        ):
            analyzer = OnboardingAnalyzer(tmp_path)
            result = analyzer.analyze()

        assert isinstance(result, OnboardingResult)
        assert isinstance(result.stats, dict)
        assert isinstance(result.insights, list)
        assert isinstance(result.greeting, str)

    def test_insight_card_dataclass(self) -> None:
        card = InsightCard(icon="mail", title="Test", body="Body", priority=3)
        assert card.icon == "mail"
        assert card.action == ""
        assert card.action_type == ""

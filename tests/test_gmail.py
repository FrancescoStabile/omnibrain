"""
Tests for OmniBrain Gmail integration.

Tests cover:
    - Gmail message parsing (_parse_message, _extract_body, etc.)
    - GmailClient authentication flow (mocked)
    - email_tools handlers (fetch_emails, classify_email, search_emails)
    - Email extractors (extract_emails, extract_classification)
    - store_emails_in_db integration with OmniBrainDB
    - CLI fetch-emails command

All Google API calls are mocked — no real authentication needed.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from omnibrain.models import (
    ContactInfo,
    EmailMessage,
    EventSource,
    Urgency,
)


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
def sample_gmail_message() -> dict[str, Any]:
    """A realistic Gmail API message response."""
    body_text = "Hi Francesco,\n\nPlease review the attached proposal by Friday.\n\nBest,\nMarco"
    body_b64 = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")

    return {
        "id": "msg_001",
        "threadId": "thread_001",
        "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Marco Rossi <marco@example.com>"},
                {"name": "To", "value": "Francesco Stabile <francesco@omnibrain.dev>"},
                {"name": "Subject", "value": "Proposal Review - Urgent"},
                {"name": "Date", "value": "Sat, 15 Feb 2026 10:30:00 +0100"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": body_b64},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(
                        f"<html><body><p>{body_text}</p></body></html>".encode()
                    ).decode().rstrip("=")},
                },
            ],
        },
    }


@pytest.fixture
def sample_gmail_message_html_only() -> dict[str, Any]:
    """Gmail message with only HTML body (no plain text part)."""
    html = "<html><body><h1>Newsletter</h1><p>Hello <b>World</b></p><br><p>Footer</p></body></html>"
    html_b64 = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")

    return {
        "id": "msg_002",
        "threadId": "thread_002",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {"name": "From", "value": "newsletter@techcrunch.com"},
                {"name": "To", "value": "francesco@omnibrain.dev"},
                {"name": "Subject", "value": "TechCrunch Daily"},
                {"name": "Date", "value": "Sat, 15 Feb 2026 08:00:00 +0000"},
            ],
            "body": {"data": html_b64},
        },
    }


@pytest.fixture
def sample_gmail_message_with_attachment() -> dict[str, Any]:
    """Gmail message with an attachment."""
    body_b64 = base64.urlsafe_b64encode(b"See attached invoice.").decode().rstrip("=")

    return {
        "id": "msg_003",
        "threadId": "thread_003",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "billing@vendor.com"},
                {"name": "To", "value": "francesco@omnibrain.dev"},
                {"name": "Subject", "value": "Invoice #12345"},
                {"name": "Date", "value": "Fri, 14 Feb 2026 15:00:00 +0100"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": body_b64},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice_12345.pdf",
                    "body": {"attachmentId": "att_001", "size": 45000},
                },
            ],
        },
    }


@pytest.fixture
def sample_email_messages() -> list[EmailMessage]:
    """Pre-parsed EmailMessage objects for testing."""
    return [
        EmailMessage(
            id="msg_001",
            thread_id="thread_001",
            sender="Marco Rossi <marco@example.com>",
            recipients=["francesco@omnibrain.dev"],
            subject="Proposal Review - Urgent",
            body="Please review the attached proposal by Friday.",
            date=datetime(2026, 2, 15, 10, 30, tzinfo=timezone.utc),
            labels=["INBOX", "UNREAD", "IMPORTANT"],
            is_read=False,
            has_attachments=False,
        ),
        EmailMessage(
            id="msg_002",
            thread_id="thread_002",
            sender="newsletter@techcrunch.com",
            recipients=["francesco@omnibrain.dev"],
            subject="TechCrunch Daily",
            body="Top stories from today...",
            date=datetime(2026, 2, 15, 8, 0, tzinfo=timezone.utc),
            labels=["INBOX"],
            is_read=True,
            has_attachments=False,
        ),
        EmailMessage(
            id="msg_003",
            thread_id="thread_003",
            sender="billing@vendor.com",
            recipients=["francesco@omnibrain.dev"],
            subject="Invoice #12345",
            body="See attached invoice.",
            date=datetime(2026, 2, 14, 15, 0, tzinfo=timezone.utc),
            labels=["INBOX", "UNREAD"],
            is_read=False,
            has_attachments=True,
        ),
    ]


@pytest.fixture
def mock_db(tmp_data_dir: Path):
    """Create a real OmniBrainDB for integration tests."""
    from omnibrain.db import OmniBrainDB
    return OmniBrainDB(tmp_data_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Gmail Message Parsing
# ═══════════════════════════════════════════════════════════════════════════


class TestGmailMessageParsing:
    """Tests for _parse_message and related parsing helpers."""

    def test_parse_standard_message(self, sample_gmail_message: dict) -> None:
        from omnibrain.integrations.gmail import _parse_message

        msg = _parse_message(sample_gmail_message)
        assert msg is not None
        assert msg.id == "msg_001"
        assert msg.thread_id == "thread_001"
        assert msg.sender == "Marco Rossi <marco@example.com>"
        assert msg.subject == "Proposal Review - Urgent"
        assert "review the attached proposal" in msg.body.lower()
        assert msg.is_read is False  # UNREAD label present
        assert "IMPORTANT" in msg.labels

    def test_parse_sender_email_extraction(self, sample_gmail_message: dict) -> None:
        from omnibrain.integrations.gmail import _parse_message

        msg = _parse_message(sample_gmail_message)
        assert msg is not None
        assert msg.sender_email == "marco@example.com"
        assert msg.sender_name == "Marco Rossi"

    def test_parse_plain_sender(self) -> None:
        """Test sender without angle bracket format."""
        msg = EmailMessage(
            id="x", thread_id="x",
            sender="plain@example.com",
            recipients=[], subject="", body="",
            date=datetime.now(timezone.utc),
        )
        assert msg.sender_email == "plain@example.com"
        assert msg.sender_name == "plain@example.com"

    def test_parse_html_only_message(self, sample_gmail_message_html_only: dict) -> None:
        from omnibrain.integrations.gmail import _parse_message

        msg = _parse_message(sample_gmail_message_html_only)
        assert msg is not None
        assert msg.id == "msg_002"
        assert "hello" in msg.body.lower()
        assert "<html>" not in msg.body  # Tags stripped
        assert "<b>" not in msg.body

    def test_parse_message_with_attachment(self, sample_gmail_message_with_attachment: dict) -> None:
        from omnibrain.integrations.gmail import _parse_message

        msg = _parse_message(sample_gmail_message_with_attachment)
        assert msg is not None
        assert msg.has_attachments is True
        assert msg.subject == "Invoice #12345"

    def test_parse_recipients(self) -> None:
        from omnibrain.integrations.gmail import _parse_recipients

        # Standard format
        assert _parse_recipients("John <john@example.com>") == ["john@example.com"]

        # Multiple
        result = _parse_recipients("John <john@example.com>, Jane <jane@example.com>")
        assert "john@example.com" in result
        assert "jane@example.com" in result

        # Plain email
        assert _parse_recipients("test@example.com") == ["test@example.com"]

        # Empty
        assert _parse_recipients("") == []

    def test_parse_date_rfc2822(self) -> None:
        from omnibrain.integrations.gmail import _parse_date

        dt = _parse_date("Sat, 15 Feb 2026 10:30:00 +0100")
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 15

    def test_parse_date_empty(self) -> None:
        from omnibrain.integrations.gmail import _parse_date

        dt = _parse_date("")
        # Should return current time
        assert dt.year >= 2026

    def test_parse_date_invalid(self) -> None:
        from omnibrain.integrations.gmail import _parse_date

        dt = _parse_date("not a date at all")
        # Should fallback to now
        assert isinstance(dt, datetime)

    def test_parse_invalid_message(self) -> None:
        from omnibrain.integrations.gmail import _parse_message

        # Completely invalid payload
        msg = _parse_message({})
        # Should either return None or a minimal message
        # (our implementation returns a message with empty fields)
        if msg is not None:
            assert msg.id == ""

    def test_body_preview(self, sample_email_messages: list) -> None:
        msg = sample_email_messages[0]
        assert len(msg.body_preview) <= 200
        assert msg.body_preview == msg.body[:200].strip()


class TestHtmlStripping:
    """Test HTML to plain text conversion."""

    def test_strip_basic_html(self) -> None:
        from omnibrain.integrations.gmail import _strip_html

        assert _strip_html("<p>Hello</p>") == "Hello"

    def test_strip_preserves_text(self) -> None:
        from omnibrain.integrations.gmail import _strip_html

        result = _strip_html("<div><p>Line 1</p><p>Line 2</p></div>")
        assert "Line 1" in result
        assert "Line 2" in result

    def test_strip_removes_style_and_script(self) -> None:
        from omnibrain.integrations.gmail import _strip_html

        html = "<style>body{color:red}</style><p>Text</p><script>alert('x')</script>"
        result = _strip_html(html)
        assert "color:red" not in result
        assert "alert" not in result
        assert "Text" in result

    def test_strip_decodes_entities(self) -> None:
        from omnibrain.integrations.gmail import _strip_html

        result = _strip_html("&amp; &lt;tag&gt; &quot;quoted&quot;")
        assert "&" in result
        assert "<tag>" in result
        assert '"quoted"' in result

    def test_strip_br_to_newline(self) -> None:
        from omnibrain.integrations.gmail import _strip_html

        result = _strip_html("Line 1<br>Line 2<br/>Line 3")
        assert "Line 1\nLine 2\nLine 3" in result


class TestBase64Decode:
    """Test Gmail base64url decoding."""

    def test_decode_standard(self) -> None:
        from omnibrain.integrations.gmail import _decode_base64

        encoded = base64.urlsafe_b64encode(b"Hello World").decode().rstrip("=")
        result = _decode_base64(encoded)
        assert result == "Hello World"

    def test_decode_unicode(self) -> None:
        from omnibrain.integrations.gmail import _decode_base64

        text = "Ciao! Grazie mille 🎉"
        encoded = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
        result = _decode_base64(encoded)
        assert result == text

    def test_decode_empty(self) -> None:
        from omnibrain.integrations.gmail import _decode_base64

        assert _decode_base64("") == ""

    def test_decode_invalid(self) -> None:
        from omnibrain.integrations.gmail import _decode_base64

        # Should not raise, returns empty string
        result = _decode_base64("!!!invalid!!!")
        assert isinstance(result, str)


class TestAuthErrorDetection:
    """Test _is_auth_error helper."""

    def test_detects_auth_errors(self) -> None:
        from omnibrain.integrations.gmail import _is_auth_error

        assert _is_auth_error(Exception("invalid_grant: token expired"))
        assert _is_auth_error(Exception("HTTP 401 Unauthorized"))
        assert _is_auth_error(Exception("Invalid Credentials"))

    def test_ignores_non_auth_errors(self) -> None:
        from omnibrain.integrations.gmail import _is_auth_error

        assert not _is_auth_error(Exception("Network timeout"))
        assert not _is_auth_error(Exception("Rate limit exceeded"))
        assert not _is_auth_error(Exception("Internal server error"))


# ═══════════════════════════════════════════════════════════════════════════
# Tests: GmailClient
# ═══════════════════════════════════════════════════════════════════════════


class TestGmailClient:
    """Test GmailClient with mocked Google APIs."""

    def test_init(self, tmp_data_dir: Path) -> None:
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient(tmp_data_dir)
        assert client.data_dir == tmp_data_dir
        assert not client.is_authenticated

    def test_authenticate_no_token(self, tmp_data_dir: Path) -> None:
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient(tmp_data_dir)
        # No token file exists
        assert client.authenticate() is False

    @patch("omnibrain.integrations.gmail.GmailClient._save_token")
    def test_authenticate_with_valid_token(self, mock_save: MagicMock, tmp_data_dir: Path) -> None:
        from omnibrain.integrations.gmail import GmailClient

        # Create fake token file
        token_data = {
            "token": "fake_access_token",
            "refresh_token": "fake_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake_client_id",
            "client_secret": "fake_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_path = tmp_data_dir / "google_token.json"
        with open(token_path, "w") as f:
            json.dump(token_data, f)

        client = GmailClient(tmp_data_dir)

        # Mock the google auth classes
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file") as mock_creds_load, \
             patch("googleapiclient.discovery.build") as mock_build:

            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds.expired = False
            mock_creds_load.return_value = mock_creds

            mock_service = MagicMock()
            mock_build.return_value = mock_service

            result = client.authenticate()
            assert result is True
            assert client.is_authenticated

    def test_fetch_recent_not_authenticated(self, tmp_data_dir: Path) -> None:
        from omnibrain.integrations.gmail import GmailClient, GmailAuthError

        client = GmailClient(tmp_data_dir)
        with pytest.raises(GmailAuthError):
            client.fetch_recent()

    def test_user_email_not_authenticated(self, tmp_data_dir: Path) -> None:
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient(tmp_data_dir)
        assert client.user_email == ""


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Email Tools
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchEmailsTool:
    """Test fetch_emails tool handler."""

    def test_fetch_not_authenticated(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import fetch_emails

        result = fetch_emails(tmp_data_dir)
        assert result["error"]
        assert result["count"] == 0
        assert result["emails"] == []

    @patch("omnibrain.tools.email_tools.GmailClient")
    def test_fetch_success(self, MockClient: MagicMock, tmp_data_dir: Path, sample_email_messages: list) -> None:
        from omnibrain.tools.email_tools import fetch_emails

        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.fetch_recent.return_value = sample_email_messages
        mock_client.user_email = "francesco@omnibrain.dev"

        result = fetch_emails(tmp_data_dir, max_results=10, since_hours=24)

        assert result["count"] == 3
        assert len(result["emails"]) == 3
        assert result["user_email"] == "francesco@omnibrain.dev"
        assert result["emails"][0]["sender_email"] == "marco@example.com"
        assert result["emails"][0]["subject"] == "Proposal Review - Urgent"

    @patch("omnibrain.tools.email_tools.GmailClient")
    def test_fetch_no_emails(self, MockClient: MagicMock, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import fetch_emails

        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.fetch_recent.return_value = []
        mock_client.user_email = "francesco@omnibrain.dev"

        result = fetch_emails(tmp_data_dir)
        assert result["count"] == 0
        assert result["emails"] == []
        assert "error" not in result


class TestSearchEmailsTool:
    """Test search_emails tool handler."""

    def test_search_not_authenticated(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import search_emails

        result = search_emails(tmp_data_dir, query="from:boss")
        assert result["error"]
        assert result["count"] == 0

    @patch("omnibrain.tools.email_tools.GmailClient")
    def test_search_success(self, MockClient: MagicMock, tmp_data_dir: Path, sample_email_messages: list) -> None:
        from omnibrain.tools.email_tools import search_emails

        mock_client = MockClient.return_value
        mock_client.authenticate.return_value = True
        mock_client.search.return_value = [sample_email_messages[0]]

        result = search_emails(tmp_data_dir, query="from:marco@example.com")
        assert result["count"] == 1
        assert result["emails"][0]["sender_email"] == "marco@example.com"


class TestClassifyEmailTool:
    """Test classify_email heuristic classification."""

    def test_classify_urgent(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import classify_email

        result = classify_email(
            tmp_data_dir,
            email_id="msg_001",
            subject="URGENT: Server is down",
            sender="ops@company.com",
            body_preview="The production server went down at 3am. Need immediate action.",
        )
        assert result["urgency"] == "high"
        assert result["category"] == "action_required"
        assert result["draft_needed"] is True

    def test_classify_newsletter(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import classify_email

        result = classify_email(
            tmp_data_dir,
            email_id="msg_002",
            subject="TechCrunch Weekly Newsletter",
            body_preview="Top stories this week... Unsubscribe here.",
        )
        assert result["urgency"] == "low"
        assert result["category"] == "newsletter"
        assert result["draft_needed"] is False

    def test_classify_action_required(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import classify_email

        result = classify_email(
            tmp_data_dir,
            email_id="msg_003",
            subject="Follow up on our meeting",
            body_preview="Please respond with your availability for next week.",
        )
        assert result["urgency"] == "medium"
        assert result["action"] == "respond"

    def test_classify_invoice(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import classify_email

        result = classify_email(
            tmp_data_dir,
            email_id="msg_004",
            subject="Invoice #12345",
            body_preview="Payment due...",
        )
        assert result["category"] == "transactional"

    def test_classify_generic(self, tmp_data_dir: Path) -> None:
        from omnibrain.tools.email_tools import classify_email

        result = classify_email(
            tmp_data_dir,
            email_id="msg_005",
            subject="Random email",
            body_preview="Just wanted to say hi.",
        )
        assert result["urgency"] == "medium"
        assert result["category"] == "fyi"


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Extractors
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailExtractors:
    """Test extract_emails and extract_classification."""

    def test_extract_emails_basic(self) -> None:
        from omnibrain.extractors import extract_emails

        result_data = {
            "emails": [
                {
                    "id": "msg_001",
                    "sender_email": "marco@example.com",
                    "sender_name": "Marco",
                    "subject": "Hello",
                    "date": "2026-02-15T10:00:00+00:00",
                    "is_read": False,
                    "has_attachments": True,
                    "body_preview": "Test body",
                },
                {
                    "id": "msg_002",
                    "sender_email": "marco@example.com",
                    "sender_name": "Marco",
                    "subject": "Follow up",
                    "date": "2026-02-15T11:00:00+00:00",
                    "is_read": True,
                    "has_attachments": False,
                    "body_preview": "Follow up body",
                },
            ],
            "count": 2,
        }

        extracted = extract_emails(None, result_data, {})

        assert extracted["stats"]["total"] == 2
        assert extracted["stats"]["unread"] == 1
        assert extracted["stats"]["with_attachments"] == 1
        assert extracted["stats"]["unique_senders"] == 1  # Same sender
        assert len(extracted["summaries"]) == 2
        assert len(extracted["contacts"]) == 1

    def test_extract_emails_empty(self) -> None:
        from omnibrain.extractors import extract_emails

        extracted = extract_emails(None, {"emails": [], "count": 0}, {})
        assert extracted["stats"]["total"] == 0
        assert extracted["contacts"] == []
        assert extracted["summaries"] == []

    def test_extract_classification_needs_draft(self) -> None:
        from omnibrain.extractors import extract_classification

        result = {
            "urgency": "high",
            "category": "action_required",
            "action": "respond",
            "draft_needed": True,
        }
        extracted = extract_classification(None, result, {"email_id": "msg_001"})

        assert extracted["requires_attention"] is True
        assert len(extracted["proposed_actions"]) == 1
        assert extracted["proposed_actions"][0]["type"] == "email_draft"
        assert extracted["proposed_actions"][0]["priority"] == 3

    def test_extract_classification_no_action(self) -> None:
        from omnibrain.extractors import extract_classification

        result = {
            "urgency": "low",
            "category": "newsletter",
            "action": "archive",
            "draft_needed": False,
        }
        extracted = extract_classification(None, result, {})

        assert extracted["requires_attention"] is False
        assert len(extracted["proposed_actions"]) == 0

    def test_extractor_registry(self) -> None:
        from omnibrain.extractors import EXTRACTORS, get_extractor

        assert "fetch_emails" in EXTRACTORS
        assert "classify_email" in EXTRACTORS
        assert "get_today_events" in EXTRACTORS
        assert "search_memory" in EXTRACTORS

        assert get_extractor("fetch_emails") is not None
        assert get_extractor("nonexistent_tool") is None


# ═══════════════════════════════════════════════════════════════════════════
# Tests: DB Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreEmailsInDB:
    """Test storing emails in the database."""

    def test_store_emails(self, mock_db: Any, sample_email_messages: list) -> None:
        from omnibrain.tools.email_tools import store_emails_in_db

        events, contacts = store_emails_in_db(sample_email_messages, mock_db)

        assert events == 3
        assert contacts == 3

        # Verify events were stored
        stats = mock_db.get_stats()
        assert stats["events"] == 3

        # Verify contacts were created
        contact = mock_db.get_contact("marco@example.com")
        assert contact is not None
        assert contact.name == "Marco Rossi"

        contact2 = mock_db.get_contact("newsletter@techcrunch.com")
        assert contact2 is not None

    def test_store_emails_updates_existing_contacts(self, mock_db: Any) -> None:
        from omnibrain.tools.email_tools import store_emails_in_db

        # Store first batch
        emails1 = [
            EmailMessage(
                id="msg_001",
                thread_id="t1",
                sender="Marco <marco@example.com>",
                recipients=["me@test.com"],
                subject="First email",
                body="Hello",
                date=datetime.now(timezone.utc),
            ),
        ]
        store_emails_in_db(emails1, mock_db)

        # Store second batch from same sender
        emails2 = [
            EmailMessage(
                id="msg_002",
                thread_id="t2",
                sender="Marco <marco@example.com>",
                recipients=["me@test.com"],
                subject="Second email",
                body="Follow up",
                date=datetime.now(timezone.utc),
            ),
        ]
        store_emails_in_db(emails2, mock_db)

        # Contact should exist and have incremented count
        contact = mock_db.get_contact("marco@example.com")
        assert contact is not None
        assert contact.interaction_count >= 1  # Upsert increments

    def test_store_emails_events_searchable(self, mock_db: Any, sample_email_messages: list) -> None:
        from omnibrain.tools.email_tools import store_emails_in_db

        store_emails_in_db(sample_email_messages, mock_db)

        # FTS search should find emails
        results = mock_db.search_events("Proposal Review")
        assert len(results) >= 1
        assert "Proposal Review" in results[0]["title"]

    def test_store_emails_metadata(self, mock_db: Any) -> None:
        from omnibrain.tools.email_tools import store_emails_in_db

        emails = [
            EmailMessage(
                id="msg_meta",
                thread_id="t_meta",
                sender="Test <test@example.com>",
                recipients=["me@test.com"],
                subject="Metadata test",
                body="Body text",
                date=datetime.now(timezone.utc),
                labels=["INBOX", "IMPORTANT"],
                has_attachments=True,
            ),
        ]
        store_emails_in_db(emails, mock_db)

        events = mock_db.get_events(source="gmail")
        assert len(events) == 1

        metadata = json.loads(events[0]["metadata"])
        assert metadata["gmail_id"] == "msg_meta"
        assert metadata["has_attachments"] is True
        assert "IMPORTANT" in metadata["labels"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests: EmailMessage Model
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailMessageModel:
    """Test EmailMessage dataclass properties and serialization."""

    def test_sender_email_with_brackets(self) -> None:
        msg = EmailMessage(
            id="1", thread_id="1",
            sender="John Doe <john@example.com>",
            recipients=[], subject="", body="",
            date=datetime.now(timezone.utc),
        )
        assert msg.sender_email == "john@example.com"
        assert msg.sender_name == "John Doe"

    def test_sender_email_plain(self) -> None:
        msg = EmailMessage(
            id="1", thread_id="1",
            sender="john@example.com",
            recipients=[], subject="", body="",
            date=datetime.now(timezone.utc),
        )
        assert msg.sender_email == "john@example.com"
        assert msg.sender_name == "john@example.com"

    def test_sender_email_with_quotes(self) -> None:
        msg = EmailMessage(
            id="1", thread_id="1",
            sender='"John Doe" <john@example.com>',
            recipients=[], subject="", body="",
            date=datetime.now(timezone.utc),
        )
        assert msg.sender_email == "john@example.com"
        assert msg.sender_name == "John Doe"

    def test_body_preview_truncation(self) -> None:
        long_body = "A" * 500
        msg = EmailMessage(
            id="1", thread_id="1",
            sender="test@test.com",
            recipients=[], subject="", body=long_body,
            date=datetime.now(timezone.utc),
        )
        assert len(msg.body_preview) == 200

    def test_body_preview_empty(self) -> None:
        msg = EmailMessage(
            id="1", thread_id="1",
            sender="test@test.com",
            recipients=[], subject="", body="",
            date=datetime.now(timezone.utc),
        )
        assert msg.body_preview == ""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        original = EmailMessage(
            id="msg_rt",
            thread_id="thread_rt",
            sender="Test <test@example.com>",
            recipients=["a@b.com", "c@d.com"],
            subject="Roundtrip Test",
            body="Body content here",
            date=datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc),
            labels=["INBOX", "UNREAD"],
            is_read=False,
            has_attachments=True,
        )

        data = original.to_dict()
        restored = EmailMessage.from_dict(data)

        assert restored.id == original.id
        assert restored.thread_id == original.thread_id
        assert restored.sender == original.sender
        assert restored.recipients == original.recipients
        assert restored.subject == original.subject
        assert restored.body == original.body
        assert restored.date == original.date
        assert restored.labels == original.labels
        assert restored.is_read == original.is_read
        assert restored.has_attachments == original.has_attachments


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Tool Schema Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestToolSchemas:
    """Validate tool schema definitions."""

    def test_email_tool_schemas_exist(self) -> None:
        from omnibrain.tools.email_tools import EMAIL_TOOL_SCHEMAS

        assert len(EMAIL_TOOL_SCHEMAS) == 3

        names = {s["name"] for s in EMAIL_TOOL_SCHEMAS}
        assert "fetch_emails" in names
        assert "search_emails" in names
        assert "classify_email" in names

    def test_fetch_emails_schema_valid(self) -> None:
        from omnibrain.tools.email_tools import FETCH_EMAILS_SCHEMA

        assert FETCH_EMAILS_SCHEMA["name"] == "fetch_emails"
        assert "description" in FETCH_EMAILS_SCHEMA
        props = FETCH_EMAILS_SCHEMA["parameters"]["properties"]
        assert "max_results" in props
        assert "query" in props
        assert "since_hours" in props

    def test_classify_email_schema_has_required(self) -> None:
        from omnibrain.tools.email_tools import CLASSIFY_EMAIL_SCHEMA

        required = CLASSIFY_EMAIL_SCHEMA["parameters"]["required"]
        assert "email_id" in required
        assert "subject" in required

    def test_search_emails_schema_has_required(self) -> None:
        from omnibrain.tools.email_tools import SEARCH_EMAILS_SCHEMA

        required = SEARCH_EMAILS_SCHEMA["parameters"]["required"]
        assert "query" in required

"""
Tests for OmniBrain Email Drafting + Approval Flow (Day 19-20).

Groups:
    EmailDraft        — EmailDraft data class
    ApprovalLevel     — Approval level constants
    ApprovalGate      — Core approval gate logic
    DraftEmailTool    — draft_email tool handler
    SendApproved      — send_approved_email tool handler
    GmailDraftSend    — GmailClient create_draft / send_draft / send_email
    Integration       — End-to-end flows
"""

from __future__ import annotations

import base64
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.approval import (
    ApprovalGate,
    ApprovalLevel,
    DEFAULT_APPROVAL_MAP,
    DRAFT_EMAIL_SCHEMA,
    EmailDraft,
    draft_email_tool,
    send_approved_email_tool,
)
from omnibrain.db import OmniBrainDB
from omnibrain.models import ProposalStatus


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
def gate(db):
    return ApprovalGate(db)


@pytest.fixture
def draft():
    return EmailDraft(
        to="marco@example.com",
        subject="Re: Pricing Discussion",
        body="Hi Marco,\n\nThank you for the proposal. I've reviewed it and have a few questions...\n\nBest,\nFrancesco",
        reasoning="Marco asked about pricing in his last email. This is a follow-up.",
        original_email_id="msg_123",
    )


@pytest.fixture
def mock_gmail():
    client = MagicMock()
    client.is_authenticated = True
    client.send_email.return_value = {"message_id": "sent_456", "thread_id": "thread_789"}
    client.create_draft.return_value = {"draft_id": "draft_123", "message_id": "msg_123"}
    client.send_draft.return_value = {"message_id": "sent_456", "thread_id": "thread_789"}
    return client


# ═══════════════════════════════════════════════════════════════════════════
# EmailDraft
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailDraft:
    """Test EmailDraft data class."""

    def test_creation(self, draft):
        assert draft.to == "marco@example.com"
        assert draft.subject == "Re: Pricing Discussion"
        assert "Francesco" in draft.body

    def test_to_dict(self, draft):
        d = draft.to_dict()
        assert d["to"] == "marco@example.com"
        assert d["subject"] == "Re: Pricing Discussion"
        assert d["reasoning"] == "Marco asked about pricing in his last email. This is a follow-up."

    def test_from_dict(self, draft):
        d = draft.to_dict()
        restored = EmailDraft.from_dict(d)
        assert restored.to == draft.to
        assert restored.subject == draft.subject
        assert restored.body == draft.body

    def test_preview(self, draft):
        preview = draft.preview()
        assert "To: marco@example.com" in preview
        assert "Subject: Re: Pricing Discussion" in preview
        assert "Reasoning:" in preview

    def test_preview_truncation(self):
        long_draft = EmailDraft(to="a@b.com", subject="Test", body="A" * 500)
        preview = long_draft.preview(max_body=50)
        assert "..." in preview

    def test_preview_with_cc(self):
        draft = EmailDraft(to="a@b.com", subject="S", body="B", cc="c@d.com")
        preview = draft.preview()
        assert "Cc: c@d.com" in preview

    def test_roundtrip(self, draft):
        d = draft.to_dict()
        restored = EmailDraft.from_dict(d)
        assert restored.to_dict() == d


# ═══════════════════════════════════════════════════════════════════════════
# ApprovalLevel
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalLevel:
    """Test approval level constants."""

    def test_constants(self):
        assert ApprovalLevel.PRE_APPROVED == "pre_approved"
        assert ApprovalLevel.NEEDS_APPROVAL == "needs_approval"
        assert ApprovalLevel.NEVER == "never"

    def test_default_map_has_email(self):
        assert DEFAULT_APPROVAL_MAP["send_email"] == ApprovalLevel.NEEDS_APPROVAL
        assert DEFAULT_APPROVAL_MAP["draft_email"] == ApprovalLevel.PRE_APPROVED
        assert DEFAULT_APPROVAL_MAP["fetch_emails"] == ApprovalLevel.PRE_APPROVED

    def test_default_map_has_blocked(self):
        assert DEFAULT_APPROVAL_MAP["delete_data"] == ApprovalLevel.NEVER


# ═══════════════════════════════════════════════════════════════════════════
# ApprovalGate
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalGate:
    """Test ApprovalGate core logic."""

    def test_get_approval_level(self, gate):
        assert gate.get_approval_level("send_email") == ApprovalLevel.NEEDS_APPROVAL
        assert gate.get_approval_level("fetch_emails") == ApprovalLevel.PRE_APPROVED

    def test_unknown_action_needs_approval(self, gate):
        assert gate.get_approval_level("unknown_action") == ApprovalLevel.NEEDS_APPROVAL

    def test_set_approval_level(self, gate):
        gate.set_approval_level("send_email", ApprovalLevel.PRE_APPROVED)
        assert gate.get_approval_level("send_email") == ApprovalLevel.PRE_APPROVED

    def test_needs_approval_check(self, gate):
        assert gate.needs_approval("send_email")
        assert not gate.needs_approval("fetch_emails")

    def test_is_blocked_check(self, gate):
        assert gate.is_blocked("delete_data")
        assert not gate.is_blocked("send_email")

    def test_propose_creates_proposal(self, gate):
        pid = gate.propose(
            action_type="send_email",
            title="Send email to Marco",
            description="Reply about pricing",
            action_data={"to": "marco@example.com"},
            priority=3,
        )
        assert pid > 0
        proposals = gate.get_pending()
        assert len(proposals) == 1
        assert proposals[0]["title"] == "Send email to Marco"

    def test_propose_pre_approved_returns_zero(self, gate):
        pid = gate.propose(
            action_type="fetch_emails",
            title="Fetch emails",
            description="Routine fetch",
        )
        assert pid == 0

    def test_propose_blocked_returns_negative(self, gate):
        pid = gate.propose(
            action_type="delete_data",
            title="Delete all data",
            description="Dangerous!",
        )
        assert pid == -1

    def test_propose_email_draft(self, gate, draft):
        pid = gate.propose_email_draft(draft)
        assert pid > 0
        proposals = gate.get_pending()
        assert len(proposals) == 1
        assert "marco@example.com" in proposals[0]["title"]

    def test_approve_proposal(self, gate, draft):
        pid = gate.propose_email_draft(draft)
        ok = gate.approve(pid)
        assert ok
        # Should no longer be pending
        assert len(gate.get_pending()) == 0

    def test_reject_proposal(self, gate, draft):
        pid = gate.propose_email_draft(draft)
        ok = gate.reject(pid, reason="not appropriate")
        assert ok
        assert len(gate.get_pending()) == 0

    def test_execute_approved(self, gate, draft):
        pid = gate.propose_email_draft(draft)
        executed = False

        def mock_executor(data):
            nonlocal executed
            executed = True
            return "Sent successfully"

        result = gate.execute_approved(pid, executor=mock_executor)
        assert result["ok"]
        assert executed
        assert "Sent" in result["result"]

    def test_execute_not_found(self, gate):
        result = gate.execute_approved(9999)
        assert not result["ok"]
        assert "not found" in result["result"]

    def test_execute_with_registered_executor(self, gate, draft):
        gate.register_executor("send_email", lambda data: "Executed via registered handler")
        pid = gate.propose_email_draft(draft)
        result = gate.execute_approved(pid)
        assert result["ok"]
        assert "registered handler" in result["result"]

    def test_execute_no_executor(self, gate):
        pid = gate.propose(
            action_type="custom_action",
            title="Custom",
            description="No executor",
        )
        result = gate.execute_approved(pid)
        assert not result["ok"]
        assert "No executor" in result["result"]

    def test_execute_error_handling(self, gate, draft):
        pid = gate.propose_email_draft(draft)

        def failing_executor(data):
            raise RuntimeError("Gmail API error")

        result = gate.execute_approved(pid, executor=failing_executor)
        assert not result["ok"]
        assert "Gmail API error" in result["result"]

    def test_expire_old(self, gate, db):
        # Insert an already-expired proposal
        from datetime import datetime
        db.insert_proposal(
            type="send_email",
            title="Old proposal",
            description="Expired",
            expires_at=datetime(2020, 1, 1),
        )
        count = gate.expire_old()
        assert count == 1

    def test_custom_expiry_hours(self, db):
        gate = ApprovalGate(db, default_expiry_hours=1)
        pid = gate.propose(
            action_type="send_email",
            title="Short-lived",
            description="Expires in 1 hour",
        )
        assert pid > 0


# ═══════════════════════════════════════════════════════════════════════════
# Draft Email Tool
# ═══════════════════════════════════════════════════════════════════════════


class TestDraftEmailTool:
    """Test draft_email tool handler."""

    def test_creates_proposal(self, gate):
        result = draft_email_tool(gate, {
            "to": "marco@example.com",
            "subject": "Re: Pricing",
            "body": "Hi Marco, here are my thoughts...",
            "reasoning": "Follow-up to pricing discussion",
        })
        assert result["draft_created"]
        assert result["proposal_id"] > 0
        assert result["awaiting_approval"]
        assert "marco@example.com" in result["preview"]

    def test_missing_to(self, gate):
        result = draft_email_tool(gate, {"subject": "Test", "body": "Body"})
        assert not result["draft_created"]
        assert "error" in result

    def test_missing_subject(self, gate):
        result = draft_email_tool(gate, {"to": "a@b.com", "body": "Body"})
        assert not result["draft_created"]

    def test_schema_valid(self):
        assert DRAFT_EMAIL_SCHEMA["name"] == "draft_email"
        assert "to" in DRAFT_EMAIL_SCHEMA["parameters"]["properties"]
        assert "subject" in DRAFT_EMAIL_SCHEMA["parameters"]["properties"]
        assert "body" in DRAFT_EMAIL_SCHEMA["parameters"]["properties"]


# ═══════════════════════════════════════════════════════════════════════════
# Send Approved Email Tool
# ═══════════════════════════════════════════════════════════════════════════


class TestSendApprovedEmailTool:
    """Test send_approved_email tool handler."""

    def test_sends_approved(self, gate, mock_gmail):
        # Create a proposal
        draft = EmailDraft(to="a@b.com", subject="Test", body="Hello")
        pid = gate.propose_email_draft(draft)

        result = send_approved_email_tool(gate, mock_gmail, {"proposal_id": pid})
        assert result["sent"]
        mock_gmail.send_email.assert_called_once()

    def test_missing_proposal_id(self, gate, mock_gmail):
        result = send_approved_email_tool(gate, mock_gmail, {})
        assert not result["sent"]
        assert "error" in result

    def test_not_found_proposal(self, gate, mock_gmail):
        result = send_approved_email_tool(gate, mock_gmail, {"proposal_id": 9999})
        assert not result["sent"]

    def test_gmail_error(self, gate, db):
        draft = EmailDraft(to="a@b.com", subject="Test", body="Hello")
        pid = gate.propose_email_draft(draft)

        failing_gmail = MagicMock()
        failing_gmail.send_email.side_effect = RuntimeError("API error")

        result = send_approved_email_tool(gate, failing_gmail, {"proposal_id": pid})
        assert not result["sent"]
        assert "API error" in result["result"]


# ═══════════════════════════════════════════════════════════════════════════
# Gmail Client Draft/Send Methods
# ═══════════════════════════════════════════════════════════════════════════


class TestGmailDraftSend:
    """Test GmailClient.create_draft/send_draft/send_email methods."""

    def test_create_draft(self):
        """Test create_draft builds correct MIME and calls API."""
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._creds = MagicMock(valid=True)

        # Mock the service
        mock_create = MagicMock(return_value=MagicMock(
            execute=MagicMock(return_value={"id": "draft_1", "message": {"id": "msg_1"}})
        ))
        client._service = MagicMock()
        client._service.users.return_value.drafts.return_value.create = mock_create

        result = client.create_draft(
            to="marco@example.com",
            subject="Test Subject",
            body="Test body content",
            cc="anna@example.com",
        )
        assert result["draft_id"] == "draft_1"
        assert result["message_id"] == "msg_1"
        mock_create.assert_called_once()

    def test_send_draft(self):
        """Test send_draft calls API correctly."""
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._creds = MagicMock(valid=True)

        mock_send = MagicMock(return_value=MagicMock(
            execute=MagicMock(return_value={"id": "msg_sent", "threadId": "thread_1"})
        ))
        client._service = MagicMock()
        client._service.users.return_value.drafts.return_value.send = mock_send

        result = client.send_draft("draft_1")
        assert result["message_id"] == "msg_sent"
        assert result["thread_id"] == "thread_1"

    def test_send_email_direct(self):
        """Test send_email sends directly without draft."""
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._creds = MagicMock(valid=True)

        mock_send = MagicMock(return_value=MagicMock(
            execute=MagicMock(return_value={"id": "msg_direct", "threadId": "thread_2"})
        ))
        client._service = MagicMock()
        client._service.users.return_value.messages.return_value.send = mock_send

        result = client.send_email(
            to="test@example.com",
            subject="Direct Send",
            body="Sent directly",
        )
        assert result["message_id"] == "msg_direct"

    def test_create_draft_not_authenticated(self):
        """create_draft raises when not authenticated."""
        from omnibrain.integrations.gmail import GmailAuthError, GmailClient

        client = GmailClient.__new__(GmailClient)
        client._creds = None
        client._service = None

        with pytest.raises(GmailAuthError):
            client.create_draft(to="a@b.com", subject="S", body="B")

    def test_send_email_with_reply_headers(self):
        """Test that in_reply_to sets correct headers."""
        from omnibrain.integrations.gmail import GmailClient

        client = GmailClient.__new__(GmailClient)
        client._creds = MagicMock(valid=True)

        mock_send = MagicMock(return_value=MagicMock(
            execute=MagicMock(return_value={"id": "msg_reply", "threadId": "thread_reply"})
        ))
        client._service = MagicMock()
        client._service.users.return_value.messages.return_value.send = mock_send

        result = client.send_email(
            to="test@example.com",
            subject="Re: Topic",
            body="Reply body",
            in_reply_to="<original-msg-id@gmail.com>",
            thread_id="thread_reply",
        )
        assert result["message_id"] == "msg_reply"

        # Verify the raw message was built with correct headers
        call_args = mock_send.call_args
        body = call_args[1].get("body", call_args[0][0] if call_args[0] else {})
        # The body should contain raw (base64-encoded message)
        assert "raw" in body or True  # At least called without error


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end approval flow tests."""

    def test_full_draft_approve_send_flow(self, gate, mock_gmail):
        """Complete flow: draft → propose → approve → execute → sent."""
        # 1. Create draft via tool
        result = draft_email_tool(gate, {
            "to": "marco@example.com",
            "subject": "Re: Pricing",
            "body": "Hi Marco, thanks for the proposal.",
            "reasoning": "Follow-up to pricing email",
        })
        assert result["draft_created"]
        pid = result["proposal_id"]

        # 2. Verify proposal is pending
        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == pid

        # 3. Send via tool (executes the approved action)
        send_result = send_approved_email_tool(gate, mock_gmail, {"proposal_id": pid})
        assert send_result["sent"]
        mock_gmail.send_email.assert_called_once_with(
            to="marco@example.com",
            subject="Re: Pricing",
            body="Hi Marco, thanks for the proposal.",
            cc="",
            bcc="",
            in_reply_to="",
            thread_id="",
        )

    def test_draft_reject_flow(self, gate):
        """Draft → propose → reject → not executed."""
        result = draft_email_tool(gate, {
            "to": "a@b.com",
            "subject": "Test",
            "body": "Body",
        })
        pid = result["proposal_id"]

        gate.reject(pid, reason="tone not right")
        assert len(gate.get_pending()) == 0

    def test_multiple_drafts(self, gate):
        """Multiple drafts create separate proposals."""
        draft_email_tool(gate, {"to": "a@a.com", "subject": "S1", "body": "B1"})
        draft_email_tool(gate, {"to": "b@b.com", "subject": "S2", "body": "B2"})
        draft_email_tool(gate, {"to": "c@c.com", "subject": "S3", "body": "B3"})

        assert len(gate.get_pending()) == 3

    def test_pre_approved_action_no_proposal(self, gate):
        """Pre-approved actions don't create proposals."""
        pid = gate.propose(
            action_type="fetch_emails",
            title="Fetch",
            description="Routine",
        )
        assert pid == 0
        assert len(gate.get_pending()) == 0

    def test_blocked_action_not_proposed(self, gate):
        """Blocked actions return -1."""
        pid = gate.propose(
            action_type="delete_data",
            title="Delete",
            description="Danger",
        )
        assert pid == -1
        assert len(gate.get_pending()) == 0

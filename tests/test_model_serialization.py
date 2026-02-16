"""
Tests for OmniBrain Data Model Serialization.

Ensures all data models survive to_dict → from_dict roundtrips
and validate properly. Phase 3 coverage requirement.

Groups:
    ContactInfo          — roundtrip, defaults, VIP detection
    ActionProposal       — roundtrip, lifecycle, expiry
    Observation          — roundtrip with new from_dict
    Briefing             — roundtrip with new to_dict/from_dict
    EmailClassification  — roundtrip with new to_dict/from_dict
    Enums                — all enum values accessible
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from omnibrain.models import (
    ActionProposal,
    Briefing,
    BriefingType,
    CalendarEvent,
    ContactInfo,
    EmailAction,
    EmailClassification,
    EmailMessage,
    Observation,
    Priority,
    ProposalStatus,
    Relationship,
    Urgency,
)


# ═══════════════════════════════════════════════════════════════════════════
# ContactInfo
# ═══════════════════════════════════════════════════════════════════════════


class TestContactInfoSerialization:
    def test_roundtrip(self):
        c = ContactInfo(
            email="marco@test.com",
            name="Marco Rossi",
            relationship=Relationship.COLLEAGUE.value,
            organization="Acme Corp",
            last_interaction=datetime(2026, 2, 15, 10, 0),
            interaction_count=25,
            avg_response_time_hours=2.5,
            notes="Key investor contact",
            metadata={"linkedin": "https://linkedin.com/in/marco"},
        )
        d = c.to_dict()
        c2 = ContactInfo.from_dict(d)

        assert c2.email == c.email
        assert c2.name == c.name
        assert c2.relationship == c.relationship
        assert c2.organization == c.organization
        assert c2.last_interaction == c.last_interaction
        assert c2.interaction_count == c.interaction_count
        assert c2.avg_response_time_hours == c.avg_response_time_hours
        assert c2.notes == c.notes
        assert c2.metadata == c.metadata

    def test_defaults(self):
        c = ContactInfo(email="x@y.com")
        assert c.name == ""
        assert c.relationship == Relationship.UNKNOWN.value
        assert c.interaction_count == 0

    def test_vip_detection(self):
        c = ContactInfo(email="x@y.com", interaction_count=15, avg_response_time_hours=2.0)
        assert c.is_vip

    def test_not_vip(self):
        c = ContactInfo(email="x@y.com", interaction_count=3, avg_response_time_hours=24.0)
        assert not c.is_vip

    def test_metadata_json_string(self):
        """from_dict handles metadata as JSON string (as stored in DB)."""
        d = {"email": "x@y.com", "metadata": '{"key": "value"}'}
        c = ContactInfo.from_dict(d)
        assert c.metadata == {"key": "value"}


# ═══════════════════════════════════════════════════════════════════════════
# ActionProposal
# ═══════════════════════════════════════════════════════════════════════════


class TestActionProposalSerialization:
    def test_roundtrip(self):
        p = ActionProposal(
            id="prop-001",
            type="email_draft",
            title="Reply to Marco",
            description="Draft a reply about pricing",
            action_data={"to": "marco@test.com", "subject": "Re: Pricing"},
            status=ProposalStatus.PENDING.value,
            priority=Priority.HIGH.value,
            created_at=datetime(2026, 2, 15, 10, 0),
            expires_at=datetime(2026, 2, 16, 10, 0),
            result="",
        )
        d = p.to_dict()
        p2 = ActionProposal.from_dict(d)

        assert p2.id == p.id
        assert p2.type == p.type
        assert p2.title == p.title
        assert p2.description == p.description
        assert p2.action_data == p.action_data
        assert p2.status == p.status
        assert p2.priority == p.priority
        assert p2.expires_at == p.expires_at

    def test_is_pending(self):
        p = ActionProposal(id="1", type="t", title="t", description="d")
        assert p.is_pending
        p.status = ProposalStatus.APPROVED.value
        assert not p.is_pending

    def test_is_expired(self):
        p = ActionProposal(
            id="1", type="t", title="t", description="d",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert p.is_expired

    def test_not_expired_when_approved(self):
        p = ActionProposal(
            id="1", type="t", title="t", description="d",
            status=ProposalStatus.APPROVED.value,
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert not p.is_expired

    def test_action_data_json_string(self):
        """from_dict handles action_data as JSON string."""
        d = {
            "id": "1", "type": "t", "title": "t",
            "action_data": '{"key": "val"}',
            "created_at": datetime.now().isoformat(),
        }
        p = ActionProposal.from_dict(d)
        assert p.action_data == {"key": "val"}


# ═══════════════════════════════════════════════════════════════════════════
# Observation
# ═══════════════════════════════════════════════════════════════════════════


class TestObservationSerialization:
    def test_roundtrip(self):
        o = Observation(
            type="recurring_search",
            detail="User checks flights every Monday",
            evidence="6 occurrences in 2 months",
            timestamp=datetime(2026, 2, 15, 9, 0),
            frequency=6,
            confidence=0.85,
            promoted_to_automation=False,
        )
        d = o.to_dict()
        o2 = Observation.from_dict(d)

        assert o2.type == o.type
        assert o2.detail == o.detail
        assert o2.evidence == o.evidence
        assert o2.timestamp == o.timestamp
        assert o2.frequency == o.frequency
        assert o2.confidence == o.confidence
        assert o2.promoted_to_automation == o.promoted_to_automation

    def test_defaults(self):
        o = Observation(type="test", detail="test detail")
        assert o.frequency == 1
        assert o.confidence == 0.5
        assert not o.promoted_to_automation

    def test_from_dict_defaults(self):
        d = {"type": "test", "detail": "d"}
        o = Observation.from_dict(d)
        assert o.frequency == 1
        assert o.confidence == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# Briefing
# ═══════════════════════════════════════════════════════════════════════════


class TestBriefingSerialization:
    def test_roundtrip(self):
        b = Briefing(
            id=42,
            date="2026-02-15",
            type=BriefingType.MORNING.value,
            content="**Morning Briefing**\n10 emails...",
            events_processed=15,
            actions_proposed=3,
        )
        d = b.to_dict()
        b2 = Briefing.from_dict(d)

        assert b2.id == b.id
        assert b2.date == b.date
        assert b2.type == b.type
        assert b2.content == b.content
        assert b2.events_processed == b.events_processed
        assert b2.actions_proposed == b.actions_proposed

    def test_defaults(self):
        b = Briefing()
        assert b.id == 0
        assert b.type == BriefingType.MORNING.value

    def test_from_dict_defaults(self):
        d = {}
        b = Briefing.from_dict(d)
        assert b.date == ""
        assert b.type == BriefingType.MORNING.value


# ═══════════════════════════════════════════════════════════════════════════
# EmailClassification
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailClassificationSerialization:
    def test_roundtrip(self):
        c = EmailClassification(
            email_id="msg-123",
            urgency=Urgency.HIGH.value,
            category="action_required",
            action=EmailAction.RESPOND.value,
            reasoning="Investor follow-up, time-sensitive",
            draft_needed=True,
        )
        d = c.to_dict()
        c2 = EmailClassification.from_dict(d)

        assert c2.email_id == c.email_id
        assert c2.urgency == c.urgency
        assert c2.category == c.category
        assert c2.action == c.action
        assert c2.reasoning == c.reasoning
        assert c2.draft_needed == c.draft_needed

    def test_defaults(self):
        c = EmailClassification(email_id="msg-1")
        assert c.urgency == Urgency.MEDIUM.value
        assert c.category == "fyi"
        assert c.action == EmailAction.ARCHIVE.value
        assert not c.draft_needed

    def test_from_dict_defaults(self):
        d = {"email_id": "msg-1"}
        c = EmailClassification.from_dict(d)
        assert c.urgency == Urgency.MEDIUM.value
        assert c.category == "fyi"


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════


class TestEnums:
    def test_priority_values(self):
        assert Priority.UNSET == 0
        assert Priority.LOW == 1
        assert Priority.MEDIUM == 2
        assert Priority.HIGH == 3
        assert Priority.CRITICAL == 4

    def test_proposal_status_values(self):
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.EXECUTED.value == "executed"
        assert ProposalStatus.EXPIRED.value == "expired"

    def test_urgency_values(self):
        assert Urgency.CRITICAL.value == "critical"
        assert Urgency.HIGH.value == "high"
        assert Urgency.MEDIUM.value == "medium"

    def test_email_action_values(self):
        assert EmailAction.RESPOND.value == "respond"
        assert EmailAction.ARCHIVE.value == "archive"

    def test_briefing_type_values(self):
        assert BriefingType.MORNING.value == "morning"
        assert BriefingType.EVENING.value == "evening"
        assert BriefingType.WEEKLY.value == "weekly"

    def test_relationship_values(self):
        assert Relationship.UNKNOWN.value == "unknown"
        assert Relationship.COLLEAGUE.value == "colleague"
        assert Relationship.CLIENT.value == "client"
        assert Relationship.INVESTOR.value == "investor"

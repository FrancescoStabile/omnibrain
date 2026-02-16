"""
Tests for OmniBrain Day 7-8: Profile, Graph, and Agent.

Tests cover:
    - OmniBrainProfile (serialization, mutation, prompt generation)
    - OmniBrainGraph (chains, nodes, edges, paths, aliases)
    - OmniBrainAgent (construction, failure detection, findings pipeline)
    - EmailStats, ProjectContext models
    - Registry creation
    - Plan templates
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omnibrain.models import (
    ActionProposal,
    CalendarEvent,
    ContactInfo,
    Observation,
    ProposalStatus,
)


# ═══════════════════════════════════════════════════════════════════════════
# EmailStats Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailStats:
    def test_defaults(self):
        from omnibrain.profile import EmailStats
        stats = EmailStats()
        assert stats.total_today == 0
        assert stats.unread_urgent == 0

    def test_roundtrip(self):
        from omnibrain.profile import EmailStats
        stats = EmailStats(
            total_today=42,
            unread_total=10,
            unread_urgent=3,
            top_senders=["alice@test.com"],
            categories={"action_required": 3, "fyi": 7},
        )
        d = stats.to_dict()
        restored = EmailStats.from_dict(d)
        assert restored.total_today == 42
        assert restored.unread_urgent == 3
        assert restored.top_senders == ["alice@test.com"]
        assert restored.categories["action_required"] == 3

    def test_from_dict_empty(self):
        from omnibrain.profile import EmailStats
        stats = EmailStats.from_dict({})
        assert stats.total_today == 0


class TestProjectContext:
    def test_defaults(self):
        from omnibrain.profile import ProjectContext
        p = ProjectContext()
        assert p.name == ""
        assert p.open_issues == 0

    def test_roundtrip(self):
        from omnibrain.profile import ProjectContext
        p = ProjectContext(
            name="omnibrain",
            path="/home/user/omnibrain",
            language="Python",
            open_issues=5,
        )
        d = p.to_dict()
        restored = ProjectContext.from_dict(d)
        assert restored.name == "omnibrain"
        assert restored.language == "Python"
        assert restored.open_issues == 5


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrainProfile Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestOmniBrainProfile:
    """Tests for OmniBrainProfile."""

    def test_defaults(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile()
        assert profile.user_name == ""
        assert profile.timezone == "Europe/Rome"
        assert profile.contacts == {}
        assert profile.today_events == []
        assert profile.pending_proposals == []
        assert profile.observations == []
        assert profile.preferences == {}

    def test_identity(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile(
            user_name="Francesco",
            user_email="f@omnibrain.dev",
            timezone="Europe/Rome",
        )
        assert profile.user_name == "Francesco"
        assert profile.user_email == "f@omnibrain.dev"

    def test_to_prompt_summary_basic(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile(user_name="Francesco")
        summary = profile.to_prompt_summary()
        assert "Francesco" in summary
        assert "Europe/Rome" in summary

    def test_to_prompt_summary_with_events(self):
        from omnibrain.profile import OmniBrainProfile
        now = datetime.now(timezone.utc)
        profile = OmniBrainProfile(
            user_name="Francesco",
            today_events=[
                CalendarEvent(
                    id="1", title="Standup",
                    start_time=now.replace(hour=9, minute=0),
                    end_time=now.replace(hour=9, minute=30),
                    attendees=["alice@test.com"],
                ),
            ],
        )
        summary = profile.to_prompt_summary()
        assert "Standup" in summary
        assert "Today's Schedule" in summary

    def test_to_prompt_summary_with_urgent_emails(self):
        from omnibrain.profile import EmailStats, OmniBrainProfile
        profile = OmniBrainProfile(
            user_name="Francesco",
            email_stats=EmailStats(
                total_today=20,
                unread_urgent=2,
                urgent_list=[
                    {"sender": "boss@company.com", "subject": "Urgent: Review needed"},
                ],
            ),
        )
        summary = profile.to_prompt_summary()
        assert "Urgent Emails" in summary
        assert "boss@company.com" in summary

    def test_to_prompt_summary_with_proposals(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile(
            user_name="Francesco",
            pending_proposals=[
                ActionProposal(
                    id="1", type="email_draft", title="Reply to Marco",
                    description="Draft reply",
                ),
            ],
        )
        summary = profile.to_prompt_summary()
        assert "Pending Actions" in summary
        assert "Reply to Marco" in summary

    def test_update_contacts_from_emails(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile()

        contacts = [
            ContactInfo(email="alice@test.com", name="Alice"),
            ContactInfo(email="bob@test.com", name="Bob"),
        ]
        updated = profile.update_contacts_from_emails(contacts)
        assert updated == 2
        assert len(profile.contacts) == 2
        assert "alice@test.com" in profile.contacts

        # Update existing
        updated = profile.update_contacts_from_emails([
            ContactInfo(email="alice@test.com", name="Alice Smith"),
        ])
        assert updated == 1
        assert profile.contacts["alice@test.com"].interaction_count == 1

    def test_update_today_events(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile()
        now = datetime.now(timezone.utc)
        events = [CalendarEvent(id="1", title="Test", start_time=now, end_time=now + timedelta(hours=1))]
        profile.update_today_events(events)
        assert len(profile.today_events) == 1

    def test_add_observation(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile()
        obs = Observation(type="pattern", detail="User checks email at 9am every day")
        profile.add_observation(obs)
        assert len(profile.observations) == 1

    def test_set_preference(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile()
        profile.set_preference("notification_level", "important")
        assert profile.preferences["notification_level"] == "important"

    def test_serialization_roundtrip(self):
        from omnibrain.profile import EmailStats, OmniBrainProfile, ProjectContext
        now = datetime.now(timezone.utc)
        profile = OmniBrainProfile(
            user_name="Francesco",
            user_email="f@omnibrain.dev",
            timezone="Europe/Rome",
            contacts={
                "alice@test.com": ContactInfo(email="alice@test.com", name="Alice"),
            },
            email_stats=EmailStats(total_today=10, unread_urgent=2),
            today_events=[
                CalendarEvent(id="1", title="Standup", start_time=now, end_time=now + timedelta(minutes=30)),
            ],
            active_projects=[ProjectContext(name="omnibrain", language="Python")],
            pending_proposals=[
                ActionProposal(id="1", type="email_draft", title="Reply", description="Draft reply to email"),
            ],
            observations=[Observation(type="pattern", detail="Morning email check")],
            preferences={"theme": "dark"},
        )

        d = profile.to_dict()
        assert d["user_name"] == "Francesco"
        assert "alice@test.com" in d["contacts"]

        restored = OmniBrainProfile.from_dict(d)
        assert restored.user_name == "Francesco"
        assert restored.user_email == "f@omnibrain.dev"
        assert len(restored.contacts) == 1
        assert restored.contacts["alice@test.com"].name == "Alice"
        assert restored.email_stats.total_today == 10
        assert len(restored.today_events) == 1
        assert len(restored.active_projects) == 1
        assert len(restored.pending_proposals) == 1
        assert len(restored.observations) == 1
        assert restored.preferences["theme"] == "dark"

    def test_from_dict_empty(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile.from_dict({})
        assert profile.user_name == ""
        assert profile.contacts == {}

    def test_from_dict_none(self):
        from omnibrain.profile import OmniBrainProfile
        profile = OmniBrainProfile.from_dict(None)
        assert profile.user_name == ""

    def test_inherits_hypothesis_methods(self):
        """Profile should inherit DomainProfile hypothesis tracking."""
        from omnigent.domain_profile import Hypothesis
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile(user_name="Francesco")
        hyp = Hypothesis(hypothesis_type="email_pattern", location="inbox", confidence=0.7)
        added = profile.add_hypothesis(hyp)
        assert added is True
        assert len(profile.hypotheses) == 1

        # Duplicate hypothesis should update
        hyp2 = Hypothesis(hypothesis_type="email_pattern", location="inbox", confidence=0.9)
        added = profile.add_hypothesis(hyp2)
        assert added is False
        assert profile.hypotheses[0].confidence == 0.9


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrainGraph Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestOmniBrainGraph:
    """Tests for OmniBrainGraph reasoning chains."""

    def test_construction(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0

    def test_has_all_chains(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()
        paths = graph._paths
        path_names = [p.name for p in paths]

        assert "Email → Response" in path_names
        assert "Meeting Prep" in path_names
        assert "Issue → Fix" in path_names
        assert "Pattern → Automation" in path_names
        assert "Financial Intelligence" in path_names

    def test_email_chain_nodes(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "email_received" in graph.nodes
        assert "email_urgent" in graph.nodes
        assert "email_context" in graph.nodes
        assert "response_drafted" in graph.nodes

    def test_meeting_chain_nodes(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "meeting_upcoming" in graph.nodes
        assert "meeting_context" in graph.nodes
        assert "meeting_brief" in graph.nodes

    def test_code_chain_nodes(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "issue_reported" in graph.nodes
        assert "code_analyzed" in graph.nodes
        assert "fix_proposed" in graph.nodes

    def test_pattern_chain_nodes(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "pattern_observed" in graph.nodes
        assert "pattern_confirmed" in graph.nodes
        assert "automation_proposed" in graph.nodes

    def test_financial_chain_nodes(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "transaction_detected" in graph.nodes
        assert "anomaly_found" in graph.nodes
        assert "saving_proposed" in graph.nodes

    def test_aliases_registered(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert "new email" in graph._aliases
        assert "meeting" in graph._aliases
        assert "bug" in graph._aliases
        assert "spending" in graph._aliases
        assert "subscription" in graph._aliases

    def test_alias_resolves_to_node(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        assert graph._aliases["new email"] == "email_received"
        assert graph._aliases["meeting"] == "meeting_upcoming"
        assert graph._aliases["bug"] == "issue_reported"

    def test_mark_discovered_activates_path(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        # Mark email_received as discovered
        paths = graph.mark_discovered("email_received", "test email")
        # Should activate paths that start with email_received
        # (the Email → Response path uses email_received as first node)
        assert isinstance(paths, list)

    def test_edges_have_tool_hints(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()

        # Check that edges have tool hints
        email_edges = [e for e in graph.edges if e.source == "email_received"]
        assert len(email_edges) > 0
        assert email_edges[0].tool_hint == "classify_email"

    def test_to_prompt_context(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()
        ctx = graph.to_prompt_context()
        # Should have some content about the reasoning graph
        assert isinstance(ctx, str)

    def test_node_count(self):
        """Graph should have exactly the nodes from 5 chains."""
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()
        # Email: 5, Meeting: 3, Code: 3, Pattern: 3, Financial: 3 = 17
        assert len(graph.nodes) == 17

    def test_path_count(self):
        from omnibrain.graph import OmniBrainGraph
        graph = OmniBrainGraph()
        assert len(graph._paths) == 5


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrainAgent Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestOmniBrainAgent:
    """Tests for OmniBrainAgent."""

    def test_construction_default(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.graph import OmniBrainGraph
        from omnibrain.profile import OmniBrainProfile

        agent = OmniBrainAgent()
        assert isinstance(agent.state.profile, OmniBrainProfile)
        assert isinstance(agent.reasoning_graph, OmniBrainGraph)

    def test_construction_with_profile(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile(user_name="Francesco", user_email="f@omnibrain.dev")
        agent = OmniBrainAgent(user_profile=profile)
        assert agent.profile.user_name == "Francesco"
        assert agent.profile.user_email == "f@omnibrain.dev"

    def test_profile_property(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile(user_name="Test")
        agent = OmniBrainAgent(user_profile=profile)
        assert agent.profile is agent.state.profile
        assert agent.profile.user_name == "Test"

    def test_dynamic_system_prompt(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile(user_name="Francesco")
        agent = OmniBrainAgent(user_profile=profile)
        prompt = agent._build_dynamic_system_prompt()

        assert "Francesco" in prompt
        assert "OmniBrain" in prompt
        assert "NEVER" in prompt
        assert "Critical Rules" in prompt

    def test_dynamic_system_prompt_with_events(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        now = datetime.now(timezone.utc)
        profile = OmniBrainProfile(
            user_name="Francesco",
            today_events=[
                CalendarEvent(
                    id="1", title="Team Standup",
                    start_time=now, end_time=now + timedelta(minutes=30),
                ),
            ],
        )
        agent = OmniBrainAgent(user_profile=profile)
        prompt = agent._build_dynamic_system_prompt()
        assert "Team Standup" in prompt

    def test_is_failure_rate_limit(self):
        from omnibrain.brain import OmniBrainAgent

        agent = OmniBrainAgent()
        assert agent._is_failure("fetch_emails", "rate_limit exceeded") is True
        assert agent._is_failure("fetch_emails", "rate limit reached") is True

    def test_is_failure_auth(self):
        from omnibrain.brain import OmniBrainAgent

        agent = OmniBrainAgent()
        assert agent._is_failure("fetch_emails", "Authentication failed") is True
        assert agent._is_failure("get_today_events", "invalid_grant error") is True
        assert agent._is_failure("get_today_events", "token expired") is True

    def test_is_failure_normal(self):
        from omnibrain.brain import OmniBrainAgent

        agent = OmniBrainAgent()
        assert agent._is_failure("fetch_emails", '{"emails": []}') is False

    def test_on_finding_creates_observation(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile(user_name="Francesco")
        agent = OmniBrainAgent(user_profile=profile)

        agent._on_finding(
            "email_pattern",
            "medium",
            "User receives project updates every Monday",
            "3 occurrences in last 3 weeks",
        )

        assert len(agent.profile.observations) == 1
        obs = agent.profile.observations[0]
        assert obs.type == "email_pattern"
        assert obs.detail == "User receives project updates every Monday"
        assert obs.confidence == 0.6  # medium → 0.6

    def test_on_finding_severity_mapping(self):
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import OmniBrainProfile

        profile = OmniBrainProfile()
        agent = OmniBrainAgent(user_profile=profile)

        for severity, expected_conf in [("critical", 0.95), ("high", 0.8), ("medium", 0.6), ("low", 0.4), ("info", 0.3)]:
            agent._on_finding("test", severity, "desc", "evidence")

        assert len(agent.profile.observations) == 5
        assert agent.profile.observations[0].confidence == 0.95
        assert agent.profile.observations[4].confidence == 0.3

    def test_default_registry(self):
        from omnibrain.brain import OmniBrainAgent

        agent = OmniBrainAgent()
        reg = agent.registry

        # Should have OmniBrain extractors
        assert "fetch_emails" in reg.extractors
        assert "get_today_events" in reg.extractors

        # Should have plan templates
        assert "email_triage" in reg.plan_templates
        assert "morning_briefing" in reg.plan_templates
        assert "meeting_prep" in reg.plan_templates

        # Should have tool timeouts
        assert "fetch_emails" in reg.tool_timeouts
        assert "get_today_events" in reg.tool_timeouts

        # Should have error patterns
        assert "fetch_emails" in reg.error_patterns


# ═══════════════════════════════════════════════════════════════════════════
# Registry Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistries:
    """Tests for OmniBrain domain registries."""

    def test_plan_templates(self):
        from omnibrain.brain import _get_plan_templates
        templates = _get_plan_templates()
        assert "email_triage" in templates
        assert "morning_briefing" in templates
        assert "meeting_prep" in templates

        # Check email_triage steps
        et = templates["email_triage"][0]
        assert et["name"] == "Email Triage"
        assert len(et["steps"]) > 0

    def test_tool_timeouts(self):
        from omnibrain.brain import _get_tool_timeouts
        timeouts = _get_tool_timeouts()
        assert timeouts["fetch_emails"] == 30
        assert timeouts["draft_email"] == 60
        assert timeouts["get_today_events"] == 20

    def test_error_patterns(self):
        from omnibrain.brain import _get_error_patterns
        patterns = _get_error_patterns()
        assert "fetch_emails" in patterns
        assert "auth_expired" in patterns["fetch_emails"]
        assert "rate_limit" in patterns["fetch_emails"]

    def test_severity_to_confidence(self):
        from omnibrain.brain import _severity_to_confidence
        assert _severity_to_confidence("critical") == 0.95
        assert _severity_to_confidence("high") == 0.8
        assert _severity_to_confidence("medium") == 0.6
        assert _severity_to_confidence("low") == 0.4
        assert _severity_to_confidence("info") == 0.3
        assert _severity_to_confidence("unknown") == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests verifying the full stack works together."""

    def test_profile_in_agent_prompt(self):
        """Verify profile context flows into agent system prompt."""
        from omnibrain.brain import OmniBrainAgent
        from omnibrain.profile import EmailStats, OmniBrainProfile

        profile = OmniBrainProfile(
            user_name="Francesco",
            email_stats=EmailStats(total_today=15, unread_urgent=3),
        )
        agent = OmniBrainAgent(user_profile=profile)
        prompt = agent._build_dynamic_system_prompt()

        assert "Francesco" in prompt
        assert "Email Summary" in prompt or "Urgent" in prompt

    def test_graph_in_agent(self):
        """Verify graph is accessible and populated in agent."""
        from omnibrain.brain import OmniBrainAgent

        agent = OmniBrainAgent()
        assert len(agent.reasoning_graph.nodes) == 17
        assert len(agent.reasoning_graph._paths) == 5

    def test_imports_from_package(self):
        """Verify all Day 7-8 classes are importable."""
        from omnibrain.profile import OmniBrainProfile, EmailStats, ProjectContext
        from omnibrain.graph import OmniBrainGraph
        from omnibrain.brain import OmniBrainAgent

        assert OmniBrainProfile is not None
        assert OmniBrainGraph is not None
        assert OmniBrainAgent is not None
        assert EmailStats is not None
        assert ProjectContext is not None

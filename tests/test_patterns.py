"""
Tests for OmniBrain Pattern Detection (Day 21).

Groups:
    DetectedPattern       — pattern data class
    AutomationProposal    — proposal data class
    PatternDetector       — core detection logic
    Helpers               — classify, describe, cluster, normalize
    ObserveAction         — observe_action auto-classification
    30DaySimulation       — simulate 30 days of email patterns
    WeeklyAnalysis        — weekly analysis output
    Promotion             — pattern → automation promotion
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from omnibrain.db import OmniBrainDB
from omnibrain.models import Observation
from omnibrain.proactive.patterns import (
    AutomationProposal,
    DetectedPattern,
    PatternDetector,
    _build_automation_proposal,
    _classify_action,
    _cluster_observations,
    _describe_action,
    _normalize,
    _word_overlap,
)


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
def detector(db):
    return PatternDetector(db)


# ═══════════════════════════════════════════════════════════════════════════
# DetectedPattern
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectedPattern:
    """Test DetectedPattern data class."""

    def test_strength_low_occurrences(self):
        p = DetectedPattern(
            pattern_type="time_pattern",
            description="Morning email check",
            occurrences=1,
            avg_confidence=0.8,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        # 1/10 * 0.8 = 0.08
        assert p.strength == 0.08

    def test_strength_high_occurrences(self):
        p = DetectedPattern(
            pattern_type="time_pattern",
            description="Morning email check",
            occurrences=10,
            avg_confidence=1.0,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        assert p.strength == 1.0

    def test_strength_capped(self):
        """Occurrences above 10 don't increase strength further."""
        p = DetectedPattern(
            pattern_type="x",
            description="y",
            occurrences=20,
            avg_confidence=0.9,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        assert p.strength == 0.9

    def test_to_dict(self):
        now = datetime.now()
        p = DetectedPattern(
            pattern_type="email_routing",
            description="Archive newsletters",
            occurrences=5,
            avg_confidence=0.75,
            first_seen=now,
            last_seen=now,
            observation_ids=[1, 2, 3, 4, 5],
        )
        d = p.to_dict()
        assert d["pattern_type"] == "email_routing"
        assert d["occurrences"] == 5
        assert d["avg_confidence"] == 0.75
        assert len(d["observation_ids"]) == 5
        assert "strength" in d


# ═══════════════════════════════════════════════════════════════════════════
# AutomationProposal
# ═══════════════════════════════════════════════════════════════════════════


class TestAutomationProposal:
    """Test AutomationProposal data class."""

    def test_to_dict(self):
        pattern = DetectedPattern(
            pattern_type="email_routing",
            description="Route",
            occurrences=5,
            avg_confidence=0.8,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        p = AutomationProposal(
            pattern=pattern,
            action_type="auto_route",
            title="Auto-route emails",
            description="Route automatically",
            trigger="on_email",
        )
        d = p.to_dict()
        assert d["action_type"] == "auto_route"
        assert d["title"] == "Auto-route emails"
        assert d["pattern_strength"] == pattern.strength


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:
    """Test internal helper functions."""

    def test_normalize(self):
        assert _normalize("  Hello   World  ") == "hello world"
        assert "HH:MM" in _normalize("reads email at 09:00")
        assert "ID" in _normalize("message abc123def456")

    def test_word_overlap_identical(self):
        assert _word_overlap("hello world", "hello world") == 1.0

    def test_word_overlap_partial(self):
        score = _word_overlap("hello world foo", "hello world bar")
        assert 0.3 < score < 0.8

    def test_word_overlap_none(self):
        assert _word_overlap("aaa", "bbb") == 0.0

    def test_word_overlap_empty(self):
        assert _word_overlap("", "hello") == 0.0

    def test_classify_email_action(self):
        assert _classify_action("send_email", {}) == "communication_pattern"
        assert _classify_action("draft_reply", {}) == "communication_pattern"

    def test_classify_routing_action(self):
        assert _classify_action("archive_email", {}) == "email_routing"
        assert _classify_action("label_email", {}) == "email_routing"

    def test_classify_calendar_action(self):
        assert _classify_action("create_meeting", {}) == "calendar_habit"
        assert _classify_action("schedule_event", {}) == "calendar_habit"

    def test_classify_search_action(self):
        # "search_emails" matches email first → communication; pure search works
        assert _classify_action("search_docs", {}) == "recurring_search"
        assert _classify_action("find_contact", {}) == "recurring_search"
        assert _classify_action("lookup_pricing", {}) == "recurring_search"

    def test_classify_with_time_context(self):
        assert _classify_action("do_stuff", {"time_of_day": "09:00"}) == "time_pattern"

    def test_classify_action_sequence(self):
        assert _classify_action("do_stuff", {"after_action": "meeting"}) == "action_sequence"

    def test_describe_action(self):
        desc = _describe_action("send_email", {"recipient": "marco@example.com"})
        assert "marco@example.com" in desc

    def test_describe_action_with_subject(self):
        desc = _describe_action("reply", {"subject": "Pricing Discussion"})
        assert "Pricing" in desc

    def test_cluster_observations(self):
        obs = [
            {"description": "reads email morning", "id": 1},
            {"description": "reads email morning", "id": 2},
            {"description": "reads email morning", "id": 3},
            {"description": "writes report evening", "id": 4},
        ]
        clusters = _cluster_observations(obs, threshold=0.6)
        assert len(clusters) == 2
        # First cluster should have 3
        sizes = sorted([len(c) for c in clusters], reverse=True)
        assert sizes[0] == 3

    def test_cluster_empty(self):
        assert _cluster_observations([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# PatternDetector
# ═══════════════════════════════════════════════════════════════════════════


class TestPatternDetector:
    """Test PatternDetector core logic."""

    def test_observe(self, detector):
        obs_id = detector.observe("time_pattern", "Morning email check", confidence=0.8)
        assert obs_id > 0

    def test_observe_multiple(self, detector):
        ids = [
            detector.observe("time_pattern", "Morning email check", confidence=0.8)
            for _ in range(5)
        ]
        assert len(ids) == 5
        assert len(set(ids)) == 5  # all unique

    def test_detect_no_observations(self, detector):
        patterns = detector.detect()
        assert patterns == []

    def test_detect_below_threshold(self, detector):
        """Only 2 observations — below min_occurrences=3."""
        detector.observe("time_pattern", "Check email morning", confidence=0.8)
        detector.observe("time_pattern", "Check email morning", confidence=0.9)
        patterns = detector.detect()
        assert len(patterns) == 0

    def test_detect_above_threshold(self, detector):
        """3 observations with high confidence → pattern detected."""
        for _ in range(3):
            detector.observe("time_pattern", "Morning email check", confidence=0.8)
        patterns = detector.detect()
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "time_pattern"
        assert patterns[0].occurrences == 3

    def test_detect_low_confidence_filtered(self, detector):
        """3 observations but low average confidence."""
        for _ in range(3):
            detector.observe("time_pattern", "Random check", confidence=0.2)
        # Default confidence_threshold is 0.5
        patterns = detector.detect()
        assert len(patterns) == 0

    def test_detect_multiple_clusters(self, detector):
        """Different descriptions form different clusters."""
        for _ in range(4):
            detector.observe("time_pattern", "Morning email check", confidence=0.8)
        for _ in range(3):
            detector.observe("time_pattern", "Evening report writing", confidence=0.7)
        patterns = detector.detect()
        assert len(patterns) == 2

    def test_detect_different_types(self, detector):
        """Different pattern types stay separate."""
        for _ in range(3):
            detector.observe("time_pattern", "Morning check", confidence=0.8)
        for _ in range(3):
            detector.observe("email_routing", "Archive newsletters", confidence=0.9)
        patterns = detector.detect()
        assert len(patterns) == 2
        types = {p.pattern_type for p in patterns}
        assert types == {"time_pattern", "email_routing"}

    def test_get_patterns(self, detector):
        """get_patterns returns last detected."""
        assert detector.get_patterns() == []
        for _ in range(3):
            detector.observe("time_pattern", "Morning check", confidence=0.8)
        detector.detect()
        assert len(detector.get_patterns()) == 1

    def test_get_strong_patterns(self, detector):
        """Only patterns above strong_threshold."""
        for _ in range(3):
            detector.observe("time_pattern", "Strong pattern", confidence=0.9)
        for _ in range(3):
            detector.observe("email_routing", "Weak pattern", confidence=0.55)
        detector.detect()
        strong = detector.get_strong_patterns()
        assert len(strong) == 1
        assert strong[0].pattern_type == "time_pattern"

    def test_sorted_by_strength(self, detector):
        """Patterns sorted by strength descending."""
        for _ in range(10):
            detector.observe("time_pattern", "Very strong", confidence=1.0)
        for _ in range(3):
            detector.observe("email_routing", "Somewhat strong", confidence=0.6)
        patterns = detector.detect()
        assert patterns[0].strength >= patterns[1].strength

    def test_summary(self, detector):
        for _ in range(3):
            detector.observe("time_pattern", "Morning check", confidence=0.8)
        detector.detect()
        s = detector.summary()
        assert s["total_observations"] == 3
        assert s["detected_patterns"] == 1

    def test_custom_min_occurrences(self, db):
        """Custom min_occurrences parameter."""
        det = PatternDetector(db, min_occurrences=5)
        for _ in range(4):
            det.observe("time_pattern", "Morning check", confidence=0.9)
        patterns = det.detect()
        assert len(patterns) == 0  # need 5, only have 4

    def test_custom_confidence_threshold(self, db):
        """Custom confidence_threshold."""
        det = PatternDetector(db, confidence_threshold=0.9)
        for _ in range(3):
            det.observe("time_pattern", "Check", confidence=0.85)
        patterns = det.detect()
        assert len(patterns) == 0  # below 0.9 threshold


# ═══════════════════════════════════════════════════════════════════════════
# observe_action
# ═══════════════════════════════════════════════════════════════════════════


class TestObserveAction:
    """Test observe_action auto-classification."""

    def test_email_action(self, detector):
        obs_id = detector.observe_action("send_email", {"recipient": "a@b.com"})
        assert obs_id > 0

    def test_calendar_action(self, detector):
        obs_id = detector.observe_action("create_meeting", {"time": "14:00"})
        assert obs_id > 0

    def test_search_action(self, detector):
        obs_id = detector.observe_action("search_emails", {"query": "pricing"})
        assert obs_id > 0

    def test_classification_flows_to_detection(self, detector):
        """Actions recorded via observe_action are detected as patterns."""
        for _ in range(5):
            detector.observe_action("send_email", {"recipient": "marco@test.com"})
        patterns = detector.detect()
        assert len(patterns) >= 1
        assert any(p.pattern_type == "communication_pattern" for p in patterns)


# ═══════════════════════════════════════════════════════════════════════════
# Automation Proposals
# ═══════════════════════════════════════════════════════════════════════════


class TestAutomationProposals:
    """Test automation proposal generation."""

    def test_propose_for_email_routing(self, detector):
        for _ in range(5):
            detector.observe("email_routing", "Archive newsletters from TechDigest", confidence=0.9)
        detector.detect()
        proposals = detector.propose_automations()
        assert len(proposals) >= 1
        assert proposals[0].action_type == "auto_route_email"

    def test_propose_for_communication(self, detector):
        for _ in range(5):
            detector.observe("communication_pattern", "Reply to Marco about pricing", confidence=0.85)
        detector.detect()
        proposals = detector.propose_automations()
        assert len(proposals) >= 1
        assert proposals[0].action_type == "auto_draft_reply"

    def test_propose_for_search(self, detector):
        for _ in range(5):
            detector.observe("recurring_search", "Search for pricing updates", confidence=0.8)
        detector.detect()
        proposals = detector.propose_automations()
        assert len(proposals) >= 1
        assert proposals[0].action_type == "scheduled_search"

    def test_no_proposals_for_weak(self, detector):
        for _ in range(3):
            detector.observe("time_pattern", "Weak pattern", confidence=0.55)
        detector.detect()
        proposals = detector.propose_automations()
        assert len(proposals) == 0

    def test_build_all_types(self):
        """_build_automation_proposal handles all pattern types."""
        now = datetime.now()
        for ptype, expected_action in [
            ("email_routing", "auto_route_email"),
            ("communication_pattern", "auto_draft_reply"),
            ("recurring_search", "scheduled_search"),
            ("time_pattern", "scheduled_task"),
            ("calendar_habit", "calendar_automation"),
            ("action_sequence", "action_chain"),
        ]:
            p = DetectedPattern(
                pattern_type=ptype,
                description="Test",
                occurrences=5,
                avg_confidence=0.9,
                first_seen=now,
                last_seen=now,
            )
            proposal = _build_automation_proposal(p)
            assert proposal is not None, f"No proposal for {ptype}"
            assert proposal.action_type == expected_action

    def test_build_unknown_type_returns_none(self):
        p = DetectedPattern(
            pattern_type="unknown_type",
            description="Test",
            occurrences=5,
            avg_confidence=0.9,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        assert _build_automation_proposal(p) is None


# ═══════════════════════════════════════════════════════════════════════════
# Promotion
# ═══════════════════════════════════════════════════════════════════════════


class TestPromotion:
    """Test pattern → automation promotion."""

    def test_promote_pattern(self, detector, db):
        for _ in range(3):
            detector.observe("email_routing", "Archive newsletters", confidence=0.9)
        patterns = detector.detect()
        assert len(patterns) == 1

        detector.promote_pattern(patterns[0])

        # Check observations are marked as promoted
        obs = db.get_observations(pattern_type="email_routing")
        for o in obs:
            assert o["promoted_to_automation"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 30 Day Simulation
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulation30Days:
    """Simulate 30 days of email patterns and detect recurring ones."""

    def test_daily_email_check_pattern(self, detector):
        """Pattern: user checks email every morning → detected."""
        for day in range(30):
            detector.observe(
                "time_pattern",
                "Morning email check at 09:00",
                evidence=f"day {day}",
                confidence=0.7 + (day % 3) * 0.1,
            )
        patterns = detector.detect()
        assert len(patterns) >= 1
        morning = [p for p in patterns if "morning" in p.description.lower()]
        assert len(morning) == 1
        assert morning[0].occurrences == 30

    def test_weekly_report_pattern(self, detector):
        """Pattern: user writes report every Monday → detected."""
        for week in range(4):
            detector.observe(
                "time_pattern",
                "Weekly report writing on Monday",
                confidence=0.85,
            )
        patterns = detector.detect()
        weekly = [p for p in patterns if "weekly" in p.description.lower()]
        assert len(weekly) == 1
        assert weekly[0].occurrences == 4

    def test_mixed_patterns(self, detector):
        """Multiple patterns in mixed stream."""
        for day in range(30):
            # Daily email check
            detector.observe("time_pattern", "Morning email check", confidence=0.8)
            # Every 3rd day: newsletter archiving
            if day % 3 == 0:
                detector.observe("email_routing", "Archive TechDigest newsletter", confidence=0.9)
            # Every week: pricing search
            if day % 7 == 0:
                detector.observe("recurring_search", "Search pricing updates", confidence=0.75)

        patterns = detector.detect()
        assert len(patterns) >= 3  # three distinct pattern types

        # Check all types present
        types = {p.pattern_type for p in patterns}
        assert "time_pattern" in types
        assert "email_routing" in types
        assert "recurring_search" in types

    def test_automation_proposals_from_simulation(self, detector):
        """Strong patterns → automation proposals."""
        for _ in range(20):
            detector.observe("email_routing", "Archive promotions from shopping sites", confidence=0.9)
        for _ in range(15):
            detector.observe("communication_pattern", "Reply to client within 1 hour", confidence=0.85)

        detector.detect()
        proposals = detector.propose_automations()
        assert len(proposals) >= 2
        action_types = {p.action_type for p in proposals}
        assert "auto_route_email" in action_types
        assert "auto_draft_reply" in action_types

    def test_noise_filtered_out(self, detector):
        """Random one-off actions don't create patterns."""
        # 30 days of strong pattern
        for _ in range(30):
            detector.observe("time_pattern", "Morning email check", confidence=0.8)

        # Random noise (1-2 occurrences each)
        detector.observe("time_pattern", "Random task XYZ", confidence=0.3)
        detector.observe("email_routing", "One-off filter action", confidence=0.4)
        detector.observe("calendar_habit", "Unusual meeting prep", confidence=0.2)

        patterns = detector.detect()
        # Only the strong daily pattern should be detected
        assert len(patterns) == 1
        assert patterns[0].occurrences == 30


# ═══════════════════════════════════════════════════════════════════════════
# Weekly Analysis
# ═══════════════════════════════════════════════════════════════════════════


class TestWeeklyAnalysis:
    """Test weekly_analysis output."""

    def test_weekly_analysis_empty(self, detector):
        result = detector.weekly_analysis()
        assert result["patterns_detected"] == 0
        assert result["automations_proposed"] == 0

    def test_weekly_analysis_with_data(self, detector):
        for _ in range(10):
            detector.observe("email_routing", "Archive newsletters", confidence=0.9)
        for _ in range(5):
            detector.observe("time_pattern", "Morning check", confidence=0.75)

        result = detector.weekly_analysis()
        assert result["patterns_detected"] >= 2
        assert result["automations_proposed"] >= 1
        assert len(result["top_patterns"]) >= 2
        assert len(result["proposals"]) >= 1

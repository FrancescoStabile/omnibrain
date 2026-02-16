"""
Tests for PriorityScorer and NotificationLevelSelector.

Coverage targets:
    - PriorityScorer core scoring (all 5 signals)
    - Convenience methods (score_email, score_event, score_proposal, score_pattern)
    - Notification level thresholds
    - Weight normalisation
    - Hard overrides (force_critical, force_silent)
    - NotificationLevelSelector (all for_* methods)
    - Quiet hours logic
    - Rate limiting
    - Module-level helpers
    - Edge cases
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from omnibrain.models import NotificationLevel as NL, Priority, Urgency
from omnibrain.proactive.scorer import (
    CRITICAL_THRESHOLD,
    DEFAULT_WEIGHTS,
    FYI_THRESHOLD,
    IMPORTANT_THRESHOLD,
    NotificationLevelSelector,
    PriorityScore,
    PriorityScorer,
    ScoreBreakdown,
    ScoringSignals,
    _downgrade_level,
    _in_quiet_hours,
    score_item,
    select_notification_level,
)


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


class TestScoringSignals:
    def test_defaults(self):
        s = ScoringSignals()
        assert s.urgency_label == ""
        assert s.priority_value == Priority.UNSET.value
        assert s.deadline is None
        assert s.is_vip is False
        assert s.relationship == "unknown"
        assert s.item_type == ""
        assert s.pattern_strength == 0.0
        assert not s.force_critical
        assert not s.force_silent

    def test_to_dict(self):
        s = ScoringSignals(
            urgency_label="high",
            is_vip=True,
            item_type="action_required",
            deadline=datetime(2025, 6, 15, 10, 0),
        )
        d = s.to_dict()
        assert d["urgency_label"] == "high"
        assert d["is_vip"] is True
        assert d["item_type"] == "action_required"
        assert d["deadline"] == "2025-06-15T10:00:00"

    def test_no_deadline_in_dict(self):
        d = ScoringSignals().to_dict()
        assert d["deadline"] is None


class TestScoreBreakdown:
    def test_to_dict_keys(self):
        b = ScoreBreakdown(urgency_raw=0.8, urgency_weighted=0.24)
        d = b.to_dict()
        assert d["urgency"]["raw"] == 0.8
        assert d["urgency"]["weighted"] == 0.24
        assert "deadline" in d
        assert "contact" in d
        assert "type" in d
        assert "pattern" in d


class TestPriorityScore:
    def test_to_dict(self):
        ps = PriorityScore(
            score=0.72,
            notification_level="important",
            reason="test",
        )
        d = ps.to_dict()
        assert d["score"] == 0.72
        assert d["notification_level"] == "important"
        assert d["reason"] == "test"
        assert "breakdown" in d


# ═══════════════════════════════════════════════════════════════════════════
# PriorityScorer — Core
# ═══════════════════════════════════════════════════════════════════════════


class TestPriorityScorerInit:
    def test_default_weights(self):
        scorer = PriorityScorer()
        assert scorer.weights == DEFAULT_WEIGHTS
        assert abs(sum(scorer.weights.values()) - 1.0) < 0.01

    def test_custom_weights_normalised(self):
        scorer = PriorityScorer(weights={"urgency": 2, "deadline": 2, "contact": 2, "type": 2, "pattern": 2})
        assert abs(sum(scorer.weights.values()) - 1.0) < 0.01

    def test_thresholds(self):
        scorer = PriorityScorer()
        assert scorer.thresholds["critical"] == CRITICAL_THRESHOLD
        assert scorer.thresholds["important"] == IMPORTANT_THRESHOLD
        assert scorer.thresholds["fyi"] == FYI_THRESHOLD

    def test_custom_thresholds(self):
        scorer = PriorityScorer(critical_threshold=0.9, important_threshold=0.6, fyi_threshold=0.3)
        assert scorer.thresholds["critical"] == 0.9


class TestForceOverrides:
    def test_force_critical(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(force_critical=True))
        assert result.score == 1.0
        assert result.notification_level == NL.CRITICAL.value
        assert "Force-critical" in result.reason

    def test_force_silent(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(force_silent=True))
        assert result.score == 0.0
        assert result.notification_level == NL.SILENT.value
        assert "Force-silent" in result.reason


class TestUrgencySignal:
    def test_critical_urgency(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="critical"))
        assert result.breakdown.urgency_raw == 1.0
        assert result.breakdown.urgency_weighted > 0

    def test_high_urgency(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="high"))
        assert result.breakdown.urgency_raw == 0.8

    def test_medium_urgency(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="medium"))
        assert result.breakdown.urgency_raw == 0.5

    def test_low_urgency(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="low"))
        assert result.breakdown.urgency_raw == 0.2

    def test_unknown_urgency_fallback(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="xyz"))
        assert result.breakdown.urgency_raw == 0.3  # default fallback

    def test_priority_enum_when_no_label(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(priority_value=Priority.HIGH.value))
        assert result.breakdown.urgency_raw == 0.8

    def test_label_overrides_priority(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(
            urgency_label="low",
            priority_value=Priority.CRITICAL.value,
        ))
        # Label takes priority
        assert result.breakdown.urgency_raw == 0.2


class TestDeadlineSignal:
    def test_no_deadline(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals())
        assert result.breakdown.deadline_raw == 0.0

    def test_past_due(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now - timedelta(hours=1),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 1.0

    def test_imminent_30_min(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(minutes=20),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 1.0

    def test_2_hours(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(hours=1),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 0.8

    def test_8_hours(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(hours=5),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 0.6

    def test_24_hours(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(hours=12),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 0.4

    def test_72_hours(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(hours=48),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 0.2

    def test_far_future(self):
        scorer = PriorityScorer()
        now = datetime.now()
        result = scorer.score(ScoringSignals(
            deadline=now + timedelta(days=30),
            reference_time=now,
        ))
        assert result.breakdown.deadline_raw == 0.1


class TestContactSignal:
    def test_vip_boost(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(is_vip=True))
        assert result.breakdown.contact_raw >= 0.8

    def test_client_relationship(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(relationship="client"))
        assert result.breakdown.contact_raw == 0.9

    def test_investor_relationship(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(relationship="investor"))
        assert result.breakdown.contact_raw == 0.9

    def test_unknown_relationship(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(relationship="unknown"))
        assert result.breakdown.contact_raw == 0.2

    def test_interaction_bonus(self):
        scorer = PriorityScorer()
        r1 = scorer.score(ScoringSignals(relationship="unknown", interaction_count=0))
        r2 = scorer.score(ScoringSignals(relationship="unknown", interaction_count=25))
        assert r2.breakdown.contact_raw > r1.breakdown.contact_raw

    def test_interaction_bonus_capped(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(relationship="unknown", interaction_count=1000))
        assert result.breakdown.contact_raw <= 1.0


class TestTypeSignal:
    def test_action_required(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(item_type="action_required"))
        assert result.breakdown.type_raw == 0.9

    def test_newsletter(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(item_type="newsletter"))
        assert result.breakdown.type_raw == 0.2

    def test_spam(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(item_type="spam"))
        assert result.breakdown.type_raw == 0.0

    def test_unknown_type_fallback(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(item_type="custom_thing"))
        assert result.breakdown.type_raw == 0.3


class TestPatternSignal:
    def test_no_pattern(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals())
        assert result.breakdown.pattern_raw == 0.0

    def test_strong_pattern(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(pattern_strength=0.9))
        assert result.breakdown.pattern_raw >= 0.9

    def test_occurrences_bonus(self):
        scorer = PriorityScorer()
        r1 = scorer.score(ScoringSignals(pattern_strength=0.5, pattern_occurrences=0))
        r2 = scorer.score(ScoringSignals(pattern_strength=0.5, pattern_occurrences=20))
        assert r2.breakdown.pattern_raw > r1.breakdown.pattern_raw

    def test_pattern_capped(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(pattern_strength=0.95, pattern_occurrences=100))
        assert result.breakdown.pattern_raw <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Notification Level Thresholds
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationLevels:
    def test_critical_level(self):
        scorer = PriorityScorer()
        # All signals maxed → critical
        result = scorer.score(ScoringSignals(
            urgency_label="critical",
            deadline=datetime.now() - timedelta(hours=1),
            reference_time=datetime.now(),
            is_vip=True,
            item_type="action_required",
            pattern_strength=1.0,
        ))
        assert result.notification_level == NL.CRITICAL.value
        assert result.score >= CRITICAL_THRESHOLD

    def test_silent_level(self):
        scorer = PriorityScorer()
        # Minimal signals → silent
        result = scorer.score(ScoringSignals(
            urgency_label="low",
            item_type="spam",
            relationship="unknown",
        ))
        assert result.notification_level == NL.SILENT.value
        assert result.score < FYI_THRESHOLD

    def test_important_level(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(
            urgency_label="high",
            item_type="meeting_prep",
            is_vip=True,
            deadline=datetime.now() + timedelta(hours=1),
            reference_time=datetime.now(),
        ))
        assert result.notification_level in (NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_fyi_level(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(
            urgency_label="medium",
            item_type="fyi",
            relationship="unknown",
        ))
        assert result.notification_level in (NL.FYI.value, NL.SILENT.value)

    def test_score_monotonic_with_urgency(self):
        """Higher urgency → higher score."""
        scorer = PriorityScorer()
        scores = {}
        for u in ["low", "medium", "high", "critical"]:
            r = scorer.score(ScoringSignals(urgency_label=u))
            scores[u] = r.score
        assert scores["low"] < scores["medium"]
        assert scores["medium"] < scores["high"]
        assert scores["high"] < scores["critical"]


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Methods
# ═══════════════════════════════════════════════════════════════════════════


class TestScoreEmail:
    def test_critical_vip_email(self):
        scorer = PriorityScorer()
        result = scorer.score_email(urgency="critical", sender_is_vip=True, category="action_required")
        assert result.score >= 0.55
        assert result.notification_level in (NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_newsletter_email(self):
        scorer = PriorityScorer()
        result = scorer.score_email(urgency="low", category="newsletter")
        assert result.notification_level in (NL.SILENT.value, NL.FYI.value)

    def test_interaction_count_used(self):
        scorer = PriorityScorer()
        r1 = scorer.score_email(urgency="medium", interaction_count=0)
        r2 = scorer.score_email(urgency="medium", interaction_count=40)
        assert r2.score >= r1.score


class TestScoreEvent:
    def test_imminent_meeting_large_group(self):
        scorer = PriorityScorer()
        result = scorer.score_event(
            deadline=datetime.now() + timedelta(minutes=10),
            attendee_count=8,
        )
        assert result.score >= 0.5

    def test_far_meeting_solo(self):
        scorer = PriorityScorer()
        result = scorer.score_event(
            deadline=datetime.now() + timedelta(days=7),
            attendee_count=1,
        )
        assert result.score < 0.5

    def test_vip_attendee_boost(self):
        scorer = PriorityScorer()
        r1 = scorer.score_event(attendee_count=2)
        r2 = scorer.score_event(attendee_count=2, has_vip_attendee=True)
        assert r2.score > r1.score


class TestScoreProposal:
    def test_high_priority_proposal(self):
        scorer = PriorityScorer()
        result = scorer.score_proposal(priority=Priority.HIGH.value)
        assert result.score >= 0.3

    def test_low_priority_proposal(self):
        scorer = PriorityScorer()
        result = scorer.score_proposal(priority=Priority.LOW.value)
        assert result.score < 0.5

    def test_proposal_with_deadline(self):
        scorer = PriorityScorer()
        r1 = scorer.score_proposal(priority=Priority.MEDIUM.value)
        r2 = scorer.score_proposal(
            priority=Priority.MEDIUM.value,
            deadline=datetime.now() + timedelta(minutes=10),
        )
        assert r2.score > r1.score


class TestScorePattern:
    def test_weak_pattern(self):
        scorer = PriorityScorer()
        result = scorer.score_pattern(strength=0.2, occurrences=2)
        assert result.score < 0.3

    def test_strong_pattern(self):
        scorer = PriorityScorer()
        result = scorer.score_pattern(strength=0.9, occurrences=15)
        assert result.score >= 0.1  # pattern weight is only 10%


# ═══════════════════════════════════════════════════════════════════════════
# Reason Generation
# ═══════════════════════════════════════════════════════════════════════════


class TestReasonGeneration:
    def test_reason_contains_level(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="critical"))
        assert any(lvl in result.reason for lvl in ["CRITICAL", "IMPORTANT", "FYI", "SILENT"])

    def test_reason_mentions_vip(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(is_vip=True))
        assert "VIP" in result.reason or "contact" in result.reason

    def test_reason_mentions_urgency(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(urgency_label="critical"))
        assert "urgency" in result.reason.lower() or "critical" in result.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# NotificationLevelSelector
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationLevelSelector:
    def test_for_email_critical(self):
        sel = NotificationLevelSelector()
        level = sel.for_email(urgency="critical", sender_is_vip=True, category="action_required")
        assert level in (NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_for_email_low(self):
        sel = NotificationLevelSelector()
        level = sel.for_email(urgency="low", category="newsletter")
        assert level in (NL.SILENT.value, NL.FYI.value)

    def test_for_event(self):
        sel = NotificationLevelSelector()
        level = sel.for_event(minutes_until=10, attendees=5, has_vip=True)
        assert level in (NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_for_event_no_deadline(self):
        sel = NotificationLevelSelector()
        level = sel.for_event(attendees=1)
        assert level in (NL.SILENT.value, NL.FYI.value, NL.IMPORTANT.value)

    def test_for_proposal(self):
        sel = NotificationLevelSelector()
        level = sel.for_proposal(priority=Priority.HIGH.value)
        assert level in (NL.FYI.value, NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_for_pattern(self):
        sel = NotificationLevelSelector()
        level = sel.for_pattern(strength=0.3, occurrences=5)
        assert level in (NL.SILENT.value, NL.FYI.value)

    def test_for_score_direct(self):
        sel = NotificationLevelSelector()
        assert sel.for_score(0.9) in (NL.CRITICAL.value, NL.IMPORTANT.value)
        assert sel.for_score(0.1) == NL.SILENT.value


class TestQuietHours:
    def test_no_quiet_hours(self):
        sel = NotificationLevelSelector(quiet_hours=None)
        assert not sel.is_quiet_hours

    def test_quiet_hours_downgrade(self):
        """During quiet hours, levels should be downgraded."""
        sel = NotificationLevelSelector(quiet_hours=(0, 24))  # Always quiet
        level = sel.for_email(urgency="critical", sender_is_vip=True, category="action_required")
        # Should be downgraded from CRITICAL → IMPORTANT or IMPORTANT → FYI
        assert level != NL.CRITICAL.value

    def test_quiet_hours_helper_daytime(self):
        assert _in_quiet_hours(14, (22, 7)) is False  # 2 PM not in 10PM-7AM
        assert _in_quiet_hours(3, (22, 7)) is True     # 3 AM in 10PM-7AM
        assert _in_quiet_hours(23, (22, 7)) is True    # 11 PM in 10PM-7AM

    def test_quiet_hours_same_day(self):
        assert _in_quiet_hours(10, (9, 17)) is True    # 10 AM in 9AM-5PM
        assert _in_quiet_hours(20, (9, 17)) is False   # 8 PM not in 9AM-5PM

    def test_downgrade_level_helper(self):
        assert _downgrade_level(NL.CRITICAL.value) == NL.IMPORTANT.value
        assert _downgrade_level(NL.IMPORTANT.value) == NL.FYI.value
        assert _downgrade_level(NL.FYI.value) == NL.FYI.value
        assert _downgrade_level(NL.SILENT.value) == NL.SILENT.value


class TestRateLimiting:
    def test_rate_limit_critical(self):
        sel = NotificationLevelSelector(max_critical_per_hour=2)
        # Simulate 2 critical notifications
        sel._critical_history = [datetime.now(), datetime.now()]

        # Third should be downgraded
        level = sel._apply_modifiers(NL.CRITICAL.value)
        assert level == NL.IMPORTANT.value

    def test_rate_limit_old_entries_pruned(self):
        sel = NotificationLevelSelector(max_critical_per_hour=2)
        # Old entries (2 hours ago) should be pruned
        old = datetime.now() - timedelta(hours=2)
        sel._critical_history = [old, old]

        level = sel._apply_modifiers(NL.CRITICAL.value)
        assert level == NL.CRITICAL.value  # Not rate limited

    def test_rate_limit_zero_disables(self):
        sel = NotificationLevelSelector(max_critical_per_hour=0)
        level = sel._apply_modifiers(NL.CRITICAL.value)
        assert level == NL.CRITICAL.value  # No rate limiting


# ═══════════════════════════════════════════════════════════════════════════
# Module-level Convenience
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleLevel:
    def test_score_item(self):
        result = score_item(ScoringSignals(urgency_label="high"))
        assert isinstance(result, PriorityScore)
        assert result.score > 0

    def test_select_notification_level(self):
        assert select_notification_level(0.9) in (NL.CRITICAL.value, NL.IMPORTANT.value)
        assert select_notification_level(0.1) == NL.SILENT.value

    def test_select_levels_monotonic(self):
        levels = [select_notification_level(s / 10) for s in range(11)]
        # Should never go from higher to lower level as score increases
        level_order = {NL.SILENT.value: 0, NL.FYI.value: 1, NL.IMPORTANT.value: 2, NL.CRITICAL.value: 3}
        numeric = [level_order[l] for l in levels]
        for i in range(len(numeric) - 1):
            assert numeric[i] <= numeric[i + 1]


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases & Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_score_capped_at_1(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals(
            urgency_label="critical",
            deadline=datetime.now() - timedelta(hours=1),
            reference_time=datetime.now(),
            is_vip=True,
            item_type="action_required",
            pattern_strength=1.0,
            pattern_occurrences=100,
        ))
        assert result.score <= 1.0

    def test_empty_signals(self):
        scorer = PriorityScorer()
        result = scorer.score(ScoringSignals())
        assert 0.0 <= result.score <= 1.0
        assert result.notification_level in (
            NL.SILENT.value, NL.FYI.value, NL.IMPORTANT.value, NL.CRITICAL.value,
        )

    def test_all_urgency_values(self):
        scorer = PriorityScorer()
        for u in Urgency:
            result = scorer.score(ScoringSignals(urgency_label=u.value))
            assert 0.0 <= result.score <= 1.0

    def test_all_priority_values(self):
        scorer = PriorityScorer()
        for p in Priority:
            result = scorer.score(ScoringSignals(priority_value=p.value))
            assert 0.0 <= result.score <= 1.0

    def test_custom_scorer_in_selector(self):
        scorer = PriorityScorer(critical_threshold=0.3)
        sel = NotificationLevelSelector(scorer=scorer)
        level = sel.for_email(urgency="critical")
        # With lower threshold, should be critical more easily
        assert level in (NL.IMPORTANT.value, NL.CRITICAL.value)

    def test_combined_quiet_hours_and_rate_limit(self):
        """Both quiet hours and rate limit active simultaneously."""
        sel = NotificationLevelSelector(
            quiet_hours=(0, 24),  # Always quiet
            max_critical_per_hour=1,
        )
        # First call: CRITICAL → downgraded to IMPORTANT (quiet hours)
        level = sel.for_email(urgency="critical", sender_is_vip=True, category="action_required")
        assert level != NL.CRITICAL.value
